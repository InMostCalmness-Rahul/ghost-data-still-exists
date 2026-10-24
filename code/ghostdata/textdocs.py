"""Parser for plain-text business documents (e.g. shift handover notes).

Verified shape (customer_account_handover_20261001.txt)::

    Snapshot: <ts>
    - <ts> | system | resource_id | record_type | result | reference-value
"""

from __future__ import annotations

import re
from pathlib import Path

from .models import EvidenceFile, Observation
from .timeutil import parse_iso

_ROW_RE = re.compile(
    r"^-\s+(\d{4}-\d{2}-\d{2}T[\d:]+Z)\s+\|\s+([^|]+?)\s*\|\s+(\S+)\s+\|\s+"
    r"([^|]+?)\s*\|\s+([^|]+?)\s*\|\s*(.*)$"
)
_SNAPSHOT_RE = re.compile(r"^Snapshot:\s*(\S+)")


def parse_txt_document(path: Path, file_id: str, dataset_relative: str, file_origin: str) -> EvidenceFile:
    from .json_records import parse_lookup_record

    captured_at = None
    records: list[Observation] = []
    parsed_rows = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        snap = _SNAPSHOT_RE.match(line)
        if snap and captured_at is None:
            captured_at = parse_iso(snap.group(1))
            continue
        row = _ROW_RE.match(line)
        if not row:
            continue
        ts_raw, system, resource_id, record_type, result, tail = row.groups()
        reference = tail.strip()
        record = {
            "recorded_at": ts_raw,
            "system": system.strip(),
            "resource_id": resource_id,
            "record_type": record_type.strip(),
            "result": result.strip(),
        }
        if reference and not reference.lower().startswith("no "):
            if reference.lower().startswith("user_"):
                record["subject_reference"] = reference
            else:
                record["owner_email"] = reference
        obs = parse_lookup_record(
            file_id=file_id,
            source_path=dataset_relative,
            source_kind="txt",
            captured_at=parse_iso(ts_raw) or captured_at,
            record=record,
            default_observed_at=parse_iso(ts_raw) or captured_at,
        )
        if obs:
            records.append(obs)
            parsed_rows += 1
    return EvidenceFile(
        file_id=file_id,
        path=dataset_relative,
        origin=file_origin,
        captured_at=captured_at,
        parser_kind="txt",
        records=records,
        notes=[f"rows={parsed_rows}"],
    )
