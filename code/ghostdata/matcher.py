"""Binds ledger observations to internal user references (M1.5 + M2).

Owner-role identifier refs are resolved through the IdentityIndex; content
-role refs (e.g., an email merely quoted inside a message body) are carried
but never used to attribute a resource. Name values are recorded but do not
bind resources either - name collisions are a known decoy vector.

M2 enhancement: also use LINK_RESOURCE_IDENTITY and DELETE_RECORD activity
claims to attribute resources that lack direct identifiers in evidence.
M2 enhancement: infer user binding from co-located resources in same evidence file.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .identities import IdentityIndex
from .ledger import EvidenceLedger
from .models import Observation, ActivityEvent


@dataclass
class UserEvidenceIndex:
    by_user: dict[str, list[Observation]] = field(default_factory=dict)
    ambiguous_bindings: list[tuple[str, Observation, set[str]]] = field(default_factory=list)
    unresolved_owner_refs: int = 0
    # Activity claims are retained only for diagnostics; they do not bind
    # resources to users.
    activity_linked_resources: dict[str, set[str]] = field(default_factory=dict)  # user_id -> {resource_ids}
    # Co-location is retained only as a diagnostic lead; it does not bind
    # resources to users.
    inferred_resources: dict[str, set[str]] = field(default_factory=dict)  # user_id -> {resource_ids}
    unresolved_activity_candidates: dict[str, set[str]] = field(default_factory=dict)

    def for_user(self, user_id: str) -> list[Observation]:
        return self.by_user.get(user_id, [])

    def file_ids_for_user(self, user_id: str) -> set[str]:
        return {obs.file_id for obs in self.for_user(user_id)}

    def activity_resources_for_user(self, user_id: str) -> set[str]:
        return self.activity_linked_resources.get(user_id, set())

    def inferred_resources_for_user(self, user_id: str) -> set[str]:
        return self.inferred_resources.get(user_id, set())

    def activity_candidates_for_user(self, user_id: str) -> set[str]:
        """Return activity candidates only when an explicit identity link resolves."""
        return self.activity_linked_resources.get(user_id, set())

    def all_resources_for_user(self, user_id: str) -> set[str]:
        """Resource IDs proven associated with a user through evidence."""
        direct = {obs.resource_id for obs in self.for_user(user_id)}
        inferred = self.inferred_resources_for_user(user_id)
        return direct | inferred


def _extract_user_from_link_claim(claim: ActivityEvent) -> str | None:
    """Extract user_id or email from LINK_RESOURCE_IDENTITY claim details."""
    import re
    details = claim.details
    # Pattern: "linked to email@domain and user_XX"
    m = re.search(r'to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s+and\s+(user_\d+)', details)
    if m:
        return m.group(2)  # return user_id
    m = re.search(r'to\s+(user_\d+)', details)
    if m:
        return m.group(1)
    return None


def _extract_email_from_link_claim(claim: ActivityEvent) -> str | None:
    """Extract email from LINK_RESOURCE_IDENTITY claim details."""
    import re
    details = claim.details
    m = re.search(r'to\s+([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', details)
    if m:
        return m.group(1)
    return None


def _activity_candidates(
    activity: list[ActivityEvent],
    identities: IdentityIndex,
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """Extract diagnostic candidates from explicit identity-link claims.

    DELETE_RECORD rows are never sufficient. LINK_RESOURCE_IDENTITY claims are
    still only candidates and must be corroborated by evidence before use.
    """
    candidates: dict[str, set[str]] = {}
    unresolved: dict[str, set[str]] = {}
    for claim in activity:
        if claim.event_type != "LINK_RESOURCE_IDENTITY":
            continue
        users = set()
        user_id = _extract_user_from_link_claim(claim)
        if user_id:
            users.update(identities.resolve_ref("user_id", user_id))
        email = _extract_email_from_link_claim(claim)
        if email:
            users.update(identities.resolve_ref("email", email))
        if users:
            for uid in users:
                candidates.setdefault(uid, set()).add(claim.resource_id)
        else:
            unresolved.setdefault(claim.resource_id, set()).add(claim.resource_id)
    return candidates, unresolved


def _infer_user_from_colocation(
    ledger: EvidenceLedger,
    identities: IdentityIndex,
    audit_at: datetime,
) -> dict[str, set[str]]:
    """
    Infer user->resource bindings from co-location in evidence files.
    Only infer for resources in the SAME SYSTEM as directly-linked resources.
    """
    inferred: dict[str, set[str]] = {}

    # 1. Group observations by file
    by_file: dict[str, list[Observation]] = {}
    for obs in ledger.observations():
        if obs.captured_at and obs.captured_at <= audit_at:
            by_file.setdefault(obs.file_id, []).append(obs)

    # 2. For each file, find users with direct links and their systems
    for file_id, obs_list in by_file.items():
        # Map system -> users directly linked in this file
        system_to_users: dict[str, set[str]] = {}
        unlinked_by_system: dict[str, list[Observation]] = {}

        for obs in obs_list:
            direct_users = set()
            for ref in obs.refs:
                if ref.role == "owner":
                    resolved = identities.resolve_ref(ref.kind, ref.value)
                    direct_users.update(resolved)

            if direct_users:
                system_to_users.setdefault(obs.system, set()).update(direct_users)
            else:
                unlinked_by_system.setdefault(obs.system, []).append(obs)

        # Infer: unlinked resources in SAME SYSTEM as directly-linked resources
        for system, users in system_to_users.items():
            if system in unlinked_by_system:
                for obs in unlinked_by_system[system]:
                    for uid in users:
                        inferred.setdefault(uid, set()).add(obs.resource_id)

    return inferred


def build_user_evidence_index(
    ledger: EvidenceLedger,
    identities: IdentityIndex,
    audit_at: datetime | None = None,
) -> UserEvidenceIndex:
    index = UserEvidenceIndex()

    # 1. Bind via owner-role refs in evidence (existing logic)
    for obs in ledger.observations():
        bound: set[str] = set()
        for ref in obs.refs:
            if ref.role != "owner":
                continue
            resolved = identities.resolve_ref(ref.kind, ref.value)
            if not resolved:
                index.unresolved_owner_refs += 1
                continue
            if len(resolved) > 1:
                index.ambiguous_bindings.append((ref.value, obs, resolved))
            bound |= resolved
        for uid in bound:
            index.by_user.setdefault(uid, []).append(obs)

    for bucket in index.by_user.values():
        bucket.sort(key=lambda o: (o.file_id, o.resource_id))

    candidates, unresolved = _activity_candidates(ledger.activity, identities)
    index.activity_linked_resources = candidates
    index.unresolved_activity_candidates = unresolved

    return index