"""Unit tests: identity index over current snapshot + audit history."""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from ghostdata.csvio import AuditEvent, IdentityUser
from ghostdata.identities import IdentityIndex


def _user(uid, email, phone="1", eh="h1"):
    return IdentityUser(
        user_id=uid,
        name=f"Person {uid}",
        email=email,
        phone=phone,
        email_hash=eh,
        updated_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
    )


def _audit(aid, uid, t, field_name, old, new):
    return AuditEvent(aid, uid, t, field_name, old, new)


class TestIdentityIndex(unittest.TestCase):
    def setUp(self):
        self.users = [
            _user("user_01", "current.one@gmail.com", "+971504827316", "hash01"),
            _user("user_02", "second.person@yahoo.com", "+34612847593", "hash02"),
            _user("user_10", "n.petrescu@yahoo.com", "+40723481638", "hash10"),
        ]
        self.events = [
            # user_01 changed email: historical address must resolve to user_01
            _audit("audit_100", "user_01", datetime(2026, 2, 1, tzinfo=timezone.utc),
                   "email", "old.history@gmail.com", "current.one@gmail.com"),
            # user_01 changed phone + hash, both shapes must resolve
            _audit("audit_101", "user_01", datetime(2026, 3, 1, tzinfo=timezone.utc),
                   "phone", "+971500000000", "+971504827316"),
            _audit("audit_102", "user_01", datetime(2026, 3, 2, tzinfo=timezone.utc),
                   "email_hash", "oldhash01", "hash01"),
            # user_10 previously used the sample-style historical email
            _audit("audit_110", "user_10", datetime(2026, 1, 15, tzinfo=timezone.utc),
                   "email", "nadia.ionescu@yahoo.com", "n.petrescu@yahoo.com"),
        ]
        self.index = IdentityIndex(self.users, self.events)

    def test_current_email_resolves(self):
        self.assertEqual(self.index.resolve_email("Current.One@GMAIL.com"), {"user_01"})

    def test_historical_email_resolves(self):
        self.assertEqual(self.index.resolve_email("old.history@gmail.com"), {"user_01"})
        self.assertEqual(self.index.resolve_email("nadia.ionescu@yahoo.com"), {"user_10"})

    def test_historical_phone_and_hash_resolves(self):
        self.assertEqual(self.index.resolve_phone("+971 500 00 00 00"), {"user_01"})
        self.assertEqual(self.index.resolve_hash("oldhash01"), {"user_01"})

    def test_unknown_email_empty(self):
        self.assertEqual(self.index.resolve_email("ghost@nowhere.dev"), set())

    def test_ambiguity_shared_old_email(self):
        events = [
            _audit("a1", "user_01", datetime(2026, 1, 1, tzinfo=timezone.utc),
                   "email", "shared.old@gmail.com", "cur1@x.com"),
            _audit("a2", "user_02", datetime(2026, 1, 2, tzinfo=timezone.utc),
                   "email", "shared.old@gmail.com", "cur2@y.com"),
        ]
        index = IdentityIndex(
            [_user("user_01", "cur1@x.com"), _user("user_02", "cur2@y.com")], events
        )
        users = index.resolve_email("shared.old@gmail.com")
        self.assertEqual(users, {"user_01", "user_02"})
        self.assertTrue(any(a.value == "shared.old@gmail.com" for a in index.ambiguities))

    def test_user_id_resolution_unknown(self):
        self.assertEqual(self.index.resolve("user_id", "user_999"), set())
        self.assertEqual(self.index.resolve("user_id", "user_01"), {"user_01"})

    def test_identifiers_basis_recorded(self):
        profile = self.index.profiles["user_01"]
        self.assertIn("old.history@gmail.com", profile.identifiers["email"])
        basis = profile.identifiers["email"]["old.history@gmail.com"]
        self.assertEqual(basis.first_seen_event_id, "audit_100")
        self.assertEqual(basis.source, "audit_log")


if __name__ == "__main__":
    unittest.main()
