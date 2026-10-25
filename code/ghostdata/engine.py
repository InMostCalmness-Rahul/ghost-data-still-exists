"""Main decision engine orchestrating the deletion audit."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from .csvio import load_activity, load_requests
from .intent import Intent, classify_intent, is_deletion_authorized
from .ledger import EvidenceLedger
from .matcher import build_user_evidence_index, UserEvidenceIndex
from .absence import verify_absence, AbsenceVerdict
from .state import build_user_state, UserStateSnapshot, ResourceState, ResourceStateRecord
from .remediation import plan_remediation, Step, Phase, Operation, State
from .models import Observation, ActivityEvent


# System ID normalization
SYSTEM_ID_MAP = {
    "support_replica": "support_platform",
    "support_platform": "support_platform",
    "account_service": "account_service",
    "search_service": "search_service",
    "analytics_platform": "analytics_platform",
    "export_service": "export_service",
    "integration_service": "integration_service",
    "backup_service": "backup_service",
    "security_service": "security_service",
    "identity_service": "identity_service",
    "email_delivery_service": "email_delivery_service",
    "cache_service": "cache_service",
    "user_export_store": "export_service",
}

def normalize_system_id(system: str) -> str:
    """Normalize system IDs to standard form."""
    return SYSTEM_ID_MAP.get(system, system)


def _observation_candidate(obs: Observation) -> dict[str, Any]:
    """Return provenance-preserving, non-authoritative tool output."""
    return {
        "evidence_id": obs.file_id,
        "source_path": obs.source_path,
        "resource_id": obs.resource_id,
        "system_id": normalize_system_id(obs.system or ""),
        "resource_kind": obs.kind,
        "capture_time": obs.captured_at.isoformat() if obs.captured_at else None,
        "observation_time": obs.observed_at.isoformat() if obs.observed_at else None,
        "identity_refs": [
            {"kind": ref.kind, "value": ref.value, "role": ref.role}
            for ref in obs.refs
        ],
        "attributes": dict(obs.attributes),
        "present": obs.present,
    }


def _within_audit(obs: Observation, audit_at: datetime) -> bool:
    return bool(
        obs.captured_at
        and obs.captured_at <= audit_at
        and (obs.observed_at is None or obs.observed_at <= audit_at)
    )


def _validated_discoveries(
    tool_results: list[dict[str, Any]],
    user_id: str,
    identity_index: Any,
    audit_at: datetime,
    ledger: EvidenceLedger,
) -> list[Observation]:
    """Accept only real, cutoff-valid observations with a unique owner link."""
    by_key = {
        (obs.file_id, obs.resource_id): obs
        for obs in ledger.observations()
        if _within_audit(obs, audit_at)
    }
    accepted: list[Observation] = []
    for entry in tool_results:
        result = entry.get("result", {})
        if not isinstance(result, dict):
            continue
        for candidate in result.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            key = (candidate.get("evidence_id"), candidate.get("resource_id"))
            obs = by_key.get(key)
            if obs is None:
                continue
            owners = set()
            for ref in obs.refs:
                if ref.role == "owner":
                    owners.update(identity_index.resolve_ref(ref.kind, ref.value))
            if owners == {user_id}:
                accepted.append(obs)
    return list({(obs.file_id, obs.resource_id): obs for obs in accepted}.values())


@dataclass
class CaseResult:
    case_id: str
    deletion_status: str  # COMPLETE | INCOMPLETE | NOT_APPLICABLE
    steps: list[Step]
    multimodal_gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _steps_to_json(steps: list[Step]) -> str:
    """Convert steps to the required JSON format."""
    return json.dumps([
        {
            "step_no": s.step_no,
            "phase": s.phase.value,
            "system_id": normalize_system_id(s.system_id),
            "resource_id": s.resource_id,
            "operation": s.operation.value,
            "state": s.state.value,
            "evidence_id": s.evidence_id,
        }
        for s in steps
    ], separators=(',', ':'))


def evaluate_case(
    case: Any,
    ledger: EvidenceLedger,
    user_index: UserEvidenceIndex,
    identity_index: Any,
    runtime_agent: Any | None = None,
) -> CaseResult:
    """Evaluate a single deletion request case."""
    audit_at = case.audit_at
    if not audit_at:
        return CaseResult(
            case_id=case.case_id,
            deletion_status="INCOMPLETE",
            steps=[],
            notes=["missing audit_at"],
        )

    # 1. Intent classification
    authorized, intent_result = is_deletion_authorized(case.request_text)
    if not authorized:
        return CaseResult(
            case_id=case.case_id,
            deletion_status="NOT_APPLICABLE",
            steps=[],
            notes=[f"Intent: {intent_result.intent.value}; {', '.join(intent_result.notes)}"],
        )

    # 2. Resolve user
    users = identity_index.resolve_email(case.email)
    if not users:
        return CaseResult(
            case_id=case.case_id,
            deletion_status="INCOMPLETE",
            steps=[],
            notes=[f"Email {case.email} not resolved to any user"],
        )

    if len(users) != 1:
        return CaseResult(
            case_id=case.case_id,
            deletion_status="INCOMPLETE",
            steps=[],
            notes=[f"Ambiguous email identity: {sorted(users)}"],
        )
    user_id = next(iter(users))

    # 3. Get observations for this user at/before audit_at
    user_obs = user_index.for_user(user_id)
    usable_obs = [
        obs for obs in user_obs
        if obs.captured_at and obs.captured_at <= audit_at
        and (obs.observed_at is None or obs.observed_at <= audit_at)
    ]

    # Runtime assistance may inspect deterministic summaries through bounded
    # tools, but it cannot alter the evidence conclusion or output steps.
    if runtime_agent is not None:
        def execute_investigation(
            action: str,
            args: dict[str, Any],
            _context: dict[str, Any],
        ) -> dict[str, Any]:
            if not isinstance(args, dict):
                raise ValueError("investigation args must be an object")
            query = args.get("query", "")
            if query is not None and not isinstance(query, str):
                raise ValueError("query must be a string")
            requested_resource = args.get("resource_id")
            if requested_resource is not None and not isinstance(requested_resource, str):
                raise ValueError("resource_id must be a string")

            def candidates(predicate) -> list[dict[str, Any]]:
                return [
                    _observation_candidate(obs)
                    for obs in ledger.observations()
                    if _within_audit(obs, audit_at)
                    and predicate(obs)
                ][:20]

            if action == "search_evidence":
                needle = query.strip().lower()
                return {"executed": True, "candidates": candidates(
                    lambda obs: not needle or needle in json.dumps(
                        _observation_candidate(obs), sort_keys=True, default=str
                    ).lower()
                )}
            if action == "resolve_identity":
                return {
                    "executed": True,
                    "resolved_user_ids": [user_id],
                    "candidates": candidates(
                        lambda obs: any(
                            ref.role == "owner"
                            and user_id in identity_index.resolve_ref(ref.kind, ref.value)
                            for ref in obs.refs
                        )
                    )[:20],
                }
            if action == "find_corroboration":
                return {
                    "executed": True,
                    "candidates": candidates(
                        lambda obs: (
                            requested_resource is None
                            or obs.resource_id == requested_resource
                        )
                    ),
                }
            if action == "check_recreate_path":
                resource_ids = {obs.resource_id for obs in usable_obs}
                events = [
                    event for event in ledger.activity
                    if event.resource_id in resource_ids
                    and (event.event_time is None or event.event_time <= audit_at)
                ]
                return {
                    "executed": True,
                    "events": [
                        {
                            "activity_id": event.activity_id,
                            "resource_id": event.resource_id,
                            "event_type": event.event_type,
                            "event_time": event.event_time.isoformat() if event.event_time else None,
                            "reported_result": event.reported_result,
                        }
                        for event in events[:20]
                    ],
                }
            if action == "extract_multimodal":
                return {
                    "executed": True,
                    "candidates": candidates(
                        lambda obs: obs.source_kind in ("pdf", "png")
                    ),
                }
            raise ValueError(f"unsupported investigation action: {action}")

        runtime_agent.investigate(
            case,
            {
                "request_text": case.request_text,
                "resolved_user": True,
                "known_observation_count": len(usable_obs),
                "known_resource_count": len({obs.resource_id for obs in usable_obs}),
            },
            tool_executor=execute_investigation,
        )
        discovered = _validated_discoveries(
            runtime_agent.last_tool_results,
            user_id,
            identity_index,
            audit_at,
            ledger,
        )
        usable_obs = list({
            (obs.file_id, obs.resource_id): obs for obs in [*usable_obs, *discovered]
        }.values())

    # 4. Build state snapshot
    snapshot = build_user_state(user_id, audit_at, usable_obs, ledger.activity)

    # 5. Verify absence for all relevant resources
    absence_findings = {}
    for resource_id, state_record in snapshot.resources.items():
        finding = verify_absence(
            resource_id=resource_id,
            system_id=state_record.system_id,
            kind=state_record.kind,
            audit_at=audit_at,
            observations=usable_obs,
            activity_claims=ledger.activity,
            user_link_basis=state_record.user_link_basis,
        )
        absence_findings[resource_id] = finding

    # 6. Plan remediation
    steps = plan_remediation(user_id, audit_at, snapshot, absence_findings, ledger.activity)

    # 7. Determine overall status
    has_findings = any(s.phase == Phase.FINDING for s in steps)
    has_remediation = any(s.phase == Phase.REMEDIATION for s in steps)

    # Check for multimodal gaps
    multimodal_gaps = []
    for obs in usable_obs:
        if obs.source_kind in ("pdf", "png"):
            multimodal_gaps.append(f"{obs.resource_id} ({obs.file_id})")

    for finding in absence_findings.values():
        if finding.requires_multimodal:
            multimodal_gaps.append(f"{finding.resource_id} absence verification requires {finding.evidence_ids}")

    has_unknown_state = any(
        record.state.name == "UNKNOWN" for record in snapshot.resources.values()
    )
    if not has_findings and not has_remediation and not has_unknown_state:
        deletion_status = "COMPLETE"
    else:
        deletion_status = "INCOMPLETE"

    return CaseResult(
        case_id=case.case_id,
        deletion_status=deletion_status,
        steps=steps,
        multimodal_gaps=multimodal_gaps,
        notes=[f"User: {user_id}; Intent: {intent_result.intent.value}"],
    )


def run_evaluation(
    requests_file: str = "sample_deletion_requests.csv",
    output_file: str = "output.csv",
) -> list[CaseResult]:
    """Run evaluation on all requests in the file."""
    ledger = EvidenceLedger().build()
    from .csvio import load_identities, load_audit_log
    identities = load_identities()
    audit_log = load_audit_log()
    from .identities import IdentityIndex
    identity_index = IdentityIndex(identities, audit_log)

    requests = load_requests(requests_file)
    results = []

    for case in requests:
        user_index = build_user_evidence_index(ledger, identity_index, case.audit_at)
        result = evaluate_case(case, ledger, user_index, identity_index)
        results.append(result)

    from evaluation.validator import write_results

    write_results(output_file, results, expected_case_ids=[case.case_id for case in requests])

    return results