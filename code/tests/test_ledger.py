"""Unit tests: evidence ledger assembly and audit_at cutoff logic."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ghostdata.ledger import EvidenceLedger
from ghostdata.models import Observation


def _obs(captured_at, observed_at=None):
    return Observation(
        file_id="evidence_x",
        source_path="evidence/logs/x.log",
        source_kind="log",
        captured_at=captured_at,
        system="account_service",
        resource_id="account_1",
        kind="USER_PROFILE",
        observed_at=observed_at,
    )


class TestCutoff(unittest.TestCase):
    def test_multimodal_evidence_is_parsed_explicitly(self):
        ledger = EvidenceLedger().build()
        pdf = ledger.file_by_id("evidence_58")
        self.assertIsNotNone(pdf)
        self.assertEqual(pdf.parser_kind, "pdf")
        support = next(obs for obs in pdf.records if obs.resource_id == "support_001")
        self.assertEqual(support.kind, "SUPPORT_ATTACHMENT")
        self.assertTrue(support.identifiable)

        png = ledger.file_by_id("evidence_23")
        self.assertIsNotNone(png)
        self.assertEqual(png.parser_kind, "png")
        self.assertEqual(png.records[0].attributes["evidence_status"], "UNREADABLE")

    def test_censored_after_audit_at(self):
        audit_at = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
        check = EvidenceLedger.usable_at(audit_at)
        self.assertTrue(check(_obs(datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc))))
        self.assertTrue(check(_obs(audit_at)), "captured exactly at audit_at is admissible")
        self.assertFalse(check(_obs(datetime(2026, 9, 16, 0, 0, tzinfo=timezone.utc))))

    def test_later_readback_in_older_file_disqualified(self):
        # File captured 2026-09-10, but its readback observation is stamped
        # 2026-09-20: a case audited on 09-15 must not use that reading.
        audit_at = datetime(2026, 9, 15, 12, 0, tzinfo=timezone.utc)
        check = EvidenceLedger.usable_at(audit_at)
        self.assertFalse(
            check(_obs(datetime(2026, 9, 10, 12, 0, tzinfo=timezone.utc),
                       datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)))
        )

    def test_no_cutoff_admits_everything(self):
        check = EvidenceLedger.usable_at(None)
        self.assertTrue(check(_obs(None)))
        self.assertTrue(check(_obs(datetime(2026, 1, 1, tzinfo=timezone.utc))))


if __name__ == "__main__":
    unittest.main()
