"""Dataset CSV loaders (stdlib csv only)."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime

from .paths import dataset_dir
from .timeutil import parse_iso


@dataclass
class DeletionRequest:
    case_id: str
    email: str
    requested_at: datetime | None
    reported_status: str  # workflow CLAIM, never proof
    reported_at: datetime | None
    audit_at: datetime | None
    request_text: str


@dataclass
class IdentityUser:
    user_id: str
    name: str
    email: str
    phone: str
    email_hash: str
    updated_at: datetime | None
    history: list["AuditEvent"] = field(default_factory=list)


@dataclass
class AuditEvent:
    audit_id: str
    user_id: str
    event_time: datetime | None
    field_name: str
    old_value: str
    new_value: str


@dataclass
class DeletionRule:
    rule_id: str
    data_category: str
    condition: str
    required_action: str


def _read_rows(relative_path: str) -> list[dict[str, str]]:
    path = dataset_dir() / relative_path
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def load_requests(filename: str = "deletion_requests.csv") -> list[DeletionRequest]:
    rows = _read_rows(filename)
    return [
        DeletionRequest(
            case_id=row["case_id"].strip(),
            email=row["email"].strip(),
            requested_at=parse_iso(row["requested_at"]),
            reported_status=row["reported_status"].strip(),
            reported_at=parse_iso(row["reported_at"]),
            audit_at=parse_iso(row["audit_at"]),
            request_text=row["request_text"].strip(),
        )
        for row in rows
    ]


def load_identities(filename: str = "user_identities.csv") -> list[IdentityUser]:
    users = []
    for row in _read_rows(filename):
        users.append(
            IdentityUser(
                user_id=row["user_id"].strip(),
                name=row["name"].strip(),
                email=row["email"].strip(),
                phone=row["phone"].strip(),
                email_hash=row["email_hash"].strip(),
                updated_at=parse_iso(row["updated_at"]),
            )
        )
    return users


def load_audit_log(filename: str = "user_audit_log.csv") -> list[AuditEvent]:
    events = []
    for row in _read_rows(filename):
        events.append(
            AuditEvent(
                audit_id=row["audit_id"].strip(),
                user_id=row["user_id"].strip(),
                event_time=parse_iso(row["event_time"]),
                field_name=row["field_name"].strip(),
                old_value=row["old_value"].strip(),
                new_value=row["new_value"].strip(),
            )
        )
    return events


def load_rules(filename: str = "deletion_rules.csv") -> list[DeletionRule]:
    return [
        DeletionRule(
            rule_id=row["rule_id"].strip(),
            data_category=row["data_category"].strip(),
            condition=row["condition"].strip(),
            required_action=row["required_action"].strip(),
        )
        for row in _read_rows(filename)
    ]


def load_activity(filename: str = "system_activity.csv") -> list["object"]:
    """Load system activity claims; typed as ActivityEvent."""
    from .models import ActivityEvent

    events = []
    for row in _read_rows(filename):
        events.append(
            ActivityEvent(
                activity_id=row["activity_id"].strip(),
                event_time=parse_iso(row["event_time"]),
                event_type=row["event_type"].strip(),
                source_system=row["source_system"].strip(),
                target_system=row["target_system"].strip(),
                resource_id=row["resource_id"].strip(),
                reported_result=row["reported_result"].strip(),
                details=row.get("details", "").strip(),
            )
        )
    return events
