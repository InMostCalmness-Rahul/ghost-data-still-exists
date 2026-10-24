"""Unit tests: record-kind classification and identifier ref extraction."""

from __future__ import annotations

import unittest

from ghostdata.classify import (
    extract_refs,
    make_ref,
    owner_refs_from_record,
    reidentify_value,
)
from ghostdata.intent import Intent, classify_intent, is_deletion_authorized


class TestClassify(unittest.TestCase):
    def test_prefix_kind_map(self):
        from ghostdata.classify import classify_kind

        self.assertEqual(classify_kind("account_005"), "USER_PROFILE")
        self.assertEqual(classify_kind("search_1308"), "SEARCH_INDEX_ENTRY")
        self.assertEqual(classify_kind("analytics_9246"), "ANALYTICS_PROFILE")
        self.assertEqual(classify_kind("data_flow_4890"), "DATA_FLOW")
        self.assertEqual(classify_kind("backup_7809"), "BACKUP_ARCHIVE")
        self.assertEqual(classify_kind("audit_record_2016"), "SECURITY_AUDIT_LOG")
        self.assertEqual(classify_kind("tombstone_9178"), "ACCOUNT_TOMBSTONE")

    def test_attachment_event_override(self):
        from ghostdata.classify import classify_kind

        self.assertEqual(
            classify_kind("support_9309", None, "attachment_pii_scan"),
            "SUPPORT_ATTACHMENT",
        )
        self.assertEqual(classify_kind("support_5569", None, "message_pii_scan"), "SUPPORT_MESSAGE")

    def test_reidentify_value_shape(self):
        self.assertEqual(reidentify_value("email", "user_524"), "user_id")
        self.assertEqual(reidentify_value("user_id", "a.b@example.com"), "email")
        self.assertEqual(reidentify_value("email", "a.b@example.com"), "email")

    def test_owner_refs_from_record(self):
        refs = owner_refs_from_record(
            {
                "resource_id": "backup_3382",
                "subject_reference": "k.amponsah80@gmail.com",
                "restore_allowed": "true",
            }
        )
        kinds = {(r.kind, r.value) for r in refs}
        self.assertIn(("email", "k.amponsah80@gmail.com"), kinds)

    def test_placeholder_not_identity(self):
        refs = owner_refs_from_record(
            {
                "resource_id": "analytics_6830",
                "subject_reference": "no direct identifier",
            }
        )
        self.assertEqual(refs, [])

    def test_extract_refs_content_role(self):
        refs = extract_refs(
            {
                "resource_id": "support_1191",
                "subject_reference": "user_524",
                "message_text": "Please send the delivery update to side.person@icloud.com.",
            }
        )
        owner = [r for r in refs if (r.kind, r.value, r.role) == ("user_id", "user_524", "owner")]
        content = [r for r in refs if (r.kind, r.value, r.role) == ("email", "side.person@icloud.com", "content")]
        self.assertTrue(owner)
        self.assertTrue(content)

    def test_null_values_skipped(self):
        refs = owner_refs_from_record(
            {"user_id": None, "email": "NULL", "phone": "", "email_hash": None}
        )
        self.assertEqual(refs, [])

    def test_make_ref_role_default(self):
        ref = make_ref("email", "A@B.com", "owner")
        self.assertEqual(ref.value, "a@b.com")
        self.assertEqual(ref.role, "owner")

    def test_unmatched_intent_is_ambiguous(self):
        result = classify_intent("Please help me with my account.")
        self.assertEqual(result.intent, Intent.AMBIGUOUS)
        self.assertFalse(is_deletion_authorized("Please help me with my account.")[0])


if __name__ == "__main__":
    unittest.main()
