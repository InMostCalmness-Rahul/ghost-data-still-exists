"""Parser for evidence/databases/*.sql point-in-time snapshots.

Every file is SQLite-compatible (problem_statement.md), so each dump is
executed inside a throwaway in-memory database and every user table is mapped
to normalized observations. The file header carries the capture timestamp and
the topology label, e.g.::

    -- Captured at: 2026-09-02T23:00:00Z
    -- Database topology: failover_replica

The topology stays attached to each observation via ``attributes["topology"]``
and ``attributes["sql_table"]`` so replica drift can be compared later.
"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from .classify import classify_kind, extract_refs
from .models import EvidenceFile, Observation
from .timeutil import parse_iso

_TOPOLOGY_RE = re.compile(r"^--\s*Database topology:\s*(\S+)", re.MULTILINE)
_CAPTURE_RE = re.compile(r"^--\s*Captured at:\s*(\S+)", re.MULTILINE)

# Typed tables from inventory snapshots: table name -> record category.
_TYPED_TABLE_KIND = {
    "customer_profiles": ("USER_PROFILE", "account_service"),
    "customer_search_documents": ("SEARCH_INDEX_ENTRY", "search_service"),
    "customer_analytics_profiles": ("ANALYTICS_PROFILE", "analytics_platform"),
    "support_records": ("SUPPORT_MESSAGE", "support_platform"),
    "customer_exports": ("USER_EXPORT", "export_service"),
    "connector_subscriptions": ("DATA_FLOW", "integration_service"),
    "backup_restore_entries": ("BACKUP_ARCHIVE", "backup_service"),
    "security_audit_records": ("SECURITY_AUDIT_LOG", "security_service"),
    "customer_search_primary": ("SEARCH_INDEX_ENTRY", "search_service"),
    "search_documents_primary": ("SEARCH_INDEX_ENTRY", "search_service"),
}

_WRAPPED_TABLES = {
    "customer_data_primary",
    "customer_data_read_replica",
    "customer_data_reporting_replica",
    "customer_data_failover_replica",
    "customer_data_replica_ap_south",
    "customer_data_replica_eu_west",
    "customer_profiles_primary",
    "customer_profiles_failover_replica",
}


def _wrapped_table_name(table: str) -> str | None:
    low = table.lower()
    if low in _WRAPPED_TABLES:
        return table
    if "replica" in low or "primary" in low:
        return table
    return None


def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    cur = conn.execute(f'PRAGMA table_info("{table}")')
    return [row[1] for row in cur.fetchall()]


def _row_to_observation(
    *,
    file_id: str,
    source_path: str,
    captured_at: datetime | None,
    topology: str | None,
    table: str,
    columns: list[str],
    row: dict,
) -> Observation | None:
    resource_id = str(row.get("resource_id") or "").strip()
    if not resource_id:
        return None
    record_json = row.get("record_json")
    if isinstance(record_json, str) and record_json.strip():
        try:
            inner = json.loads(record_json)
        except json.JSONDecodeError:
            inner = None
        if isinstance(inner, dict):
            inner.setdefault("resource_id", resource_id)
            obs = _from_wrapped_record(
                file_id=file_id,
                source_path=source_path,
                captured_at=captured_at,
                topology=topology,
                table=table,
                columns=columns,
                record=inner,
                updated_at=row.get("updated_at"),
            )
            if obs:
                return obs
    kind_pair = _TYPED_TABLE_KIND.get(table)
    kind, system = kind_pair if kind_pair else (classify_kind(resource_id, table), None)
    if table == "customer_profiles" or table.startswith("customer_profiles_"):
        kind = "USER_PROFILE"
        system = system or "account_service"
    refs = extract_refs(row)
    present: bool | None = True
    enabled = None
    restore_allowed = None
    identifiable = None
    if table == "connector_subscriptions" or table.startswith("connector"):
        enabled = bool(row.get("enabled"))
    if "restore_allowed" in row and row.get("restore_allowed") is not None:
        restore_allowed = bool(row.get("restore_allowed"))
    if table in ("security_audit_records",):
        present = True
    ident_fields = ("full_name", "email", "phone", "email_hash", "display_name",
                    "requester_name", "requester_email", "requester_phone", "owner_email")
    identifiable = any(
        isinstance(row.get(f), str) and row.get(f).strip() and row.get(f).strip().lower() != "null"
        for f in ident_fields
    ) or None
    attributes = dict(row)
    attributes["sql_table"] = table
    if topology:
        attributes["topology"] = topology
    return Observation(
        file_id=file_id,
        source_path=source_path,
        source_kind="sql",
        captured_at=captured_at,
        system=system,
        resource_id=resource_id,
        kind=kind,
        observed_at=parse_iso(row.get("updated_at")) or parse_iso(row.get("indexed_at")) or captured_at,
        refs=refs,
        present=present,
        enabled=enabled,
        restore_allowed=restore_allowed,
        identifiable=identifiable,
        retention_until=parse_iso(row.get("retention_until")),
        account_status=row.get("account_status"),
        attributes=attributes,
    )


def _from_wrapped_record(
    *,
    file_id: str,
    source_path: str,
    captured_at: datetime | None,
    topology: str | None,
    table: str,
    columns: list[str],
    record: dict,
    updated_at: str | None,
) -> Observation | None:
    resource_id = str(record.get("resource_id") or "").strip()
    if not resource_id:
        return None
    collection = record.get("__collection__") or ""
    kind = classify_kind(resource_id, record.get("record_type"), collection)
    refs = extract_refs(record)
    ident_fields = ("email", "phone", "email_hash", "full_name", "name", "display_name",
                    "requester_name", "requester_email", "requester_phone")
    any_identifier = any(
        isinstance(record.get(f), str) and record.get(f).strip() and record.get(f).strip().lower() != "null"
        for f in ident_fields
    )
    present: bool | None = True
    enabled = None
    restore_allowed = None
    identifiable = None
    account_status = record.get("account_status")
    if "enabled" in record and record.get("enabled") is not None:
        enabled = bool(record.get("enabled")) if not isinstance(record.get("enabled"), str) \
            else record.get("enabled").strip().lower() in ("true", "1")
    if "restore_allowed" in record and record.get("restore_allowed") is not None:
        value = record.get("restore_allowed")
        restore_allowed = bool(value) if not isinstance(value, str) else value.strip().lower() in ("true", "1")
    if collection in ("customer_analytics_reports", "deleted_customer_references",
                      "support_conversations", "security_audit_events"):
        identifiable = any_identifier or None
    attributes = dict(record)
    attributes["sql_table"] = table
    if collection:
        attributes["collection"] = collection
    if topology:
        attributes["topology"] = topology
    return Observation(
        file_id=file_id,
        source_path=source_path,
        source_kind="sql",
        captured_at=captured_at,
        system=record.get("__origin_system__") or record.get("system"),
        resource_id=resource_id,
        kind=kind,
        observed_at=parse_iso(record.get("recorded_at")) or parse_iso(updated_at) or captured_at,
        refs=refs,
        present=present,
        enabled=enabled,
        restore_allowed=restore_allowed,
        identifiable=identifiable,
        retention_until=parse_iso(record.get("retention_until")) or parse_iso(record.get("retained_until")),
        account_status=account_status,
        attributes=attributes,
    )


def parse_sql_snapshot(path: Path, file_id: str, dataset_relative: str) -> EvidenceFile:
    notes: list[str] = []
    text = path.read_text(encoding="utf-8", errors="replace")
    topology_match = _TOPOLOGY_RE.search(text)
    capture_match = _CAPTURE_RE.search(text)
    topology = topology_match.group(1) if topology_match else None
    captured_at = parse_iso(capture_match.group(1)) if capture_match else None
    try:
        conn = sqlite3.connect(":memory:")
        conn.executescript(text)
    except (sqlite3.Error, OSError) as exc:
        conn = None
        notes.append(f"sqlite exec failed: {exc.__class__.__name__}")
    records: list[Observation] = []
    if conn is not None:
        try:
            table_rows = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
            for (table,) in table_rows:
                columns = _columns(conn, table)
                rows = [dict(zip(columns, values)) for values in conn.execute(f'SELECT * FROM "{table}"')]
                if table == "snapshot_scope":
                    for row in rows:
                        notes.append(f"scope:{row.get('origin_system')}@{row.get('captured_at')}")
                    if captured_at is None and rows:
                        first = rows[0].get("captured_at")
                        captured_at = parse_iso(first) if first else None
                    continue
                wrapped = _wrapped_table_name(table)
                if wrapped is not None and "record_json" in columns:
                    for row in rows:
                        try:
                            inner = json.loads(row.get("record_json") or "")
                        except json.JSONDecodeError:
                            notes.append(f"bad_record_json:{row.get('resource_id')}")
                            continue
                        if not isinstance(inner, dict):
                            notes.append(f"non_object_record_json:{row.get('resource_id')}")
                            continue
                        inner.setdefault("__origin_system__", row.get("origin_system"))
                        inner.setdefault("__collection__", row.get("collection_name"))
                        obs = _from_wrapped_record(
                            file_id=file_id,
                            source_path=dataset_relative,
                            captured_at=captured_at,
                            topology=topology,
                            table=table,
                            columns=columns,
                            record=inner,
                            updated_at=row.get("updated_at"),
                        )
                        if obs:
                            records.append(obs)
                    notes.append(f"table={table}({len(rows)})")
                    continue
                if table in _TYPED_TABLE_KIND or table.startswith("customer_profiles_"):
                    for row in rows:
                        obs = _row_to_observation(
                            file_id=file_id,
                            source_path=dataset_relative,
                            captured_at=captured_at,
                            topology=topology,
                            table=table,
                            columns=columns,
                            row=row,
                        )
                        if obs:
                            records.append(obs)
                    notes.append(f"table={table}({len(rows)})")
                    continue
                # Unmapped tables are kept as notes so nothing silently disappears.
                notes.append(f"unmapped_table={table}({len(rows)})")
        except sqlite3.Error as exc:
            notes.append(f"sqlite read failed: {exc.__class__.__name__}")
        finally:
            conn.close()
    notes.append(f"topology={topology}" if topology else "topology=unlabeled")
    return EvidenceFile(
        file_id=file_id,
        path=dataset_relative,
        origin="database_snapshot",
        captured_at=captured_at,
        parser_kind="sql",
        records=records,
        notes=notes,
    )
