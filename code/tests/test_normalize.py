"""Unit tests: normalization + time helpers."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ghostdata.normalize import normalize_email, normalize_hash, normalize_phone, normalize_user_id
from ghostdata.timeutil import parse_iso


class TestNormalize(unittest.TestCase):
    def test_email_case_folding(self):
        self.assertEqual(normalize_email("OBI.ADAEZE@ICLOUD.COM"), "obi.adaeze@icloud.com")
        self.assertEqual(normalize_email(None), None)
        self.assertEqual(normalize_email("   "), None)

    def test_phone_digits_only(self):
        self.assertEqual(normalize_phone("+971 50 482 7316"), "971504827316")
        self.assertEqual(normalize_phone("+1 (202) 555-0103"), "12025550103")
        self.assertEqual(normalize_phone(None), None)

    def test_hash(self):
        self.assertEqual(
            normalize_hash("SHA256:ABC"),
            "abc",
            "sha256: prefix must be stripped for comparison",
        )
        self.assertEqual(normalize_hash(None), None)

    def test_user_id(self):
        self.assertEqual(normalize_user_id("USER_042"), "user_042")
        self.assertEqual(normalize_user_id("NULL"), None)


class TestTimeUtil(unittest.TestCase):
    def test_parse_z(self):
        self.assertEqual(
            parse_iso("2026-09-15T11:59:39Z"),
            datetime(2026, 9, 15, 11, 59, 39, tzinfo=timezone.utc),
        )

    def test_parse_offset_and_none(self):
        self.assertIsNotNone(parse_iso("2026-09-15T11:59:39+02:00"))
        self.assertIsNone(parse_iso(""))
        self.assertIsNone(parse_iso("not-a-date"))
        self.assertIsNone(parse_iso(None))


if __name__ == "__main__":
    unittest.main()
