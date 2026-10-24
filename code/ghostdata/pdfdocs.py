"""Conservative text extraction for participant-visible PDF evidence."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from .classify import classify_kind, extract_refs
from .models import EvidenceFile, Observation
from .timeutil import parse_iso

RESOURCE_ID = re.compile(r"\b(?:account|support|search|analytics|backup|export|"
                         r"data_flow|audit_record|tombstone|object)_\d+\b", re.I)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
USER_ID = re.compile(r"\buser_\d+\b", re.I)


def _extract_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to extract PDF evidence") from exc

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def parse_pdf_document(
    path: Path,
    file_id: str,
    dataset_relative: str,
    captured_at: datetime | None,
    origin: str,
) -> EvidenceFile:
    """Extract grounded identifiers from a PDF while preserving provenance."""
    try:
        text = _extract_text(path)
    except (OSError, RuntimeError, ValueError) as exc:
        return EvidenceFile(
            file_id=file_id,
            path=dataset_relative,
            origin=origin,
            captured_at=captured_at,
            parser_kind="pdf",
            records=[],
            notes=[f"pdf extraction unavailable: {exc.__class__.__name__}"],
        )

    resource_ids = list(dict.fromkeys(RESOURCE_ID.findall(text)))
    if not resource_ids:
        return EvidenceFile(
            file_id=file_id,
            path=dataset_relative,
            origin=origin,
            captured_at=captured_at,
            parser_kind="pdf",
            records=[],
            notes=["pdf extracted text but no supported resource_id was found"],
        )

    refs = extract_refs({
        "email": EMAIL.search(text).group(0) if EMAIL.search(text) else None,
        "user_id": USER_ID.search(text).group(0) if USER_ID.search(text) else None,
    })
    records = []
    for resource_id in resource_ids:
        kind = classify_kind(resource_id, event=origin)
        if resource_id.lower().startswith("support_") and (
            "attachment" in dataset_relative.lower() or "attachment" in text.lower()
        ):
            kind = "SUPPORT_ATTACHMENT"
        records.append(
            Observation(
                file_id=file_id,
                source_path=dataset_relative,
                source_kind="pdf",
                captured_at=captured_at,
                system=origin.replace("_service", "_service"),
                resource_id=resource_id,
                kind=kind,
                observed_at=captured_at,
                refs=list(refs),
                present=True,
                identifiable=True,
                attributes={
                    "extracted_text": text,
                    "extraction": "pypdf",
                },
            )
        )
    return EvidenceFile(
        file_id=file_id,
        path=dataset_relative,
        origin=origin,
        captured_at=captured_at,
        parser_kind="pdf",
        records=records,
        notes=[f"extracted resource_ids={','.join(resource_ids)}"],
    )


def unreadable_png(
    file_id: str,
    dataset_relative: str,
    captured_at: datetime | None,
    origin: str,
) -> EvidenceFile:
    """Represent screenshot evidence without treating pixels as observed facts."""
    return EvidenceFile(
        file_id=file_id,
        path=dataset_relative,
        origin=origin,
        captured_at=captured_at,
        parser_kind="png",
        records=[
            Observation(
                file_id=file_id,
                source_path=dataset_relative,
                source_kind="png",
                captured_at=captured_at,
                system=None,
                resource_id=f"unreadable_{file_id}",
                kind="UNKNOWN",
                observed_at=captured_at,
                attributes={
                    "evidence_status": "UNREADABLE",
                    "reason": "OCR is not enabled; screenshot contents were not interpreted",
                },
            )
        ],
        notes=["UNREADABLE: OCR is not enabled"],
    )
