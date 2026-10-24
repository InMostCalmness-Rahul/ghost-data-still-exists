"""Evidence manifest loading and the normalized ledger assembly.

`EvidenceLedger` is the single entry point: it reads evidence_files.csv for
file identity/capture metadata (manifest linkage is metadata only - user-to-
resource bindings always come from inspected file contents), dispatches each
file to its parser, and offers resolution helpers used by validation.
"""

from __future__ import annotations

import csv

from .models import ActivityEvent, EvidenceFile
from .paths import dataset_dir, evidence_dir
from .timeutil import parse_iso


def load_manifest(filename: str = "evidence_files.csv") -> list[EvidenceFile]:
    """Skeleton evidence files from the manifest (no records parsed yet)."""
    path = dataset_dir() / filename
    files: list[EvidenceFile] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            files.append(
                EvidenceFile(
                    file_id=row["file_id"].strip(),
                    path=row["file_path"].strip(),
                    origin=row.get("origin", "").strip(),
                    captured_at=parse_iso(row.get("captured_at")),
                    parser_kind="unknown",
                )
            )
    return files


def _dataset_relative(path_in_dataset: str) -> str:
    return path_in_dataset  # manifest paths are dataset-relative already


def parse_all_evidence() -> tuple[list[EvidenceFile], list[ActivityEvent]]:
    """Parse every manifest file according to its suffix."""
    from .json_records import parse_records_document
    from .logfiles import parse_log_file
    from .sqlsnapshots import parse_sql_snapshot
    from .textdocs import parse_txt_document

    files = load_manifest()
    activity = _load_activity()
    evidence_root_res = evidence_dir().resolve()
    parsed: list[EvidenceFile] = []
    for skeleton in files:
        dataset_relative = _dataset_relative(skeleton.path)
        real_path = dataset_dir() / dataset_relative
        resolved = real_path.resolve()
        try:
            resolved.relative_to(evidence_root_res)
        except ValueError as exc:  # pragma: no cover - defensive
            raise ValueError(f"manifest path escapes dataset/evidence: {skeleton.path}") from exc
        suffix = real_path.suffix.lower()
        common = dict(file_id=skeleton.file_id, dataset_relative=dataset_relative)
        if suffix == ".sql":
            ef = parse_sql_snapshot(real_path, **common)
            ef.origin = skeleton.origin
        elif suffix == ".json":
            ef = parse_records_document(real_path, common["file_id"], dataset_relative)
            ef.origin = skeleton.origin or ef.origin
        elif suffix == ".log":
            ef = parse_log_file(real_path, common["file_id"], dataset_relative)
            ef.origin = skeleton.origin
        elif suffix == ".txt":
            ef = parse_txt_document(real_path, common["file_id"], dataset_relative, skeleton.origin)
        else:
            # PDF / PNG handled by the multimodal stage (M3).
            ef = EvidenceFile(
                file_id=skeleton.file_id,
                path=dataset_relative,
                origin=skeleton.origin,
                captured_at=skeleton.captured_at,
                parser_kind=suffix.lstrip("."),
                records=[],
                notes=["multimodal: facts extracted in a later milestone"],
            )
        # Keep manifest capture time as authoritative when the file itself
        # does not declare one; never let parser output push it later.
        if ef.captured_at is None:
            ef.captured_at = skeleton.captured_at
        parsed.append(ef)
    return parsed, activity


def _load_activity(filename: str = "system_activity.csv") -> list[ActivityEvent]:
    from .csvio import load_activity

    return load_activity(filename)  # type: ignore[return-value]


class EvidenceLedger:
    """Normalized view over all evidence files plus the activity claim stream."""

    def __init__(self) -> None:
        self.files: list[EvidenceFile] = []
        self.activity: list[ActivityEvent] = []
        self._built = False

    def build(self) -> "EvidenceLedger":
        self.files, self.activity = parse_all_evidence()
        self._built = True
        return self

    def file_by_id(self, file_id: str) -> EvidenceFile | None:
        for ef in self.files:
            if ef.file_id == file_id:
                return ef
        return None

    def observations(self):
        for ef in self.files:
            for obs in ef.records:
                yield obs

    def activity_for_resource(self, resource_id: str, cutoff=None):
        """Activity claims for a resource with event_time <= cutoff (if given)."""
        rows = []
        for ev in self.activity:
            if ev.resource_id != resource_id:
                continue
            if cutoff is not None and ev.event_time is not None and ev.event_time > cutoff:
                continue
            rows.append(ev)
        rows.sort(
            key=lambda e: (
                e.event_time.isoformat() if e.event_time else "",
                e.activity_id,
            )
        )
        return rows

    @staticmethod
    def usable_at(cutoff):
        """Close over the audit_at cutoff for time-filtered iteration."""

        def _check(obs) -> bool:
            # Evidence must exist at or before audit_at (AGENTS.md section 6.6).
            file_time = obs.captured_at
            record_time = obs.observed_at or file_time
            if cutoff is not None:
                if file_time is not None and file_time > cutoff:
                    return False
                if record_time is not None and record_time > cutoff:
                    return False
            return True

        return _check
