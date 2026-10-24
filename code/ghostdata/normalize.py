"""Identifier normalization helpers.

Normalization keeps matching robust to formatting differences while avoiding
loose/fuzzy matches that could bind decoy records to the wrong person.
"""

from __future__ import annotations


def normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    if not text:
        return None
    return text


def normalize_user_id(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if text == "" or text.lower() == "null":
        return None
    return text.lower()


def normalize_phone(value: str | None) -> str | None:
    """Digits-only key: survives ' +971 50 482 7316' vs '+971504827316'."""
    if value is None:
        return None
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return None
    return digits


def normalize_hash(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    if text == "" or text.lower() == "null":
        return None
    # Accept optional algorithm prefixes like "sha256:<hex>".
    if ":" in text:
        text = text.rsplit(":", 1)[-1]
    return text


def normalize_name(value: str | None) -> str | None:
    if value is None:
        return None
    text = " ".join(value.strip().lower().split())
    if not text:
        return None
    return text


REF_NORMALIZERS = {
    "email": normalize_email,
    "phone": normalize_phone,
    "email_hash": normalize_hash,
    "user_id": normalize_user_id,
    "name": normalize_name,
}
