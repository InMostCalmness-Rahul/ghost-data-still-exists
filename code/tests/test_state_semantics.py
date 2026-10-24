"""Regression tests for audit-time state and absence semantics."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ghostdata.absence import AbsenceVerdict, verify_absence
from ghostdata.models import ActivityEvent, Observation
from ghostdata.state import (
    EvidenceStrength,
    ResourceState,
    _strength_from_observation,
    _state_from_observation,
    build_user_state,
)


UTC = timezone.utc
AUDIT = datetime(2026, 9, 10, tzinfo=UTC)


def observation(**kwargs):
    values = {
        "file_id": "evidence_01",
        "source_path": "evidence/logs/x.log",
        "source_kind": "log",
        "captured_at": AUDIT,
        "system": "account_service",
        "resource_id": "account_01",
        "kind": "USER_PROFILE",
        "observed_at": AUDIT,
        "refs": [],
    }
    values.update(kwargs)
    return Observation(**values)


class TestStateSemantics(unittest.TestCase):
    def test_privacy_flags_map_to_distinct_states(self):
        tombstone = Observation(
            file_id="evidence_tombstone",
            source_path="records/tombstone.json",
            source_kind="json",
            captured_at=datetime(2026, 9, 1),
            system="account_service",
            resource_id="tombstone_1",
            kind="ACCOUNT_TOMBSTONE",
            observed_at=datetime(2026, 9, 1),
            present=True,
            identifiable=False,
            redacted=True,
        )
        analytics = Observation(
            file_id="evidence_analytics",
            source_path="records/analytics.json",
            source_kind="json",
            captured_at=datetime(2026, 9, 1),
            system="analytics_platform",
            resource_id="analytics_1",
            kind="ANALYTICS_PROFILE",
            observed_at=datetime(2026, 9, 1),
            present=True,
            identifiable=False,
            anonymized=True,
        )
        exposed = Observation(
            file_id="evidence_exposed",
            source_path="records/tombstone.json",
            source_kind="json",
            captured_at=datetime(2026, 9, 1),
            system="account_service",
            resource_id="tombstone_2",
            kind="ACCOUNT_TOMBSTONE",
            observed_at=datetime(2026, 9, 1),
            present=True,
            identifiable=True,
        )
        unknown = Observation(
            file_id="evidence_unknown",
            source_path="records/account.json",
            source_kind="json",
            captured_at=datetime(2026, 9, 1),
            system="account_service",
            resource_id="account_1",
            kind="USER_PROFILE",
            observed_at=datetime(2026, 9, 1),
            present=True,
        )
        self.assertEqual(_state_from_observation(tombstone), ResourceState.PRESENT_REDACTED)
        self.assertEqual(_state_from_observation(analytics), ResourceState.PRESENT_ANONYMIZED)
        self.assertEqual(_state_from_observation(exposed), ResourceState.PRESENT_IDENTIFIABLE)
        self.assertEqual(_state_from_observation(unknown), ResourceState.UNKNOWN)

    def test_strength_uses_explicit_rank(self):
        self.assertEqual(
            _strength_from_observation(observation(), AUDIT),
            EvidenceStrength.STRONG,
        )
        self.assertGreater(
            EvidenceStrength.STRONG.value != EvidenceStrength.MODERATE.value,
            False,
        )

    def test_activity_success_does_not_create_absence(self):
        event = ActivityEvent(
            "activity_01", AUDIT, "DELETE_RECORD", "account_service",
            "account_service", "account_01", "SUCCESS", "",
        )
        snapshot = build_user_state("user_01", AUDIT, [], [event])
        self.assertEqual(snapshot.resources, {})
        finding = verify_absence(
            "account_01", "account_service", "USER_PROFILE", AUDIT, [], [event]
        )
        self.assertEqual(finding.verdict, AbsenceVerdict.NOT_VERIFIED)

    def test_process_states_are_distinct_from_record_absence(self):
        flow = observation(
            resource_id="flow_01",
            kind="DATA_FLOW",
            system="integration_service",
            enabled=False,
        )
        backup = observation(
            resource_id="backup_01",
            kind="BACKUP_ARCHIVE",
            system="backup_service",
            restore_allowed=False,
        )
        self.assertEqual(_state_from_observation(flow), ResourceState.DISABLED)
        self.assertEqual(_state_from_observation(backup), ResourceState.BLOCKED)

    def test_future_observation_is_ignored(self):
        future = observation(
            captured_at=datetime(2026, 9, 11, tzinfo=UTC),
            observed_at=datetime(2026, 9, 11, tzinfo=UTC),
            present=True,
        )
        snapshot = build_user_state("user_01", AUDIT, [future])
        self.assertEqual(snapshot.resources["account_01"].state, ResourceState.UNKNOWN)


if __name__ == "__main__":
    unittest.main()
