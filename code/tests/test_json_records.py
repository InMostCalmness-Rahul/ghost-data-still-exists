"""Unit tests: JSON record documents and TXT handover parsing."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ghostdata.json_records import parse_records_document
from ghostdata.textdocs import parse_txt_document

BUNDLE = """{
  "exported_at": "2026-09-15T12:00:00Z",
  "source": "records_assurance_service",
  "snapshots": [
    {
      "captured_at": "2026-09-15T12:00:00Z",
      "data_store": "account_service",
      "collection": "customer_profiles",
      "records": []
    },
    {
      "captured_at": "2026-09-15T12:00:00Z",
      "data_store": "identity_service",
      "collection": "deleted_customer_references",
      "records": [
        {
          "resource_id": "tombstone_440",
          "subject_reference": "user_541",
          "name": null,
          "email": null,
          "phone": null,
          "email_hash": null,
          "account_status": "DELETED"
        },
        {
          "resource_id": "tombstone_9178",
          "subject_reference": "user_542",
          "name": "Kofi Addo",
          "email": "addo.kofi@gmail.com",
          "phone": "+233 24 991 1328",
          "email_hash": "4f4b9c98a05a2dad20e52313cce7809d18c3da544754dcd46d728b0173174b26",
          "account_status": "DELETED"
        }
      ]
    },
    {
      "captured_at": "2026-09-15T12:00:00Z",
      "data_store": "security_service",
      "collection": "security_audit_events",
      "records": [
        {
          "resource_id": "audit_record_6909",
          "subject_reference": "user_541",
          "event_name": "account_deletion_reviewed"
        }
      ]
    }
  ]
}
"""

EXPORT_JOBS = """{
  "captured_at": "2026-09-14T15:40:00Z",
  "source": "user_export_store",
  "collection": "customer_export_jobs",
  "records": [
    {
      "resource_id": "export_001",
      "owner_email": "gabriel.costa@proton.me",
      "file_name": "customer_export_001.zip",
      "created_at": "2026-08-04T16:11:00Z",
      "expires_at": "2026-10-04T16:11:00Z",
      "download_available": true,
      "included_sections": ["profile", "orders"]
    }
  ]
}
"""

LOOKUP_REGISTRATION = """{
  "exported_at": "2026-04-09T12:00:00Z",
  "origin": "customer_export_service",
  "record_count": 2,
  "records": [
    {
      "recorded_at": "2026-04-03T12:00:00Z",
      "system": "account_service",
      "resource_id": "account_7618",
      "record_type": "USER_PROFILE",
      "result": "FOUND",
      "subject_reference": "dnakamura7301@gmail.com"
    },
    {
      "recorded_at": "2026-04-09T12:00:00Z",
      "system": "account_service",
      "resource_id": "account_1718",
      "record_type": "USER_PROFILE",
      "result": "NOT_FOUND",
      "subject_reference": "camila.almeida@outlook.com"
    }
  ]
}
"""

ANALYTICS = """{
  "captured_at": "2026-09-07T09:45:00Z",
  "source": "analytics_identity_store",
  "collection": "customer_analytics_reports",
  "records": [
    {
      "resource_id": "analytics_901",
      "user_id": null,
      "email": null,
      "phone": null,
      "email_hash": null,
      "reporting_window": "last_90_days"
    },
    {
      "resource_id": "analytics_824",
      "user_id": "user_824",
      "email": "dahl.freja@icloud.com",
      "phone": "+46 70 226 32 84",
      "email_hash": "d61fb631b92c3bac651984c5cca965640b4a854f1619c2be08e8e2751ed4257b",
      "reporting_window": "last_90_days"
    }
  ]
}
"""

HANDOVER = """CUSTOMER PLATFORM - SHIFT HANDOVER
Snapshot: 2026-10-01T12:00:00Z

Account and downstream checks completed during the shift:

- 2026-10-01T12:00:00Z | account_service | account_3677 | USER_PROFILE | NOT_FOUND | y.tanaka32@gmail.com
- 2026-10-01T12:00:00Z | analytics_platform | analytics_6830 | ANALYTICS_PROFILE | ANONYMIZED | no direct identifier
- 2026-10-01T12:00:00Z | backup_service | backup_706 | BACKUP_ARCHIVE | BLOCKED | user_39
- 2026-10-01T12:00:00Z | integration_service | data_flow_2901 | DATA_FLOW | DISABLED | user_39
"""


def _json_file(tmpdir, name, content):
    path = (Path(tmpdir) / name)
    path.write_text(content, encoding="utf-8")
    return path


class TestJsonRecords(unittest.TestCase):
    def test_snapshot_bundle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _json_file(tmpdir, "bundle.json", BUNDLE)
            ef = parse_records_document(path, "evidence_51", "evidence/records/bundle.json")
        self.assertEqual(ef.parser_kind, "json")
        by_rid = {o.resource_id: o for o in ef.records}
        clean = by_rid["tombstone_440"]
        dirty = by_rid["tombstone_9178"]
        self.assertEqual(clean.kind, "ACCOUNT_TOMBSTONE")
        self.assertIs(clean.present, True)
        self.assertIs(clean.identifiable, False)
        self.assertTrue(clean.redacted)
        self.assertTrue(dirty.identifiable)
        self.assertEqual({(r.kind, r.value) for r in dirty.refs},
                         {("user_id", "user_542"), ("name", "kofi addo"),
                          ("email", "addo.kofi@gmail.com"),
                          ("phone", "233249911328"),
                          ("email_hash", "4f4b9c98a05a2dad20e52313cce7809d18c3da544754dcd46d728b0173174b26")})
        audit = by_rid["audit_record_6909"]
        self.assertEqual(audit.kind, "SECURITY_AUDIT_LOG")
        self.assertEqual(audit.refs[0].value, "user_541")

    def test_export_jobs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _json_file(tmpdir, "jobs.json", EXPORT_JOBS)
            ef = parse_records_document(path, "evidence_59", "evidence/records/jobs.json")
        obs = ef.records[0]
        self.assertEqual(obs.kind, "USER_EXPORT")
        self.assertIs(obs.present, True)
        self.assertEqual(obs.refs[0].value, "gabriel.costa@proton.me")
        self.assertEqual(obs.attributes.get("download_available"), True)

    def test_expired_export_is_not_present(self):
        document = EXPORT_JOBS.replace('"download_available": true', '"download_available": false')
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _json_file(tmpdir, "expired.json", document)
            ef = parse_records_document(path, "evidence_59", "evidence/records/expired.json")
        self.assertIs(ef.records[0].present, False)

    def test_lookup_registration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _json_file(tmpdir, "lookup.json", LOOKUP_REGISTRATION)
            ef = parse_records_document(path, "evidence_36", "evidence/records/lookup.json")
        by_rid = {o.resource_id: o for o in ef.records}
        self.assertIs(by_rid["account_7618"].present, True)
        self.assertIs(by_rid["account_1718"].present, False)
        self.assertEqual(by_rid["account_7618"].refs[0].value, "dnakamura7301@gmail.com")

    def test_analytics(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _json_file(tmpdir, "analytics.json", ANALYTICS)
            ef = parse_records_document(path, "evidence_56", "evidence/records/analytics.json")
        by_rid = {o.resource_id: o for o in ef.records}
        self.assertIs(by_rid["analytics_901"].identifiable, False)
        self.assertTrue(by_rid["analytics_901"].anonymized)
        self.assertTrue(by_rid["analytics_824"].identifiable)


class TestTextDocs(unittest.TestCase):
    def test_handover(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _json_file(tmpdir, "handover.txt", HANDOVER)
            ef = parse_txt_document(path, "evidence_03", "evidence/records/handover.txt", "customer_account_service")
        self.assertEqual(ef.parser_kind, "txt")
        by_rid = {o.resource_id: o for o in ef.records}
        self.assertEqual(len(by_rid), 4)
        self.assertIs(by_rid["account_3677"].present, False)
        anon = by_rid["analytics_6830"]
        self.assertTrue(anon.anonymized)
        self.assertEqual(anon.refs, [])
        blocked = by_rid["backup_706"]
        self.assertTrue(blocked.present)
        self.assertEqual({(r.kind, r.value) for r in blocked.refs}, {("user_id", "user_39")})
        flow = by_rid["data_flow_2901"]
        self.assertIs(flow.enabled, False)

    def test_bad_lines_tolerated(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _json_file(tmpdir, "handover2.txt", "no rows here\n")
            ef = parse_txt_document(path, "evidence_x", "evidence/records/handover2.txt", "orig")
        self.assertEqual(ef.records, [])
        self.assertEqual(ef.notes[0], "rows=0")


if __name__ == "__main__":
    unittest.main()
