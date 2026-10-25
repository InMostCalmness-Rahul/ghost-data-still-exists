"""Remediation planner with exact policy ordering rules.

Ordering:
1. DISABLE_DATA_FLOW / BLOCK_RESTORE (stop active recreation risks)
2. DELETE_RECORD / REDACT_RECORD / ANONYMIZE_RECORD (downstream copies before sources when dependency requires)
3. Verification steps for each remediated item
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from .absence import AbsenceFinding, AbsenceVerdict
from .csvio import load_rules
from .models import Observation
from .state import ResourceState, ResourceStateRecord, UserStateSnapshot


class Phase(Enum):
    FINDING = "FINDING"
    REMEDIATION = "REMEDIATION"
    VERIFICATION = "VERIFICATION"


class Operation(Enum):
    # Findings
    REPORT_REMAINING_RECORD = "REPORT_REMAINING_RECORD"
    REPORT_EXPOSED_PII = "REPORT_EXPOSED_PII"
    REPORT_ACTIVE_DATA_FLOW = "REPORT_ACTIVE_DATA_FLOW"
    REPORT_RESTORE_RISK = "REPORT_RESTORE_RISK"
    # Remediation
    DISABLE_DATA_FLOW = "DISABLE_DATA_FLOW"
    BLOCK_RESTORE = "BLOCK_RESTORE"
    DELETE_RECORD = "DELETE_RECORD"
    REDACT_RECORD = "REDACT_RECORD"
    ANONYMIZE_RECORD = "ANONYMIZE_RECORD"
    # Verification
    VERIFY_RECORD_ABSENT = "VERIFY_RECORD_ABSENT"
    VERIFY_RECORD_PRESENT = "VERIFY_RECORD_PRESENT"
    VERIFY_RECORD_REDACTED = "VERIFY_RECORD_REDACTED"
    VERIFY_RECORD_ANONYMIZED = "VERIFY_RECORD_ANONYMIZED"
    VERIFY_DATA_FLOW_DISABLED = "VERIFY_DATA_FLOW_DISABLED"
    VERIFY_RESTORE_BLOCKED = "VERIFY_RESTORE_BLOCKED"


class State(Enum):
    PRESENT = "PRESENT"
    ABSENT = "ABSENT"
    REDACTED = "REDACTED"
    ANONYMIZED = "ANONYMIZED"
    DISABLED = "DISABLED"
    BLOCKED = "BLOCKED"
    ACTIVE = "ACTIVE"


@dataclass
class Step:
    step_no: int
    phase: Phase
    system_id: str
    resource_id: str
    operation: Operation
    state: State
    evidence_id: str
    rationale: str = ""


def _policy_action(kind: str, attributes: dict[str, Any] | None = None) -> str:
    """Read the required action from the participant-supplied policy."""
    if kind == "DATA_FLOW":
        return "DISABLE"
    if kind == "SUPPORT_MESSAGE" and attributes:
        record_type = str(attributes.get("record_type", "")).upper()
        marker_found = str(attributes.get("marker_found", "")).lower()
        if record_type == "SUPPORT_ATTACHMENT" or marker_found == "false":
            return "DELETE"
    for rule in load_rules():
        if rule.data_category == kind:
            return rule.required_action
    return "UNKNOWN"


# Dependency ordering: downstream before upstream when source feeds downstream
# These are (downstream_kind, upstream_kind) pairs that must be processed downstream first
DEPENDENCY_ORDER = [
    ("SEARCH_INDEX_ENTRY", "USER_PROFILE"),
    ("ANALYTICS_PROFILE", "USER_PROFILE"),
    ("SUPPORT_MESSAGE", "USER_PROFILE"),
    ("SUPPORT_ATTACHMENT", "USER_PROFILE"),
    ("USER_EXPORT", "USER_PROFILE"),
    ("CACHE_ENTRY", "USER_PROFILE"),
]


def _plan_for_resource(
    resource_id: str,
    system_id: str,
    kind: str,
    state_record: ResourceStateRecord,
    absence_finding: AbsenceFinding | None,
    step_counter: int,
) -> tuple[list[Step], int]:
    """Generate steps for a single resource based on its state and policy."""
    steps = []
    action = _policy_action(kind, state_record.attributes)

    # If already compliant (absent/anonymized/redacted as required), only verify
    if action == "DELETE":
        if state_record.state in (ResourceState.ABSENT_VERIFIED, ResourceState.ABSENT_CLAIMED):
            # Already absent - add verification
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RECORD_ABSENT,
                state=State.ABSENT,
                evidence_id=absence_finding.evidence_ids[0] if absence_finding and absence_finding.evidence_ids else "",
                rationale=f"Policy requires DELETE; {absence_finding.reasoning if absence_finding else 'claimed absent'}",
            ))
        elif state_record.state == ResourceState.PRESENT_IDENTIFIABLE:
            # Finding + remediation + verification
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.FINDING,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.REPORT_REMAINING_RECORD,
                state=State.PRESENT,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Policy requires DELETE but record still present with identifiers",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.REMEDIATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.DELETE_RECORD,
                state=State.ABSENT,
                evidence_id="",
                rationale="Policy requires DELETE",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RECORD_ABSENT,
                state=State.ABSENT,
                evidence_id="",
                rationale="Verify deletion complete",
            ))

    elif action == "ANONYMIZE":
        if state_record.state == ResourceState.PRESENT_ANONYMIZED:
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RECORD_ANONYMIZED,
                state=State.ANONYMIZED,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Policy requires ANONYMIZE; already anonymized",
            ))
        elif state_record.state in (ResourceState.PRESENT_IDENTIFIABLE, ResourceState.PRESENT_REDACTED):
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.FINDING,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.REPORT_EXPOSED_PII,
                state=State.PRESENT,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Policy requires ANONYMIZE but record still attributable",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.REMEDIATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.ANONYMIZE_RECORD,
                state=State.ANONYMIZED,
                evidence_id="",
                rationale="Policy requires ANONYMIZE",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RECORD_ANONYMIZED,
                state=State.ANONYMIZED,
                evidence_id="",
                rationale="Verify anonymization complete",
            ))

    elif action == "REDACT":
        if state_record.state == ResourceState.PRESENT_REDACTED:
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RECORD_REDACTED,
                state=State.REDACTED,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Policy requires REDACT; already redacted",
            ))
        elif state_record.state == ResourceState.PRESENT_IDENTIFIABLE:
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.FINDING,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.REPORT_EXPOSED_PII,
                state=State.PRESENT,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Policy requires REDACT but identifiers still exposed",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.REMEDIATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.REDACT_RECORD,
                state=State.REDACTED,
                evidence_id="",
                rationale="Policy requires REDACT",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RECORD_REDACTED,
                state=State.REDACTED,
                evidence_id="",
                rationale="Verify redaction complete",
            ))

    elif action == "RETAIN" and kind != "BACKUP_ARCHIVE":
        # Security audit logs and legal holds must remain
        if state_record.state == ResourceState.PRESENT_IDENTIFIABLE:
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RECORD_PRESENT,
                state=State.PRESENT,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Policy requires RETAIN; verify record still present",
            ))

    elif action == "DISABLE":  # DATA_FLOW
        if state_record.state == ResourceState.DISABLED:
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                state=State.DISABLED,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Data flow already disabled",
            ))
        elif state_record.state == ResourceState.PRESENT_ACTIVE:
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.FINDING,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.REPORT_ACTIVE_DATA_FLOW,
                state=State.ACTIVE,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Active data flow can recreate user data",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.REMEDIATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.DISABLE_DATA_FLOW,
                state=State.DISABLED,
                evidence_id="",
                rationale="Disable data flow to prevent recreation",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                state=State.DISABLED,
                evidence_id="",
                rationale="Verify data flow disabled",
            ))

    elif action == "RETAIN" and kind == "BACKUP_ARCHIVE":  # handled by RETAIN but special
        if state_record.state == ResourceState.PRESENT_RESTORABLE:
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.FINDING,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.REPORT_RESTORE_RISK,
                state=State.ACTIVE,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Backup can restore user data",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.REMEDIATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.BLOCK_RESTORE,
                state=State.BLOCKED,
                evidence_id="",
                rationale="Block restore to prevent data recreation",
            ))
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RESTORE_BLOCKED,
                state=State.BLOCKED,
                evidence_id="",
                rationale="Verify restore blocked",
            ))
        elif state_record.state in (ResourceState.BLOCKED, ResourceState.ABSENT_VERIFIED):
            step_counter += 1
            steps.append(Step(
                step_no=step_counter,
                phase=Phase.VERIFICATION,
                system_id=system_id,
                resource_id=resource_id,
                operation=Operation.VERIFY_RESTORE_BLOCKED,
                state=State.BLOCKED,
                evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                rationale="Backup already blocked from restore",
            ))

    return steps, step_counter


def _topological_sort(resources: list[tuple[str, str, ResourceStateRecord]]) -> list[tuple[str, str, ResourceStateRecord]]:
    """Sort resources so downstream kinds come before upstream kinds."""
    # Create a mapping from resource_id to its index
    resource_map = {r[0]: i for i, r in enumerate(resources)}

    # Build dependency graph
    indegree = {r[0]: 0 for r in resources}
    graph = {r[0]: [] for r in resources}

    for i, (rid, sys, rec) in enumerate(resources):
        for downstream_kind, upstream_kind in DEPENDENCY_ORDER:
            if rec.kind == upstream_kind:
                # Find downstream resources for this user
                for j, (rid2, sys2, rec2) in enumerate(resources):
                    if rec2.kind == downstream_kind:
                        graph[rid2].append(rid)
                        indegree[rid] += 1

    # Kahn's algorithm
    queue = [rid for rid in indegree if indegree[rid] == 0]
    result = []
    while queue:
        rid = queue.pop(0)
        result.append(next(r for r in resources if r[0] == rid))
        for dep in graph[rid]:
            indegree[dep] -= 1
            if indegree[dep] == 0:
                queue.append(dep)

    # Add any remaining (shouldn't happen in valid DAG)
    for r in resources:
        if r not in result:
            result.append(r)

    return result


def plan_remediation(
    user_id: str,
    audit_at: datetime,
    snapshot: UserStateSnapshot,
    absence_findings: dict[str, AbsenceFinding],
    activity_claims: list[Any] = None,
) -> list[Step]:
    """Generate the complete ordered remediation plan."""
    all_steps = []
    step_counter = 0

    # First pass: collect all resources that need action
    resources_needing_action: list[tuple[str, str, ResourceStateRecord]] = []

    for resource_id, state_record in snapshot.resources.items():
        action = _policy_action(state_record.kind, state_record.attributes)
        needs_backup_control = (
            state_record.kind == "BACKUP_ARCHIVE"
            and state_record.state in (ResourceState.PRESENT_RESTORABLE, ResourceState.BLOCKED)
        )
        state_is_compliant = state_record.state in (
            ResourceState.ABSENT_VERIFIED,
            ResourceState.ABSENT_CLAIMED,
            ResourceState.PRESENT_ANONYMIZED,
            ResourceState.PRESENT_REDACTED,
            ResourceState.DISABLED,
            ResourceState.BLOCKED,
        )
        if (
            (action in ("DELETE", "ANONYMIZE", "REDACT", "DISABLE") and not state_is_compliant)
            or needs_backup_control
        ):
            resources_needing_action.append((resource_id, state_record.system_id, state_record))

    # Sort by dependency order
    resources_needing_action = _topological_sort(resources_needing_action)

    # Phase 1: Disable data flows and block restores FIRST
    for resource_id, system_id, state_record in resources_needing_action:
        action = _policy_action(state_record.kind, state_record.attributes)
        if action == "DISABLE":  # DATA_FLOW
            steps, step_counter = _plan_for_resource(
                resource_id, system_id, state_record.kind, state_record,
                absence_findings.get(resource_id), step_counter
            )
            all_steps.extend(steps)

    for resource_id, system_id, state_record in resources_needing_action:
        if state_record.kind == "BACKUP_ARCHIVE" and state_record.state == ResourceState.PRESENT_RESTORABLE:
            steps, step_counter = _plan_for_resource(
                resource_id, system_id, state_record.kind, state_record,
                absence_findings.get(resource_id), step_counter
            )
            all_steps.extend(steps)

    # Phase 2: Process record-level remediation in dependency order
    for resource_id, system_id, state_record in resources_needing_action:
        action = _policy_action(state_record.kind, state_record.attributes)
        if action in ("DELETE", "ANONYMIZE", "REDACT") and state_record.kind != "BACKUP_ARCHIVE":
            steps, step_counter = _plan_for_resource(
                resource_id, system_id, state_record.kind, state_record,
                absence_findings.get(resource_id), step_counter
            )
            all_steps.extend(steps)

    # Phase 3: Verification for retained records (security audit logs, legal holds)
    for resource_id, state_record in snapshot.resources.items():
        action = _policy_action(state_record.kind, state_record.attributes)
        if action == "RETAIN" and state_record.kind in ("SECURITY_AUDIT_LOG", "LEGAL_HOLD_RECORD"):
            if state_record.state == ResourceState.PRESENT_IDENTIFIABLE:
                step_counter += 1
                all_steps.append(Step(
                    step_no=step_counter,
                    phase=Phase.VERIFICATION,
                    system_id=state_record.system_id,
                    resource_id=resource_id,
                    operation=Operation.VERIFY_RECORD_PRESENT,
                    state=State.PRESENT,
                    evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                    rationale=f"Policy requires RETAIN for {state_record.kind}",
                ))

    # Phase 4: Verification for already-compliant resources
    for resource_id, state_record in snapshot.resources.items():
        action = _policy_action(state_record.kind, state_record.attributes)
        # Skip if already handled above
        if action == "DELETE" and state_record.state in (ResourceState.ABSENT_VERIFIED, ResourceState.ABSENT_CLAIMED):
            if not any(s.resource_id == resource_id and s.operation == Operation.VERIFY_RECORD_ABSENT for s in all_steps):
                step_counter += 1
                all_steps.append(Step(
                    step_no=step_counter,
                    phase=Phase.VERIFICATION,
                    system_id=state_record.system_id,
                    resource_id=resource_id,
                    operation=Operation.VERIFY_RECORD_ABSENT,
                    state=State.ABSENT,
                    evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                    rationale="Policy requires DELETE; verify absence",
                ))
        elif action == "ANONYMIZE" and state_record.state == ResourceState.PRESENT_ANONYMIZED:
            if not any(s.resource_id == resource_id and s.operation == Operation.VERIFY_RECORD_ANONYMIZED for s in all_steps):
                step_counter += 1
                all_steps.append(Step(
                    step_no=step_counter,
                    phase=Phase.VERIFICATION,
                    system_id=state_record.system_id,
                    resource_id=resource_id,
                    operation=Operation.VERIFY_RECORD_ANONYMIZED,
                    state=State.ANONYMIZED,
                    evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                    rationale="Policy requires ANONYMIZE; verify anonymization",
                ))
        elif action == "REDACT" and state_record.state == ResourceState.PRESENT_REDACTED:
            if not any(s.resource_id == resource_id and s.operation == Operation.VERIFY_RECORD_REDACTED for s in all_steps):
                step_counter += 1
                all_steps.append(Step(
                    step_no=step_counter,
                    phase=Phase.VERIFICATION,
                    system_id=state_record.system_id,
                    resource_id=resource_id,
                    operation=Operation.VERIFY_RECORD_REDACTED,
                    state=State.REDACTED,
                    evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                    rationale="Policy requires REDACT; verify redaction",
                ))
        elif action == "DISABLE" and state_record.state == ResourceState.DISABLED:
            if not any(s.resource_id == resource_id and s.operation == Operation.VERIFY_DATA_FLOW_DISABLED for s in all_steps):
                step_counter += 1
                all_steps.append(Step(
                    step_no=step_counter,
                    phase=Phase.VERIFICATION,
                    system_id=state_record.system_id,
                    resource_id=resource_id,
                    operation=Operation.VERIFY_DATA_FLOW_DISABLED,
                    state=State.DISABLED,
                    evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                    rationale="Data flow already disabled; verify",
                ))
        elif action == "RETAIN" and state_record.kind == "BACKUP_ARCHIVE" and state_record.state == ResourceState.BLOCKED:
            if not any(
                s.resource_id == resource_id and s.operation == Operation.VERIFY_RESTORE_BLOCKED
                for s in all_steps
            ):
                step_counter += 1
                all_steps.append(Step(
                    step_no=step_counter,
                    phase=Phase.VERIFICATION,
                    system_id=state_record.system_id,
                    resource_id=resource_id,
                    operation=Operation.VERIFY_RESTORE_BLOCKED,
                    state=State.BLOCKED,
                    evidence_id=state_record.evidence_ids[0] if state_record.evidence_ids else "",
                    rationale="Restore access is already blocked",
                ))

    # Emit all findings before remediation and all remediation before
    # verification. Stable sorting preserves dependency order within a phase.
    phase_order = {
        Phase.FINDING: 0,
        Phase.REMEDIATION: 1,
        Phase.VERIFICATION: 2,
    }
    all_steps.sort(key=lambda step: phase_order[step.phase])

    # Renumber steps to be consecutive
    for i, step in enumerate(all_steps):
        step.step_no = i + 1

    return all_steps