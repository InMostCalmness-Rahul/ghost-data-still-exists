"""Unit tests: binding ledger observations to internal user references."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ghostdata.csvio import AuditEvent, IdentityUser
from ghostdata.identities import IdentityIndex
from ghostdata.ledger import EvidenceLedger
from ghostdata.matcher import build_user_evidence_index
from ghostdata.models import ActivityEvent, EvidenceFile, Observation


def _obs(file_id, rid, refs, kind="USER_PROFILE", role="owner"):
    return Observation(
        file_id=file_id,
        source_path="evidence/logs/x.log",
        source_kind="log",
        captured_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        system="account_service",
        resource_id=rid,
        kind=kind,
        observed_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
        refs=refs,
        present=True,
    )


class TestMatcher(unittest.TestCase):
    def _identities(self):
        return IdentityIndex(
            [
                IdentityUser("user_01", "A One", "one@x.com", "1", "h1",
                             datetime(2026, 1, 1, tzinfo=timezone.utc)),
                IdentityUser("user_02", "B Two", "two@x.com", "2", "h2",
                             datetime(2026, 1, 1, tzinfo=timezone.utc)),
            ],
            [],
        )

    def test_owner_ref_binds(self):
        obs = _obs("evidence_01", "account_5", [make(("email", "one@x.com"))])
        ledger = EvidenceLedger()
        ledger.files = [EvidenceFile("evidence_01", "p", "o", obs.captured_at, "log", [obs])]
        index = build_user_evidence_index(ledger, self._identities())
        self.assertEqual(len(index.for_user("user_01")), 1)
        self.assertEqual(index.file_ids_for_user("user_01"), {"evidence_01"})

    def test_content_ref_never_binds(self):
        from ghostdata.classify import make_ref

        obs = _obs("evidence_02", "support_9", [make_ref("email", "stranger@x.com", "content")])
        ledger = EvidenceLedger()
        ledger.files = [EvidenceFile("evidence_02", "p", "o", obs.captured_at, "log", [obs])]
        index = build_user_evidence_index(ledger, self._identities())
        self.assertEqual(index.for_user("user_01"), [])
        self.assertEqual(index.unresolved_owner_refs, 0)

    def test_unresolved_owner_ref_counted(self):
        obs = _obs("evidence_03", "support_9", [make(("email", "nobody@nowhere.io"))])
        ledger = EvidenceLedger()
        ledger.files = [EvidenceFile("evidence_03", "p", "o", obs.captured_at, "log", [obs])]
        index = build_user_evidence_index(ledger, self._identities())
        self.assertEqual(index.unresolved_owner_refs, 1)

    def test_activity_claim_does_not_bind_resource(self):
        obs = _obs("evidence_04", "account_9", [])
        ledger = EvidenceLedger()
        ledger.files = [EvidenceFile("evidence_04", "p", "o", obs.captured_at, "log", [obs])]
        ledger.activity = [
            ActivityEvent(
                "activity_01",
                obs.captured_at,
                "LINK_RESOURCE_IDENTITY",
                "account_service",
                "search_service",
                "account_9",
                "SUCCESS",
                "linked to one@x.com and user_01",
            )
        ]
        index = build_user_evidence_index(ledger, self._identities())
        self.assertEqual(index.for_user("user_01"), [])
        self.assertEqual(index.all_resources_for_user("user_01"), set())

    def test_same_file_colocation_does_not_bind_resource(self):
        owner = _obs("evidence_05", "account_10", [make(("email", "one@x.com"))])
        unrelated = _obs("evidence_05", "search_10", [])
        unrelated.kind = "SEARCH_INDEX_ENTRY"
        ledger = EvidenceLedger()
        ledger.files = [EvidenceFile(
            "evidence_05", "p", "o", owner.captured_at, "log", [owner, unrelated]
        )]
        index = build_user_evidence_index(
            ledger, self._identities(), owner.captured_at
        )
        self.assertEqual(
            {obs.resource_id for obs in index.for_user("user_01")},
            {"account_10"},
        )
        self.assertEqual(index.inferred_resources_for_user("user_01"), set())


def make(pair):
    from ghostdata.classify import make_ref

    return make_ref(*pair, "owner")


if __name__ == "__main__":
    unittest.main()
