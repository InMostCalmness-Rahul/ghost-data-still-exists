"""Core dataclasses for the normalized evidence ledger."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Ref:
    """An identifier value observed inside an evidence source.

    role "owner" means the evidence links the identifier to the resource
    (e.g., subject_reference, lookup_key, owner_email). role "content" means
    the value merely appears inside free text (message bodies) and must not by
    itself bind the resource to that person.
    """

    kind: str  # email | phone | email_hash | user_id
    value: str  # normalized value
    role: str  # owner | content
    raw: str = ""


@dataclass
class Observation:
    """One normalized resource observation extracted from an evidence file."""

    file_id: str
    source_path: str  # dataset-relative evidence path
    source_kind: str  # sql | json | log | txt | pdf | png
    captured_at: datetime | None  # file capture time
    system: str | None  # owning system, e.g. account_service
    resource_id: str
    kind: str  # normalized record category, e.g. USER_PROFILE
    observed_at: datetime | None  # record-level observation time
    refs: list[Ref] = field(default_factory=list)
    present: bool | None = None
    enabled: bool | None = None
    restore_allowed: bool | None = None
    identifiable: bool | None = None
    redacted: bool | None = None
    anonymized: bool | None = None
    retention_until: datetime | None = None
    account_status: str | None = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class EvidenceFile:
    """A parsed evidence file and everything extracted from it."""

    file_id: str
    path: str  # path as listed in evidence_files.csv (dataset-relative)
    origin: str
    captured_at: datetime | None
    parser_kind: str  # sql | json | log | txt | pdf | png | unknown
    records: list[Observation] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ActivityEvent:
    """A row of system_activity.csv. `reported_result` is a CLAIM only."""

    activity_id: str
    event_time: datetime | None
    event_type: str
    source_system: str
    target_system: str
    resource_id: str
    reported_result: str
    details: str


IPDF_PNG_NOTE = "multimodal file parsed by M3; no record fields extracted yet"
