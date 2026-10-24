"""Parser for evidence/records/*.json (and *.txt handover documents).

Two record families exist:

1. Structured record collections: a top-level document with ``collection`` +
   ``records``, or ``snapshots`` splitting per data_store/collection.
2. Lookup-style registries: record items carrying
   ``system``/``resource_id``/``record_type``/``result``/``subject_reference``.
   The same row shape also appears in some .log and .txt files, hence the
   shared helper ``parse_lookup_record``.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .classify import classify_kind, extract_refs, owner_refs_from_record, reidentify_value
from .models import EvidenceFile, Observation
from .timeutil import parse_iso


def _present_from_result(result: str | None) -> bool | None:
    if result is None:
        return None
    lowered = result.strip().lower()
    if lowered in ("found", "active", "identifiable", "present"):
        return True
    if lowered in ("not_found", "absent"):
        return False
    # REDACTED / ANONYMIZED / BLOCKED imply the record still exists.
    if lowered in ("redacted", "anonymized", "blocked", "disabled"):
        return True
    return None


def _flag_from_result(result: str | None, flag: str) -> bool | None:
    lowered = (result or "").strip().lower()
    if not lowered:
        return None
    return lowered == flag


def _bool(value) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def _truthy_text(value) -> bool:
    return isinstance(value, str) and bool(value.strip()) and value.strip().lower() != "null"


def _privacy_flags(
    kind: str,
    identifiable: bool,
) -> tuple[bool, bool | None, bool | None]:
    """Return explicit identifier presence and applicable privacy treatment."""
    if identifiable:
        return True, None, None
    if kind in {"ACCOUNT_TOMBSTONE", "SUPPORT_MESSAGE", "EMAIL_DELIVERY_LOG"}:
        return False, True, None
    if kind in {"ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"}:
        return False, None, True
    return False, None, None


def parse_lookup_record(
    *,
    file_id: str,
    source_path: str,
    source_kind: str,
    captured_at: datetime | None,
    record: dict,
    default_observed_at: datetime | None = None,
) -> Observation | None:
    """Parse a ``system | resource_id | record_type | result | reference`` row."""
    resource_id = str(record.get("resource_id") or "").strip()
    if not resource_id:
        return None
    record_type = record.get("record_type")
    result = record.get("result")
    system = record.get("system") or record.get("source_system")
    observed_at = parse_iso(record.get("recorded_at")) or default_observed_at
    owner_refs = owner_refs_from_record(record)
    attributes = {k: v for k, v in record.items() if k != "subject_reference"}
    lowered_result = (result or "").strip().lower()
    kind_hint = classify_kind(resource_id, record_type)
    enabled = restore_allowed = None
    if kind_hint == "DATA_FLOW":
        if lowered_result in ("active",):
            enabled = True
        elif lowered_result in ("disabled", "stopped"):
            enabled = False
    if kind_hint == "BACKUP_ARCHIVE":
        if lowered_result in ("blocked",):
            restore_allowed = False
        elif lowered_result in ("active",):
            restore_allowed = True
    return Observation(
        file_id=file_id,
        source_path=source_path,
        source_kind=source_kind,
        captured_at=captured_at,
        system=system or None,
        resource_id=resource_id,
        kind=kind_hint,
        observed_at=observed_at,
        refs=owner_refs,
        present=_present_from_result(result),
        enabled=enabled,
        restore_allowed=restore_allowed,
        identifiable=True if lowered_result == "identifiable" else None,
        redacted=True if lowered_result == "redacted" else None,
        anonymized=True if lowered_result == "anonymized" else None,
        attributes=attributes,
    )


_STRUCTURED_COLLECTIONS = {
    "customer_profiles",
    "customer_search_documents",
    "customer_analytics_reports",
    "deleted_customer_references",
    "support_conversations",
    "ticket_attachments",
    "backup_catalog",
    "connector_configurations",
    "customer_export_jobs",
    "security_audit_events",
    "retained_order_records",
    "operational_record_history",
}


def parse_structured_record(
    *,
    file_id: str,
    source_path: str,
    source_kind: str,
    captured_at: datetime | None,
    collection: str,
    data_store: str | None,
    record: dict,
    default_observed_at: datetime | None = None,
) -> Observation | None:
    resource_id = str(record.get("resource_id") or "").strip()
    if not resource_id:
        return None
    record_type = record.get("record_type")
    result = record.get("result")
    kind = classify_kind(
        resource_id,
        record_type or ("LEGAL_HOLD_RECORD" if collection == "retained_order_records" else None),
        collection,
    )
    refs = extract_refs(record)
    attributes = dict(record)
    present: bool | None = None
    enabled = _bool(record.get("enabled"))
    restore_allowed = _bool(record.get("restore_allowed"))
    ident_fields = (
        "email", "phone", "email_hash", "full_name", "name", "display_name",
        "requester_name", "requester_email", "requester_phone",
    )
    any_identifier = any(_truthy_text(record.get(f)) for f in ident_fields)
    identifiable: bool | None = None
    redacted: bool | None = None
    anonymized: bool | None = None
    if result:
        present = _present_from_result(result)
        redacted = _flag_from_result(result, "redacted")
        anonymized = _flag_from_result(result, "anonymized")
        identifiable = True if result.strip().lower() == "identifiable" else None
        if anonymized:
            identifiable = False
    elif collection in _STRUCTURED_COLLECTIONS:
        if collection == "customer_export_jobs" and "download_available" in record:
            present = _bool(record.get("download_available"))
        else:
            present = True
        identifiable, inferred_redacted, inferred_anonymized = _privacy_flags(kind, any_identifier)
        redacted = inferred_redacted
        anonymized = inferred_anonymized
    return Observation(
        file_id=file_id,
        source_path=source_path,
        source_kind=source_kind,
        captured_at=captured_at,
        system=data_store or record.get("system"),
        resource_id=resource_id,
        kind=kind,
        observed_at=(
            parse_iso(record.get("recorded_at"))
            or parse_iso(record.get("indexed_at"))
            or parse_iso(record.get("observed_at"))
            or default_observed_at
        ),
        refs=refs,
        present=present,
        enabled=enabled,
        restore_allowed=restore_allowed,
        identifiable=identifiable,
        redacted=redacted,
        anonymized=anonymized,
        retention_until=parse_iso(record.get("retention_until")) or parse_iso(record.get("retained_until")),
        account_status=record.get("account_status") or record.get("status"),
        attributes=attributes,
    )


def parse_records_document(path: Path, file_id: str, dataset_relative: str) -> EvidenceFile:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return EvidenceFile(
            file_id, dataset_relative, "", None, "json", [],
            [f"json decode failed: {exc.__class__.__name__}"],
        )
    if not isinstance(doc, dict):
        return EvidenceFile(file_id, dataset_relative, "", None, "json", [], ["unexpected json shape"])

    records: list[Observation] = []
    notes: list[str] = []
    default_observed_at = parse_iso(doc.get("exported_at")) or parse_iso(doc.get("captured_at"))
    captured_at = parse_iso(doc.get("captured_at")) or parse_iso(doc.get("exported_at"))

    snapshots = doc.get("snapshots")
    if isinstance(snapshots, list):
        collections: list[str] = []
        for snap in snapshots:
            collection = (snap.get("collection") or "").strip()
            if collection not in collections:
                collections.append(collection)
            store = snap.get("data_store")
            snap_captured = parse_iso(snap.get("captured_at")) or captured_at
            for record in snap.get("records") or []:
                obs = parse_structured_record(
                    file_id=file_id,
                    source_path=dataset_relative,
                    source_kind="json",
                    captured_at=snap_captured,
                    collection=collection,
                    data_store=store,
                    record=record,
                    default_observed_at=default_observed_at,
                )
                if obs:
                    records.append(obs)
        notes.append("collections=" + ",".join(c for c in collections if c))
    elif isinstance(doc.get("service_exports"), dict):
        _parse_service_exports(doc, records, notes, captured_at, file_id, dataset_relative)
    else:
        raw_records = doc.get("records") or []
        collection = (doc.get("collection") or "").strip()
        for record in raw_records:
            if record.get("record_type") and record.get("system") and "result" in record:
                obs = parse_lookup_record(
                    file_id=file_id,
                    source_path=dataset_relative,
                    source_kind="json",
                    captured_at=captured_at,
                    record=record,
                    default_observed_at=default_observed_at,
                )
            else:
                obs = parse_structured_record(
                    file_id=file_id,
                    source_path=dataset_relative,
                    source_kind="json",
                    captured_at=captured_at,
                    collection=collection,
                    data_store=(
                        doc.get("data_store")
                        or doc.get("origin")
                        or doc.get("source")
                    ),
                    record=record,
                    default_observed_at=default_observed_at,
                )
            if obs:
                records.append(obs)
        if collection:
            notes.append(f"collection={collection}")
        origin_name = doc.get("source") or doc.get("origin")
        if origin_name:
            notes.append(f"origin={origin_name}")

    return EvidenceFile(
        file_id=file_id,
        path=dataset_relative,
        origin=str(doc.get("origin") or doc.get("source") or ""),
        captured_at=captured_at,
        parser_kind="json",
        records=records,
        notes=notes,
    )


_BLOCK_TAXONOMY = {
    "profile_lookups": "USER_PROFILE",
    "profiles": "ANALYTICS_PROFILE",
    "index_queries": "SEARCH_INDEX_ENTRY",
    "tickets": "SUPPORT_MESSAGE",
    "exports": "USER_EXPORT",
    "connectors": "DATA_FLOW",
    "restore_entries": "BACKUP_ARCHIVE",
    "audit_records": "SECURITY_AUDIT_LOG",
    "documents": "ACCOUNT_TOMBSTONE",
}


def _parse_service_exports(doc: dict, records: list, notes: list, captured_at, file_id: str, dataset_relative: str) -> None:
    """Parse the `service_resource_export_*.json` point-in-time readbacks.

    Layout: top-level `service_exports` -> per-service blocks:
      account_service/profile_lookups (status_code, profile shell),
      analytics_platform/profiles, search_service/index_queries (hits),
      support_platform/tickets, export_service/exports,
      integration_service/connectors, backup_service/restore_entries,
      security_service/audit_records, identity_service/documents.
    """
    from .classify import classify_kind, extract_refs

    seen_blocks: list[str] = []
    for service, blocks in doc["service_exports"].items():
        for block_name, rows in blocks.items():
            default_kind = _BLOCK_TAXONOMY.get(block_name)
            seen_blocks.append(f"{service}/{block_name}({len(rows)})")
            for record in rows:
                resource_id = str(record.get("resource_id") or "").strip()
                if not resource_id:
                    continue
                kind = default_kind or classify_kind(resource_id, record.get("record_type"), block_name)
                shell = record.get("profile")
                hits = record.get("hits")
                attributes = dict(record)
                if isinstance(shell, dict):
                    for key, value in shell.items():
                        attributes.setdefault(key, value)
                if isinstance(hits, dict):
                    documents = hits.get("documents")
                    attributes.setdefault("total", hits.get("total"))
                    if isinstance(documents, list):
                        for entry in documents:
                            if isinstance(entry, dict) and entry.get("resource_id") == resource_id:
                                for key, value in entry.items():
                                    attributes.setdefault(key, value)
                refs = extract_refs(attributes)
                attributes["service_block"] = block_name
                status_code = record.get("status_code")
                present: bool | None = None
                if status_code is not None:
                    present = status_code == 200
                elif block_name == "index_queries":
                    try:
                        present = int(attributes.get("total") or 0) > 0
                    except (TypeError, ValueError):
                        present = None
                else:
                    present = True
                enabled = _bool(record.get("enabled"))
                restore_allowed = _bool(record.get("restore_allowed"))
                ident_fields = ("email", "phone", "email_hash", "full_name", "name",
                                "display_name", "requester_name", "requester_email", "requester_phone")
                any_identifier = any(
                    isinstance(attributes.get(f), str) and attributes.get(f).strip()
                    and attributes.get(f).strip().lower() != "null"
                    for f in ident_fields
                )
                if kind in (
                    "ANALYTICS_PROFILE", "SUPPORT_MESSAGE", "ACCOUNT_TOMBSTONE",
                    "EMAIL_DELIVERY_LOG", "PRODUCT_TELEMETRY",
                ):
                    identifiable, redacted, anonymized = _privacy_flags(kind, any_identifier)
                else:
                    identifiable, redacted, anonymized = None, None, None
                records.append(
                    Observation(
                        file_id=file_id,
                        source_path=dataset_relative,
                        source_kind="json",
                        captured_at=captured_at,
                        system=service,
                        resource_id=resource_id,
                        kind=kind,
                        observed_at=parse_iso(record.get("observed_at")) or captured_at,
                        refs=refs,
                        present=present,
                        enabled=enabled if kind == "DATA_FLOW" else None,
                        restore_allowed=restore_allowed if kind == "BACKUP_ARCHIVE" else None,
                        identifiable=identifiable,
                        redacted=redacted,
                        anonymized=anonymized,
                        retention_until=parse_iso(attributes.get("retention_until")),
                        account_status=attributes.get("account_status"),
                        attributes=attributes,
                    )
                )
    notes.append("blocks=" + ",".join(seen_blocks))
