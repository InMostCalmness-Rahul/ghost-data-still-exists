"""Conservative text extraction for participant-visible PDF evidence."""

from __future__ import annotations

import re
import os
import shutil
from datetime import datetime
from pathlib import Path

from .classify import classify_kind, extract_refs
from .models import EvidenceFile, Observation
from .timeutil import parse_iso

RESOURCE_ID = re.compile(r"\b(?:account|support|search|analytics|backup|export|"
                         r"data_flow|audit_record|tombstone|object)_\d+\b", re.I)
EMAIL = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
USER_ID = re.compile(r"\buser_\d+\b", re.I)


def _tesseract_command() -> str | None:
    configured = os.environ.get("TESSERACT_CMD")
    if configured:
        return configured
    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in (
        Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
        Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
    ):
        if candidate.exists():
            return str(candidate)
    return None


def _ocr_language() -> tuple[str, str]:
    requested = os.environ.get("GHOSTDATA_OCR_LANG", "eng")
    try:
        import pytesseract

        available = set(pytesseract.get_languages(config=""))
    except (ImportError, RuntimeError, OSError):
        return requested, requested
    selected = [language for language in requested.split("+") if language in available]
    if not selected:
        selected = ["eng"] if "eng" in available else sorted(available)[:1]
    return requested, "+".join(selected)


def _ocr_image(path: Path) -> tuple[str, str, str]:
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("Pillow and pytesseract are required for OCR") from exc
    command = _tesseract_command()
    if not command:
        raise RuntimeError("tesseract.exe was not found")
    pytesseract.pytesseract.tesseract_cmd = command
    requested, selected = _ocr_language()
    with Image.open(path) as image:
        text = pytesseract.image_to_string(image, lang=selected)
    return text, requested, selected


def _ocr_pdf(path: Path) -> tuple[str, str, str]:
    try:
        import pymupdf as fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required for OCR fallback on PDFs") from exc
    try:
        from PIL import Image
        import pytesseract
    except ImportError as exc:
        raise RuntimeError("Pillow and pytesseract are required for OCR") from exc
    command = _tesseract_command()
    if not command:
        raise RuntimeError("tesseract.exe was not found")
    pytesseract.pytesseract.tesseract_cmd = command
    requested, selected = _ocr_language()
    parts: list[str] = []
    document = fitz.open(str(path))
    try:
        for page in document:
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            with Image.frombytes("RGB", (pixmap.width, pixmap.height), pixmap.samples) as image:
                parts.append(pytesseract.image_to_string(image, lang=selected))
    finally:
        document.close()
    return "\n".join(parts), requested, selected


def _extract_text(path: Path) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("pypdf is required to extract PDF evidence") from exc

    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _observations_from_text(
    text: str,
    file_id: str,
    dataset_relative: str,
    captured_at: datetime | None,
    origin: str,
    source_kind: str,
    extraction: str,
    ocr_languages: tuple[str, str] | None = None,
) -> tuple[list[Observation], list[str]]:
    resource_ids = list(dict.fromkeys(RESOURCE_ID.findall(text)))
    if not resource_ids:
        return [], ["no supported resource_id was found"]
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
        attributes = {
            "extracted_text": text,
            "extraction": extraction,
        }
        if ocr_languages:
            attributes["ocr_language_requested"] = ocr_languages[0]
            attributes["ocr_language_used"] = ocr_languages[1]
        records.append(
            Observation(
                file_id=file_id,
                source_path=dataset_relative,
                source_kind=source_kind,
                captured_at=captured_at,
                system=origin.replace("_service", "_service"),
                resource_id=resource_id,
                kind=kind,
                observed_at=captured_at,
                refs=list(refs),
                present=True,
                identifiable=True,
                attributes=attributes,
            )
        )
    return records, [f"extracted resource_ids={','.join(resource_ids)}"]


def parse_pdf_document(
    path: Path,
    file_id: str,
    dataset_relative: str,
    captured_at: datetime | None,
    origin: str,
) -> EvidenceFile:
    """Extract grounded identifiers from a PDF while preserving provenance."""
    notes: list[str] = []
    try:
        text = _extract_text(path)
        records, notes = _observations_from_text(
            text, file_id, dataset_relative, captured_at, origin, "pdf", "pypdf"
        )
        if records:
            return EvidenceFile(file_id, dataset_relative, origin, captured_at, "pdf", records, notes)
        notes.insert(0, "pypdf produced no supported identifiers; trying Tesseract OCR")
    except (OSError, RuntimeError, ValueError) as exc:
        notes.append(f"pdf text extraction unavailable: {exc.__class__.__name__}")
    try:
        text, requested, selected = _ocr_pdf(path)
        records, ocr_notes = _observations_from_text(
            text, file_id, dataset_relative, captured_at, origin, "pdf", "tesseract", (requested, selected)
        )
        notes.extend(ocr_notes)
        notes.append(f"OCR language requested={requested}; used={selected}")
    except (OSError, RuntimeError, ValueError) as exc:
        notes.append(f"pdf OCR unavailable: {exc.__class__.__name__}")
        records = []
    return EvidenceFile(
        file_id=file_id,
        path=dataset_relative,
        origin=origin,
        captured_at=captured_at,
        parser_kind="pdf",
        records=records,
        notes=notes,
    )


def parse_png_document(
    path: Path,
    file_id: str,
    dataset_relative: str,
    captured_at: datetime | None,
    origin: str,
) -> EvidenceFile:
    """OCR a screenshot while keeping raw OCR non-authoritative."""
    try:
        text, requested, selected = _ocr_image(path)
        records, notes = _observations_from_text(
            text, file_id, dataset_relative, captured_at, origin, "png", "tesseract", (requested, selected)
        )
        notes.insert(0, "OCR completed; identifiers require normal ownership validation")
        notes.append(f"OCR language requested={requested}; used={selected}")
        return EvidenceFile(file_id, dataset_relative, origin, captured_at, "png", records, notes)
    except (OSError, RuntimeError, ValueError) as exc:
        return unreadable_png(file_id, dataset_relative, captured_at, origin, str(exc))


def unreadable_png(
    file_id: str,
    dataset_relative: str,
    captured_at: datetime | None,
    origin: str,
    reason: str = "OCR is unavailable",
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
                    "reason": reason,
                },
            )
        ],
        notes=[f"UNREADABLE: {reason}"],
    )
