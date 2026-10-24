"""Time-aware resource state reconstruction.

Builds the state of each resource at or before a given audit_at timestamp
from direct evidence observations, with confidence scoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .models import Observation


class ResourceState(Enum):
    """Possible states of a resource relative to a user at audit time."""
    PRESENT_IDENTIFIABLE = "present_identifiable"      # Record exists with direct identifiers
    PRESENT_REDACTED = "present_redacted"              # Record exists but identifiers redacted
    PRESENT_ANONYMIZED = "present_anonymized"          # Record exists but anonymized
    PRESENT_ACTIVE = "present_active"                  # Data flow/backup active
    PRESENT_RESTORABLE = "present_restorable"          # Backup can be restored
    DISABLED = "disabled"                              # Data flow is disabled
    BLOCKED = "blocked"                                # Restore is blocked
    ABSENT_VERIFIED = "absent_verified"                # Proven absent at audit time
    ABSENT_CLAIMED = "absent_claimed"                  # Workflow claims absent, but not verified
    UNKNOWN = "unknown"                                # No evidence either way


class EvidenceStrength(Enum):
    STRONG = "strong"       # Direct observation at/before audit_at
    MODERATE = "moderate"   # Observation close to audit_at, or inference from co-located resources
    WEAK = "weak"           # Only workflow claim, or evidence after audit_at
    NONE = "none"           # No evidence


_STRENGTH_RANK = {
    EvidenceStrength.NONE: 0,
    EvidenceStrength.WEAK: 1,
    EvidenceStrength.MODERATE: 2,
    EvidenceStrength.STRONG: 3,
}


@dataclass
class ResourceStateRecord:
    resource_id: str
    system_id: str
    kind: str
    state: ResourceState
    strength: EvidenceStrength
    evidence_ids: list[str] = field(default_factory=list)  # file_ids that support this
    observed_at: datetime | None = None
    confidence: float = 0.0  # 0.0 - 1.0
    attributes: dict[str, Any] = field(default_factory=dict)
    user_link_basis: str = ""  # "direct" | "inferred" | "claim" | "none"


@dataclass
class UserStateSnapshot:
    """Complete state picture for a user at audit_at."""
    user_id: str
    audit_at: datetime
    resources: dict[str, ResourceStateRecord] = field(default_factory=dict)
    active_data_flows: list[str] = field(default_factory=list)  # resource_ids
    restore_risks: list[str] = field(default_factory=list)      # resource_ids
    legal_holds: list[str] = field(default_factory=list)
    retention_requirements: list[str] = field(default_factory=list)

    def add_resource(self, record: ResourceStateRecord) -> None:
        self.resources[record.resource_id] = record
        if record.state == ResourceState.PRESENT_ACTIVE:
            self.active_data_flows.append(record.resource_id)
        if record.state == ResourceState.PRESENT_RESTORABLE:
            self.restore_risks.append(record.resource_id)
        if record.kind == "LEGAL_HOLD_RECORD":
            self.legal_holds.append(record.resource_id)
        if record.kind == "SECURITY_AUDIT_LOG" and record.state in (
            ResourceState.PRESENT_IDENTIFIABLE, ResourceState.PRESENT_REDACTED
        ):
            self.retention_requirements.append(record.resource_id)


def _strength_from_observation(obs: Observation, audit_at: datetime) -> EvidenceStrength:
    """Determine evidence strength based on observation timing and type."""
    if obs.captured_at and obs.captured_at <= audit_at:
        if obs.observed_at and obs.observed_at <= audit_at:
            return EvidenceStrength.STRONG
        return EvidenceStrength.MODERATE
    if obs.observed_at and obs.observed_at <= audit_at:
        return EvidenceStrength.MODERATE
    return EvidenceStrength.WEAK


def _state_from_observation(obs: Observation) -> ResourceState:
    """Derive resource state from a single observation."""
    # Present states
    if obs.kind in ("USER_PROFILE", "SEARCH_INDEX_ENTRY", "CACHE_ENTRY",
                     "SUPPORT_MESSAGE", "SUPPORT_ATTACHMENT", "USER_EXPORT",
                     "EMAIL_DELIVERY_LOG", "ACCOUNT_TOMBSTONE"):
        if obs.present is False:
            return ResourceState.ABSENT_VERIFIED
        if obs.present is True:
            if obs.redacted:
                return ResourceState.PRESENT_REDACTED
            if obs.anonymized:
                return ResourceState.PRESENT_ANONYMIZED
            if obs.identifiable is False and obs.kind in ("ANALYTICS_PROFILE", "PRODUCT_TELEMETRY"):
                return ResourceState.PRESENT_ANONYMIZED
            if obs.identifiable is True:
                return ResourceState.PRESENT_IDENTIFIABLE
            if obs.kind == "USER_EXPORT":
                return ResourceState.PRESENT_IDENTIFIABLE
            return ResourceState.UNKNOWN

    if obs.kind == "ANALYTICS_PROFILE":
        if obs.present is False:
            return ResourceState.ABSENT_VERIFIED
        if obs.anonymized:
            return ResourceState.PRESENT_ANONYMIZED
        if obs.redacted:
            return ResourceState.PRESENT_REDACTED
        if obs.identifiable is False:
            return ResourceState.PRESENT_ANONYMIZED
        if obs.identifiable is True:
            return ResourceState.PRESENT_IDENTIFIABLE
        return ResourceState.UNKNOWN

    if obs.kind == "DATA_FLOW":
        if obs.enabled is False:
            return ResourceState.DISABLED
        if obs.enabled is True:
            return ResourceState.PRESENT_ACTIVE
        return ResourceState.UNKNOWN

    if obs.kind == "BACKUP_ARCHIVE":
        if obs.restore_allowed is True:
            return ResourceState.PRESENT_RESTORABLE
        if obs.restore_allowed is False:
            return ResourceState.BLOCKED
        if obs.present is False:
            return ResourceState.ABSENT_VERIFIED
        return ResourceState.UNKNOWN

    if obs.kind == "SECURITY_AUDIT_LOG":
        if obs.present is False:
            return ResourceState.ABSENT_VERIFIED
        return ResourceState.PRESENT_IDENTIFIABLE  # retained per policy

    if obs.kind == "LEGAL_HOLD_RECORD":
        return ResourceState.PRESENT_IDENTIFIABLE

    return ResourceState.UNKNOWN


def build_user_state(
    user_id: str,
    audit_at: datetime,
    observations: list[Observation],
    activity_claims: list[Any] = None,
) -> UserStateSnapshot:
    """Build a user's state snapshot at audit_at from observations."""
    snapshot = UserStateSnapshot(user_id=user_id, audit_at=audit_at)

    # Group observations by resource
    by_resource: dict[str, list[Observation]] = {}
    for obs in observations:
        by_resource.setdefault(obs.resource_id, []).append(obs)

    for resource_id, obs_list in by_resource.items():
        # Sort by observed_at desc, then captured_at desc (most recent first)
        obs_list.sort(
            key=lambda o: (
                o.observed_at or datetime.min,
                o.captured_at or datetime.min,
            ),
            reverse=True,
        )

        # Find the strongest evidence at/before audit_at
        best_obs = None
        best_strength = EvidenceStrength.NONE
        for obs in obs_list:
            if obs.captured_at and obs.captured_at > audit_at:
                continue
            if obs.observed_at and obs.observed_at > audit_at:
                continue
            strength = _strength_from_observation(obs, audit_at)
            if _STRENGTH_RANK[strength] > _STRENGTH_RANK[best_strength] or (
                strength == best_strength and best_obs is None
            ):
                best_obs = obs
                best_strength = strength

        if best_obs is None:
            # No observation at/before audit_at - check activity claims
            state = ResourceState.UNKNOWN
            strength = EvidenceStrength.NONE
            evidence_ids = []
            user_link = "none"
            obs_for_attrs = None
        else:
            state = _state_from_observation(best_obs)
            strength = best_strength
            evidence_ids = [best_obs.file_id]
            user_link = "direct" if best_obs.refs else "inferred"
            obs_for_attrs = best_obs

        record = ResourceStateRecord(
            resource_id=resource_id,
            system_id=obs_for_attrs.system if obs_for_attrs else "",
            kind=obs_for_attrs.kind if obs_for_attrs else "",
            state=state,
            strength=strength,
            evidence_ids=evidence_ids,
            observed_at=obs_for_attrs.observed_at if obs_for_attrs else None,
            confidence=0.9 if strength == EvidenceStrength.STRONG else 0.6 if strength == EvidenceStrength.MODERATE else 0.3,
            attributes=obs_for_attrs.attributes if obs_for_attrs else {},
            user_link_basis=user_link,
        )
        snapshot.add_resource(record)

    return snapshot