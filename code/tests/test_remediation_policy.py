"""Regression tests for policy-backed remediation planning."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ghostdata.absence import AbsenceFinding, AbsenceVerdict
from ghostdata.remediation import (
    Operation,
    Phase,
    State,
    _policy_action,
    plan_remediation,
)
from ghostdata.state import (
    EvidenceStrength,
    ResourceState,
    ResourceStateRecord,
    UserStateSnapshot,
)


UTC = timezone.utc
AUDIT = datetime(2026, 9, 10, tzinfo=UTC)


def record(resource_id, kind, state, system):
    return ResourceStateRecord(
        resource_id=resource_id,
        system_id=system,
        kind=kind,
        state=state,
        strength=EvidenceStrength.STRONG,
        evidence_ids=["evidence_01"],
        user_link_basis="direct",
    )


class TestRemediationPolicy(unittest.TestCase):
    def test_policy_actions_are_loaded_from_dataset(self):
        self.assertEqual(_policy_action("USER_PROFILE"), "DELETE")
        self.assertEqual(_policy_action("SUPPORT_MESSAGE"), "REDACT")
        self.assertEqual(_policy_action("ANALYTICS_PROFILE"), "ANONYMIZE")
        self.assertEqual(_policy_action("DATA_FLOW"), "DISABLE")

    def test_backup_restore_risk_is_planned_and_verified(self):
        snapshot = UserStateSnapshot("user_01", AUDIT)
        snapshot.add_resource(record(
            "backup_01", "BACKUP_ARCHIVE",
            ResourceState.PRESENT_RESTORABLE, "backup_service",
        ))
        finding = AbsenceFinding(
            "backup_01",
            "backup_service",
            "BACKUP_ARCHIVE",
            AbsenceVerdict.PRESENT,
            ["evidence_01"],
            0.9,
            "restore allowed",
        )
        steps = plan_remediation(
            "user_01", AUDIT, snapshot, {"backup_01": finding}, []
        )
        self.assertEqual(
            [step.operation for step in steps],
            [
                Operation.REPORT_RESTORE_RISK,
                Operation.BLOCK_RESTORE,
                Operation.VERIFY_RESTORE_BLOCKED,
            ],
        )
        self.assertEqual(steps[1].evidence_id, "")
        self.assertEqual(steps[2].evidence_id, "")

    def test_disabled_flow_only_needs_verification(self):
        snapshot = UserStateSnapshot("user_01", AUDIT)
        snapshot.add_resource(record(
            "flow_01", "DATA_FLOW", ResourceState.DISABLED,
            "integration_service",
        ))
        steps = plan_remediation("user_01", AUDIT, snapshot, {}, [])
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0].phase, Phase.VERIFICATION)
        self.assertEqual(steps[0].operation, Operation.VERIFY_DATA_FLOW_DISABLED)
        self.assertEqual(steps[0].state, State.DISABLED)


if __name__ == "__main__":
    unittest.main()
