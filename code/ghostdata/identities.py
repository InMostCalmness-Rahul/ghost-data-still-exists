"""Current + historical identity resolution (M1).

Builds a stable internal reference (`user_id`) for each person from the
current snapshot (`user_identities.csv`) and the change history
(`user_audit_log.csv`), then exposes reverse lookups from any identifier
(email / phone / email_hash / user_id) to that internal reference.

Every mapping keeps the evidence basis (current value vs audit-log event) so
history-sensitive logic can later check validity windows at `audit_at`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .csvio import AuditEvent, IdentityUser
from .normalize import normalize_email, normalize_hash, normalize_phone, normalize_user_id

_KIND_NAMES = {
    "email": "email",
    "email_hash": "email_hash",
    "phone": "phone",
}


@dataclass
class IdentifierBasis:
    """One known identifier value and where the knowledge comes from."""

    kind: str
    value: str
    first_seen_event_id: str | None  # audit_id that introduced it, if historical
    source: str  # "current" | "audit_log"


@dataclass
class IdentityProfile:
    user_id: str
    name: str
    current_email: str
    current_phone: str
    current_email_hash: str
    updated_at: object | None
    identifiers: dict[str, dict[str, IdentifierBasis]] = field(default_factory=dict)

    def add(self, basis: IdentifierBasis) -> None:
        bucket = self.identifiers.setdefault(basis.kind, {})
        if basis.value not in bucket:
            bucket[basis.value] = basis

    def emails(self) -> list[str]:
        return sorted(self.identifiers.get("email", {}).keys())

    def phones(self) -> list[str]:
        return sorted(self.identifiers.get("phone", {}).keys())

    def hashes(self) -> list[str]:
        return sorted(self.identifiers.get("email_hash", {}).keys())


@dataclass
class Ambiguity:
    value: str
    kind: str
    users: list[str]


class IdentityIndex:
    """Reverse index mapping normalized identifiers to internal user refs."""

    def __init__(
        self,
        users: list[IdentityUser],
        audit_events: list[AuditEvent],
    ) -> None:
        self.profiles: dict[str, IdentityProfile] = {}
        self._reverse: dict[str, dict[str, set[str]]] = {}
        self.ambiguities: list[Ambiguity] = []
        self._build(users, audit_events)

    # ------------------------------------------------------------------ build

    def _build(self, users: list[IdentityUser], audit_events: list[AuditEvent]) -> None:
        events_by_user: dict[str, list[AuditEvent]] = {}
        for event in audit_events:
            uid = normalize_user_id(event.user_id)
            if uid:
                events_by_user.setdefault(uid, []).append(event)

        for user in users:
            uid = normalize_user_id(user.user_id)
            if not uid:
                continue
            profile = IdentityProfile(
                user_id=uid,
                name=user.name,
                current_email=normalize_email(user.email) or "",
                current_phone=normalize_phone(user.phone) or "",
                current_email_hash=normalize_hash(user.email_hash) or "",
                updated_at=user.updated_at,
            )
            if profile.current_email:
                profile.add(IdentifierBasis("email", profile.current_email, None, "current"))
            if profile.current_phone:
                profile.add(IdentifierBasis("phone", profile.current_phone, None, "current"))
            if profile.current_email_hash:
                profile.add(IdentifierBasis("email_hash", profile.current_email_hash, None, "current"))
            self.profiles[uid] = profile
            self._index(uid, profile)

        # Audit-replay resolution: field changes give old/new identifier values.
        for uid in self.profiles:
            history = events_by_user.get(uid, [])
            sorted_events = sorted(
                history,
                key=lambda e: (e.event_time.isoformat() if e.event_time else "", e.audit_id),
            )
            for event in sorted_events:
                kind = _KIND_NAMES.get(event.field_name.strip().lower())
                if kind is None:
                    continue
                for value in (event.old_value, event.new_value):
                    normalized = self._normalize(kind, value)
                    if not normalized:
                        continue
                    basis = IdentifierBasis(kind, normalized, event.audit_id, "audit_log")
                    self.profiles[uid].add(basis)
                    self._index_single(uid, kind, normalized)

        self._detect_ambiguities()

    @staticmethod
    def _normalize(kind: str, value: str) -> str | None:
        if kind == "email":
            return normalize_email(value)
        if kind == "phone":
            return normalize_phone(value)
        if kind == "email_hash":
            return normalize_hash(value)
        return None

    def _index(self, uid: str, profile: IdentityProfile) -> None:
        for kind, values in profile.identifiers.items():
            for value in values:
                self._index_single(uid, kind, value)

    def _index_single(self, uid: str, kind: str, value: str) -> None:
        if not value:
            return
        self._reverse.setdefault(kind, {}).setdefault(value, set()).add(uid)

    def _detect_ambiguities(self) -> None:
        for kind, values in self._reverse.items():
            for value, uids in values.items():
                if len(uids) > 1:
                    self.ambiguities.append(Ambiguity(value=value, kind=kind, users=sorted(uids)))

    # ---------------------------------------------------------------- queries

    def resolve(self, kind: str, value: str | None) -> set[str]:
        if value is None:
            return set()
        normalized = self._normalize(kind, value)
        if not normalized:
            if kind == "user_id":
                uid = normalize_user_id(value)
                return {uid} if uid in self.profiles else set()
            return set()
        return set(self._reverse.get(kind, {}).get(normalized, set()))

    def resolve_email(self, value: str | None) -> set[str]:
        return self.resolve("email", value)

    def resolve_phone(self, value: str | None) -> set[str]:
        return self.resolve("phone", value)

    def resolve_hash(self, value: str | None) -> set[str]:
        return self.resolve("email_hash", value)

    def resolve_ref(self, kind: str, value: str | None) -> set[str]:
        return self.resolve(kind, value)

    def has_user(self, uid: str) -> bool:
        return normalize_user_id(uid) in self.profiles
