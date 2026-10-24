"""Unit tests: SQL snapshot parser over synthetic SQLite-compatible dumps."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ghostdata.sqlsnapshots import parse_sql_snapshot

WRAPPED_DUMP = """-- Ghost Data Still Exists: point-in-time database snapshot
-- Dialect: SQLite-compatible SQL
-- Captured at: 2026-09-02T23:00:00Z
-- Database topology: read_replica
-- Compare the primary and any replica tables for replication drift.

BEGIN TRANSACTION;
CREATE TABLE customer_data_primary (
            resource_id TEXT PRIMARY KEY,
            origin_system TEXT NOT NULL,
            collection_name TEXT NOT NULL,
            record_json TEXT NOT NULL CHECK (json_valid(record_json)),
            updated_at TEXT NOT NULL
        );
CREATE TABLE customer_data_read_replica (
            resource_id TEXT PRIMARY KEY,
            origin_system TEXT NOT NULL,
            collection_name TEXT NOT NULL,
            record_json TEXT NOT NULL CHECK (json_valid(record_json)),
            updated_at TEXT NOT NULL
        );
INSERT INTO customer_data_primary VALUES('account_100','account_service','customer_profiles','{"resource_id":"account_100","user_id":"user_100","email":"kept.one@gmail.com","phone":null,"email_hash":null,"account_status":"ACTIVE"}','2026-09-02T22:00:00Z');
INSERT INTO customer_data_read_replica VALUES('account_100','account_service','customer_profiles','{"resource_id":"account_100","user_id":"user_100","email":"kept.one@gmail.com","phone":null,"email_hash":null,"account_status":"ACTIVE"}','2026-09-02T21:00:00Z');
INSERT INTO customer_data_primary VALUES('data_flow_55','integration_service','connector_configurations','{"resource_id":"data_flow_55","customer_email":"drift.user@x.com","connector_name":"c","enabled":true}','2026-09-02T20:00:00Z');
COMMIT;
"""

TYPED_DUMP = """-- Captured at: 2026-09-16T08:37:39Z
-- Database topology: unlabeled_snapshot

BEGIN TRANSACTION;
CREATE TABLE snapshot_scope (origin_system TEXT PRIMARY KEY, captured_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE customer_profiles (resource_id TEXT PRIMARY KEY, customer_reference TEXT, full_name TEXT, email TEXT, phone TEXT, email_hash TEXT, account_status TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE backup_restore_entries (resource_id TEXT PRIMARY KEY, customer_reference TEXT, customer_email TEXT, archive_key TEXT NOT NULL, restore_allowed INTEGER NOT NULL CHECK (restore_allowed IN (0,1)), updated_at TEXT NOT NULL);
CREATE TABLE security_audit_records (resource_id TEXT PRIMARY KEY, subject_reference TEXT NOT NULL, event_code TEXT NOT NULL, retention_until TEXT NOT NULL, updated_at TEXT NOT NULL);
INSERT INTO snapshot_scope VALUES('account_service','2026-09-16T08:37:39Z','2026-09-16T08:37:39Z');
INSERT INTO customer_profiles VALUES('account_777','user_07','Some Name','kept.seven@x.com',NULL,NULL,'DELETION_PENDING','2026-09-16T08:22:10Z');
INSERT INTO backup_restore_entries VALUES('backup_4978',NULL,'k.appiah88@gmail.com','archive/customer-data/backup_4978.tar.zst',1,'2026-09-16T07:59:54Z');
INSERT INTO security_audit_records VALUES('audit_record_1738','user_68','ACCOUNT_DELETION_RECORDED','2031-12-31T23:59:59Z','2026-09-16T06:06:38Z');
COMMIT;
"""


def _write(tmpdir, name, content):
    path = Path(tmpdir) / name
    path.write_text(content, encoding="utf-8")
    return path


class TestSqlSnapshots(unittest.TestCase):
    def test_wrapped_replica_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write(tmpdir, "wrapped.sql", WRAPPED_DUMP)
            ef = parse_sql_snapshot(path, "evidence_01", "evidence/databases/wrapped.sql")
        self.assertEqual(ef.parser_kind, "sql")
        self.assertEqual(ef.captured_at, datetime(2026, 9, 2, 23, 0, tzinfo=timezone.utc))
        by_table = {}
        for obs in ef.records:
            by_table.setdefault(obs.attributes.get("sql_table"), []).append(obs)
        self.assertEqual(len(by_table.get("customer_data_primary", [])), 2)
        self.assertEqual(len(by_table.get("customer_data_read_replica", [])), 1)
        drift = by_table["customer_data_read_replica"][0]
        self.assertEqual(drift.attributes["topology"], "read_replica")
        profile_obs = by_table["customer_data_primary"][0]
        self.assertEqual(profile_obs.kind, "USER_PROFILE")
        self.assertEqual(
            {(r.kind, r.value) for r in profile_obs.refs},
            {("user_id", "user_100"), ("email", "kept.one@gmail.com")},
        )
        flow_obs = [o for o in ef.records if o.resource_id == "data_flow_55"][0]
        self.assertEqual(flow_obs.kind, "DATA_FLOW")
        self.assertIs(flow_obs.enabled, True)

    def test_typed_inventory_tables(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write(tmpdir, "typed.sql", TYPED_DUMP)
            ef = parse_sql_snapshot(path, "evidence_09", "evidence/databases/typed.sql")
        self.assertEqual(ef.captured_at, datetime(2026, 9, 16, 8, 37, 39, tzinfo=timezone.utc))
        kinds = {obs.resource_id: obs for obs in ef.records}
        self.assertIn("account_777", kinds)
        account = kinds["account_777"]
        self.assertEqual(account.kind, "USER_PROFILE")
        self.assertEqual(account.account_status, "DELETION_PENDING")
        backup = kinds["backup_4978"]
        self.assertIs(backup.restore_allowed, True)
        self.assertEqual(backup.kind, "BACKUP_ARCHIVE")
        security = kinds["audit_record_1738"]
        self.assertEqual(security.kind, "SECURITY_AUDIT_LOG")
        self.assertEqual(security.retention_until.year, 2031)
        self.assertEqual(
            {(r.kind, r.value) for r in security.refs}, {("user_id", "user_68")}
        )

    def test_bad_sql_is_notes_not_crash(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = _write(tmpdir, "bad.sql", "THIS IS NOT SQL AT ALL >>>>")
            ef = parse_sql_snapshot(path, "evidence_bad", "evidence/databases/bad.sql")
        self.assertEqual(ef.records, [])
        self.assertTrue(any("sqlite exec failed" in n for n in ef.notes))


if __name__ == "__main__":
    unittest.main()
