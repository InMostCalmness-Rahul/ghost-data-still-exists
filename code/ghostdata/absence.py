"""Explicit absence verification.

Distinguishes verified absence (sufficient evidence of non-existence)
from unverified absence (no evidence found, or only workflow claims).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

from .models import Observation


class AbsenceVerdict(Enum):
    VERIFIED_ABSENT = "verified_absent"          # Direct evidence of absence at audit_at
    VERIFIED_ABSENT_INFERRED = "verified_absent_inferred"  # Inferred from authoritative snapshot
    CLAIMED_ABSENT = "claimed_absent"            # Only workflow claim, no direct evidence
    NOT_VERIFIED = "not_verified"                # No evidence either way
    PRESENT = "present"                          # Evidence shows presence


@dataclass
class AbsenceFinding:
    resource_id: str
    system_id: str
    kind: str
    verdict: AbsenceVerdict
    evidence_ids: list[str]
    confidence: float
    reasoning: str
    requires_multimodal: bool = False


# Store configurations: which evidence files constitute authoritative snapshots
# for each system/kind. These are determined from the dataset structure.
AUTHORITATIVE_SNAPSHOTS = {
    # system -> {kind -> [evidence_file_ids that are authoritative snapshots]}
    "account_service": {
        "USER_PROFILE": ["evidence_54", "evidence_93", "evidence_05", "evidence_90"],
    },
    "search_service": {
        "SEARCH_INDEX_ENTRY": ["evidence_57", "evidence_05"],
    },
    "analytics_platform": {
        "ANALYTICS_PROFILE": ["evidence_93", "evidence_56"],
    },
    "support_platform": {
        "SUPPORT_MESSAGE": ["evidence_61", "evidence_01"],
        "SUPPORT_ATTACHMENT": ["evidence_58"],  # PDF - multimodal
    },
    "export_service": {
        "USER_EXPORT": ["evidence_59"],
    },
    "backup_service": {
        "BACKUP_ARCHIVE": ["evidence_93", "evidence_92"],
    },
    "integration_service": {
        "DATA_FLOW": ["evidence_92", "evidence_01"],
    },
    "security_service": {
        "SECURITY_AUDIT_LOG": ["evidence_92", "evidence_94", "evidence_01"],
    },
    "identity_service": {
        "ACCOUNT_TOMBSTONE": ["evidence_51"],
    },
}


def _is_authoritative_snapshot(file_id: str, system_id: str, kind: str) -> bool:
    """Check if a file is an authoritative snapshot for the given system/kind."""
    return file_id in AUTHORITATIVE_SNAPSHOTS.get(system_id, {}).get(kind, [])


def verify_absence(
    resource_id: str,
    system_id: str,
    kind: str,
    audit_at: datetime,
    observations: list[Observation],
    activity_claims: list[Any] = None,
    user_link_basis: str = "none",
) -> AbsenceFinding:
    """
    Determine if a resource is verified absent at audit_at.

    Rules:
    1. Direct observation of absence (present=False) at/before audit_at = VERIFIED_ABSENT
    2. Authoritative snapshot at/before audit_at that doesn't contain the resource = VERIFIED_ABSENT_INFERRED
    3. Only workflow claim of deletion = CLAIMED_ABSENT
    4. No evidence = NOT_VERIFIED
    5. Evidence shows present = PRESENT
    """
    # Filter observations for this resource at/before audit_at
    relevant_obs = [
        obs for obs in observations
        if obs.resource_id == resource_id
        and obs.system == system_id
        and obs.kind == kind
        and obs.captured_at
        and obs.captured_at <= audit_at
    ]

    if not relevant_obs:
        return AbsenceFinding(
            resource_id=resource_id,
            system_id=system_id,
            kind=kind,
            verdict=AbsenceVerdict.NOT_VERIFIED,
            evidence_ids=[],
            confidence=0.0,
            reasoning="No observation found at/before audit_at; no successful delete claim",
        )

    # Sort by captured_at desc (most recent snapshot first)
    relevant_obs.sort(key=lambda o: o.captured_at, reverse=True)

    # Check for direct absence observation
    for obs in relevant_obs:
        if obs.present is False:
            # Check if this is an authoritative snapshot
            is_authoritative = _is_authoritative_snapshot(obs.file_id, system_id, kind)
            if is_authoritative:
                return AbsenceFinding(
                    resource_id=resource_id,
                    system_id=system_id,
                    kind=kind,
                    verdict=AbsenceVerdict.VERIFIED_ABSENT_INFERRED,
                    evidence_ids=[obs.file_id],
                    confidence=0.85,
                    reasoning=f"Authoritative snapshot {obs.file_id} shows resource absent (present=False)",
                )
            else:
                return AbsenceFinding(
                    resource_id=resource_id,
                    system_id=system_id,
                    kind=kind,
                    verdict=AbsenceVerdict.VERIFIED_ABSENT,
                    evidence_ids=[obs.file_id],
                    confidence=0.75,
                    reasoning=f"Observation {obs.file_id} shows resource absent (present=False)",
                )

    # Check for present observations
    for obs in relevant_obs:
        if obs.present is True:
            return AbsenceFinding(
                resource_id=resource_id,
                system_id=system_id,
                kind=kind,
                verdict=AbsenceVerdict.PRESENT,
                evidence_ids=[obs.file_id],
                confidence=0.9,
                reasoning=f"Observation {obs.file_id} shows resource present",
            )

    # No definitive evidence either way
    return AbsenceFinding(
        resource_id=resource_id,
        system_id=system_id,
        kind=kind,
        verdict=AbsenceVerdict.NOT_VERIFIED,
        evidence_ids=[obs.file_id for obs in relevant_obs],
        confidence=0.3,
        reasoning="Observations exist but none show definitive absence or presence",
        requires_multimodal=any(obs.source_kind in ("pdf", "png") for obs in relevant_obs),
    )