"""Shared evidence helpers: record-kind classification and identifier refs.

Classification is general: explicit record_type labels win, then event-name
hints, then resource-id prefixes. No case ids or user ids are hardcoded.
"""

from __future__ import annotations

import re

from .models import Ref
from .normalize import normalize_email, normalize_hash, normalize_phone, normalize_user_id

# Resource-id prefix -> record category. Prefixes are system-wide naming
# conventions observed across every evidence source, not case-specific facts.
PREFIX_KIND = {
    "account_": "USER_PROFILE",
    "search_": "SEARCH_INDEX_ENTRY",
    "cache_": "CACHE_ENTRY",
    "analytics_": "ANALYTICS_PROFILE",
    "support_": "SUPPORT_MESSAGE",
    "export_": "USER_EXPORT",
    "data_flow_": "DATA_FLOW",
    "backup_": "BACKUP_ARCHIVE",
    "audit_record_": "SECURITY_AUDIT_LOG",
    "tombstone_": "ACCOUNT_TOMBSTONE",
    "email_delivery_": "EMAIL_DELIVERY_LOG",
    "legal_hold_": "LEGAL_HOLD_RECORD",
}


def classify_kind(resource_id: str, record_type: str | None = None, event: str | None = None) -> str:
    """Choose the normalized record category for an observation."""
    if record_type:
        rt = record_type.strip().upper()
        if rt in PREFIX_KIND.values():
            return rt
        # lookup files sometimes use other labels; fall through to prefix map
    rid = (resource_id or "").strip().lower()
    for prefix, kind in PREFIX_KIND.items():
        if rid.startswith(prefix):
            if prefix == "support_" and event and "attachment" in event.lower():
                return "SUPPORT_ATTACHMENT"
            return kind
    if event:
        lowered = event.lower()
        if "attachment" in lowered:
            return "SUPPORT_ATTACHMENT"
        if "message" in lowered or "ticket" in lowered:
            return "SUPPORT_MESSAGE"
        if "connector" in lowered or "data_flow" in lowered:
            return "DATA_FLOW"
        if "restore" in lowered or "backup" in lowered:
            return "BACKUP_ARCHIVE"
        if "tombstone" in lowered:
            return "ACCOUNT_TOMBSTONE"
    return "UNKNOWN"


# Fields that identify the person the resource belongs to.
OWNER_REF_FIELDS = {
    "user_id": "user_id",
    "customer_reference": "user_id",
    "subject_reference": "user_id",
    "subject_ref": "user_id",
    "lookup_value": "email",
    "lookup_key": "email",
    "match_key": "email",
    "subject_key": "email",
    "scan_key": "email",
    "correlation_key": "email",
    "owner_email": "email",
    "requester_email": "email",
    "uploaded_by": "email",
    "customer_email": "email",
    "email": "email",
    "full_name": "name",
    "name": "name",
    "display_name": "name",
    "requester_name": "name",
    "phone": "phone",
    "requester_phone": "phone",
    "owner_phone": "phone",
    "email_hash": "email_hash",
    "matched_value": "email",
}

# Free-text fields whose contents must only count as role="content" refs
# (a message may mention another person's email - decoy protection).
CONTENT_FIELDS = {"message_text", "message_excerpt", "details", "file_name", "object_key", "archive_path", "archive_key"}

EMAIL_IN_TEXT = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")


def _kind_of(field_name: str) -> str | None:
    return OWNER_REF_FIELDS.get(field_name)


def reidentify_value(kind: str, value: str) -> str:
    """Fix value-shape mismatches between field name and value format.

    - a value like 'user_524' recorded under an email-named field (e.g.
      customer_email) is a user reference, not an email;
    - an email-shaped value recorded under user-reference-named fields (e.g.
      subject_reference in backup catalogs) is an email, not user_id.
    """
    if kind == "email" and value.lower().startswith("user_") and not EMAIL_IN_TEXT.fullmatch(value):
        return "user_id"
    if kind == "user_id" and EMAIL_IN_TEXT.fullmatch(value):
        return "email"
    return kind


def make_ref(kind: str, value: str, role: str = "owner") -> Ref:
    raw = value
    return Ref(kind=kind, value=normalize(kind, value), role=role, raw=raw)


def normalize(kind: str, value: str) -> str:
    if kind == "email":
        return normalize_email(value) or ""
    if kind == "phone":
        return normalize_phone(value) or ""
    if kind == "email_hash":
        return normalize_hash(value) or ""
    if kind == "user_id":
        return normalize_user_id(value) or ""
    return value.strip().lower()


def owner_refs_from_record(record: dict) -> list[Ref]:
    """Owner-role identifier refs from recognized identity field names.

    Placeholder values (e.g. "no direct identifier") are skipped outright.
    """
    refs: list[Ref] = []
    seen: set[tuple[str, str]] = set()
    for key, kind in OWNER_REF_FIELDS.items():
        value = record.get(key)
        if value is None:
            continue
        text = value.strip() if isinstance(value, str) else str(value).strip()
        if not text or text.lower() == "null":
            continue
        if len(text) < 4 or text.lower().startswith("no "):
            continue
        kind2 = reidentify_value(kind, text)
        ref = make_ref(kind2, text, "owner")
        if ref.value and (ref.kind, ref.value) not in seen:
            seen.add((ref.kind, ref.value))
            refs.append(ref)
    return refs


def extract_refs(record: dict, *, as_content: bool = False) -> list[Ref]:
    """Extract identifier refs from a record dict.

    Recognized identity field names yield owner-role refs; free-text fields
    yield content-role refs; unknown fields are ignored (never guessed).
    """
    refs: list[Ref] = []
    seen: set[tuple[str, str, str]] = set()
    default_role = "content" if as_content else "owner"
    for key, value in record.items():
        if value is None:
            continue
        text = value if isinstance(value, str) else str(value)
        text = text.strip()
        if not text or text.lower() == "null":
            continue
        key_l = key.strip().lower()
        if key_l in CONTENT_FIELDS:
            if key_l in ("message_text", "message_excerpt", "details"):
                for match in EMAIL_IN_TEXT.findall(text):
                    ref = make_ref("email", match, "content")
                    tag = (ref.kind, ref.value, ref.role)
                    if tag not in seen and ref.value:
                        seen.add(tag)
                        refs.append(ref)
            continue
        ref_kind = _kind_of(key_l)
        if ref_kind is None:
            continue
        ref_kind = reidentify_value(ref_kind, text)
        ref = make_ref(ref_kind, text, default_role)
        tag = (ref.kind, ref.value, ref.role)
        if tag not in seen and ref.value:
            seen.add(tag)
            refs.append(ref)
    return refs
