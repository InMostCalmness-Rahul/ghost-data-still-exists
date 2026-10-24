"""Unit tests: log file parsing across all five observed line formats."""

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ghostdata.logfiles import parse_log_file

KV_TRACE = """2026-09-26T07:49:50Z level=INFO service=account_service trace_id=rb-1 event=profile_lookup_started lookup_key=historical.person@gmail.com
2026-09-26T07:49:51Z level=INFO service=account_service trace_id=rb-1 resource_id=account_222 event=profile_lookup_completed rows=1 http_status=200
2026-09-26T07:51:26Z level=INFO service=integration_service trace_id=rb-2 event=connector_config_read_started subject_key=user_49
2026-09-26T07:51:27Z level=INFO service=integration_service trace_id=rb-2 resource_id=data_flow_4713 event=connector_config_read_completed enabled=false last_delivery_status=stopped
2026-09-26T07:54:41Z level=INFO service=backup_service trace_id=rb-3 event=restore_policy_read_started lookup_key=backup.person@gmail.com
2026-09-26T07:54:42Z level=INFO service=backup_service trace_id=rb-3 resource_id=backup_7809 event=restore_policy_read_completed archive_present=true restore_allowed=false
2026-09-26T07:57:13Z level=INFO service=search_service trace_id=rb-4 event=index_query_started match_key=hit.person@gmail.com
2026-09-26T07:57:14Z level=INFO service=search_service trace_id=rb-4 resource_id=search_888 event=index_query_completed result=hit
2026-09-26T09:19:47Z level=INFO service=support_platform trace_id=rb-5 event=message_scan_started subject_key=varga.person@yahoo.com
2026-09-26T09:19:48Z level=WARN service=support_platform trace_id=rb-5 resource_id=support_9553 event=message_pii_scan matched_value=varga.person@yahoo.com detector=direct_identifier
"""

JSON_LINES = """2026-09-10T08:56:15Z {"severity":"DEBUG","service":"log_router","event":"export_started"}
2026-09-10T08:56:20Z {"severity":"INFO","service":"account_service","trace_id":"tr-5563868","resource_id":"account_6633","event":"profile_lookup_completed","rows":"1","http_status":"200","duration_ms":"84"}
2026-09-15T11:22:02Z {"severity":"DEBUG","service":"analytics_platform","event":"analytics_profile_read_started","lookup_key":"anon.read@x.com"}
2026-09-15T11:22:03Z {"severity":"INFO","service":"analytics_platform","trace_id":"tr-9000001","resource_id":"analytics_257","event":"analytics_profile_read","direct_identifiers":"0","email":"null","phone":"null"}
"""

PIPE_LINES = """2026-07-03T07:51:30Z | DEBUG | log_router | collector-5 | export_started | instance="collector-5"
2026-07-03T07:51:32Z | DEBUG | security_service | tr-5156005 | audit_record_read_completed | instance="security-6" resource_id="audit_record_4413" integrity_check="passed" rows="1" correlation_key="user_211"
"""

SYSLOG_LINES = """2026-08-22T10:51:11Z <15>1 node-1 account_service tr-4973247 - - level=DEBUG event="profile_lookup_started" lookup_key="nana.b9576@outlook.com"
2026-08-22T10:51:17Z <15>1 node-1 account_service tr-4973247 - - level=DEBUG resource_id="account_1785" event="profile_lookup_completed" rows="1" http_status="200"
"""

CLOUD_LINES = """2026-06-08T06:52:07Z requestId=collector-1 level=DEBUG function=log_router message="event=\\"export_started\\""
2026-06-08T06:52:09Z requestId=tr-1108860 level=INFO function=search_service message="resource_id=\\"search_021\\" event=\\"index_query_completed\\" index=\\"customer_directory_v3\\" result=\\"hit\\" correlation_key=\\"mrios9507.jr@fastmail.com\\""
"""

BRACKET_LINES = """2026-07-28T05:51:16Z [DEBUG] [log_router] [collector-9] export_started: instance="collector-9"
2026-07-28T05:51:21Z [INFO] [account_service] [tr-6074163] profile_lookup_completed: resource_id="account_7947" rows="0" http_status="404" correlation_key="erik.h9688@outlook.com"
"""

RECORD_LOOKUP_LINES = """2026-03-15T07:00:00Z INFO service=downstream_delivery_service event=record_lookup seq=2 system="account_service" resource_id="account_1538" record_type="USER_PROFILE" result="FOUND" subject_reference="n.mokoena70@yahoo.com"
2026-03-15T07:00:00Z WARN service=search_index_service event=record_lookup seq=12 system="analytics_platform" resource_id="analytics_3181" record_type="ANALYTICS_PROFILE" result="IDENTIFIABLE" subject_reference="zmahlangu160178@gmail.com"
"""


class TestLogFileParser(unittest.TestCase):
    def _parse(self, content):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "x.log"
            path.write_text(content, encoding="utf-8")
            return parse_log_file(path, "ev_test", "evidence/logs/x.log")

    def _by_rid(self, ef):
        return {obs.resource_id: obs for obs in ef.records}

    def test_kv_trace_pairing(self):
        ef = self._parse(KV_TRACE)
        obs = self._by_rid(ef)
        self.assertEqual(len(obs), 5)
        account = obs["account_222"]
        self.assertEqual(account.kind, "USER_PROFILE")
        self.assertIs(account.present, True)
        self.assertEqual({(r.kind, r.value) for r in account.refs}, {("email", "historical.person@gmail.com")})

        flow = obs["data_flow_4713"]
        self.assertIs(flow.enabled, False)
        self.assertEqual({(r.kind, r.value) for r in flow.refs}, {("user_id", "user_49")})

        backup = obs["backup_7809"]
        self.assertEqual(backup.kind, "BACKUP_ARCHIVE")
        self.assertIs(backup.restore_allowed, False)
        self.assertIs(backup.present, True)

        search = obs["search_888"]
        self.assertIs(search.present, True)

        message = obs["support_9553"]
        self.assertEqual(message.kind, "SUPPORT_MESSAGE")
        self.assertIs(message.present, True)

    def test_json_lines(self):
        ef = self._parse(JSON_LINES)
        obs = self._by_rid(ef)
        self.assertEqual(len(obs), 2)
        self.assertIs(obs["account_6633"].present, True)
        anon = obs["analytics_257"]
        self.assertIs(anon.identifiable, False)

    def test_pipe_lines(self):
        ef = self._parse(PIPE_LINES)
        obs = self._by_rid(ef)
        self.assertEqual(len(obs), 1)
        audit = obs["audit_record_4413"]
        self.assertEqual(audit.kind, "SECURITY_AUDIT_LOG")
        self.assertEqual({(r.kind, r.value) for r in audit.refs}, {("user_id", "user_211")})

    def test_syslog_lines(self):
        ef = self._parse(SYSLOG_LINES)
        obs = self._by_rid(ef)
        self.assertIs(obs["account_1785"].present, True)
        self.assertEqual({(r.kind, r.value) for r in obs["account_1785"].refs},
                         {("email", "nana.b9576@outlook.com")})

    def test_cloud_lines(self):
        ef = self._parse(CLOUD_LINES)
        obs = self._by_rid(ef)
        self.assertEqual(len(obs), 1)
        self.assertEqual(obs["search_021"].refs[0].value, "mrios9507.jr@fastmail.com")

    def test_bracket_lines(self):
        ef = self._parse(BRACKET_LINES)
        obs = self._by_rid(ef)
        absent = obs["account_7947"]
        self.assertIs(absent.present, False)
        self.assertEqual({(r.kind, r.value) for r in absent.refs},
                         {("email", "erik.h9688@outlook.com")})

    def test_record_lookup_selfcontained_lines(self):
        ef = self._parse(RECORD_LOOKUP_LINES)
        obs = self._by_rid(ef)
        self.assertEqual(len(obs), 2)
        self.assertEqual(obs["account_1538"].kind, "USER_PROFILE")
        self.assertIs(obs["account_1538"].present, True)
        self.assertEqual(obs["account_1538"].refs[0].value, "n.mokoena70@yahoo.com")
        self.assertIs(obs["analytics_3181"].identifiable, True)

    def test_garbage_lines_skipped(self):
        ef = self._parse("not a log line at all\n2026-13-45T99:99:99Z broken\n")
        self.assertEqual(ef.records, [])
        self.assertTrue(any("skipped=2" in n for n in ef.notes))


if __name__ == "__main__":
    unittest.main()
