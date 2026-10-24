"""Parser for evidence/logs/*.log point-in-time readbacks and lookup logs.

Five line formats are auto-detected per line::

  kv      ts k=v k="v ..."                    (resource_lookup_trace, service_events,
                                              support_replica, notification_delivery,
                                              search_index_diagnostic)
  json    ts {"k": "v", ...}                  (structured_service_events)
  pipe    ts | LVL | service | trace | event | k="v"   (operations_stream)
  syslog  ts <pri>1 host service trace - - kv          (syslog_archive)
  cloud   ts requestId=X level=Y function=F message="kv-escaped"  (cloud_runtime_export)
  bracket ts [LVL] [service] [trace] event: k="v"      (application_trace)

Readback traces pair a _started line (carrying the lookup key) with a
_completed line (carrying resource_id + state). Events are grouped by
trace_id; each distinct resource_id in a group yields one Observation with
all identifiers proportionally attributed to the group context.

State flags are derived from observed facts (http_status, rows, marker_found,
enabled, restore_allowed, archive_present, result), never from the reported
operation claims.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from .classify import classify_kind
from .models import EvidenceFile, Observation
from .timeutil import parse_iso

_TS_RE = r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z"
_KV_RE = re.compile(r'(\w+)=("((?:[^"\\]|\\.)*)"|(\S+))')
_JSON_LINE_RE = re.compile(rf"^({_TS_RE})\s(\{{.*\}})\s*$")
_SYSLOG_RE = re.compile(rf"^({_TS_RE})\s<\d+>1\s(\S+)\s(\S+)\s(\S+)\s\S+\s\S+\s(.*)$")
_PIPE_RE = re.compile(
    rf"^({_TS_RE})\s\|\s(\w+)\s\|\s(\S+)\s\|\s(\S+)\s\|\s(\S+)\s\|\s(.*)$"
)
_BRACKET_RE = re.compile(
    rf"^({_TS_RE})\s\[([A-Z]+)\]\s\[(\S+)\]\s\[([^\]]+)\]\s([A-Za-z_]+):\s(.*)$"
)
_CLOUD_HEADER_RE = re.compile(
    rf"^({_TS_RE})\srequestId=(\S+)\slevel=([A-Z]+)\sfunction=(\S+)\s"
    r'message="((?:[^"\\]|\\.)*)"\s*$'
)
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

_OWNER_KEYS = {
    "lookup_key": "email",
    "match_key": "email",
    "subject_key": "email",
    "scan_key": "email",
    "lookup_value": "email",
    "correlation_key": "email",
    "subject_ref": "user_id",
    "subject_reference": "user_id",
    "matched_value": "email",
    "requester_email": "email",
    "customer_email": "email",
}


@dataclass
class LogEvent:
    ts_raw: str
    ts: object | None
    level: str | None
    service: str | None
    trace_id: str | None
    event: str | None
    attrs: dict = field(default_factory=dict)


def _kv_parse(text: str, unescape: bool = False) -> dict:
    out = {}
    for key, _whole, quoted, bare in _KV_RE.findall(text):
        value = quoted if quoted != "" else bare
        if value is None:
            value = ""
        if unescape:
            value = value.replace('\\"', '"').replace("\\\\", "\\")
        if value.endswith('"') and value.startswith('"'):
            value = value[1:-1]
        out[key.strip()] = value.strip()
    return out


def _parse_line(line: str) -> LogEvent | None:
    line = line.rstrip("\n").rstrip()
    if not line.strip():
        return None
    ts_match = re.match(f"^({ _TS_RE })", line)
    if not ts_match:
        return None
    ts_raw = ts_match.group(1)
    ts = parse_iso(ts_raw)
    if ts is None:
        return None  # timestamp-shaped but invalid: untrustworthy line
    rest = line[ts_match.end():].strip()

    m = _PIPE_RE.match(line)
    if m:
        # pipe format:  ts | LVL | service | trace-or-instance | event | kv
        _level, service, trace_field, event, rest2 = m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        trace_id = trace_field if trace_field.startswith("tr-") else None
        return LogEvent(ts_raw, ts, _level, service, trace_id, event, _kv_parse(rest2, unescape=True))

    m = _BRACKET_RE.match(line)
    if m:
        _level, service, trace_field, event, rest2 = m.group(2), m.group(3), m.group(4), m.group(5), m.group(6)
        trace_id = trace_field if trace_field.startswith("tr-") else None
        return LogEvent(ts_raw, ts, _level, service, trace_id, event, _kv_parse(rest2))

    m = _SYSLOG_RE.match(line)
    if m:
        service, trace_field, rest2 = m.group(3), m.group(4), m.group(5)
        trace_id = trace_field if trace_field.startswith("tr-") else None
        attrs = _kv_parse(rest2)
        level = attrs.pop("level", None)
        event = attrs.pop("event", None)
        return LogEvent(ts_raw, ts, level, service, trace_id, event, attrs)

    m = _CLOUD_HEADER_RE.match(line)
    if m:
        _trace, level, function, payload = m.group(2), m.group(3), m.group(4), m.group(5)
        trace_id = _trace if _trace.startswith("tr-") else None
        attrs = _kv_parse(payload.replace('\\"', '"'), unescape=False)
        event = attrs.pop("event", None)
        return LogEvent(ts_raw, ts, level, function, trace_id, event, attrs)

    m = _JSON_LINE_RE.match(line)
    if m:
        try:
            payload = json.loads(m.group(2))
        except json.JSONDecodeError:
            return None
        event = payload.pop("event", None)
        level = payload.pop("severity", None) or payload.pop("level", None)
        service = payload.pop("service", None) or payload.pop("logger", None)
        trace_id = payload.pop("trace_id", None)
        return LogEvent(ts_raw, ts, level, service, trace_id, event, payload)

    # default: kv format
    attrs = _kv_parse(rest)
    level = attrs.pop("level", None)
    service = attrs.pop("service", None)
    trace_id = attrs.pop("trace_id", None)
    event = attrs.pop("event", None)
    if event is None and rest.startswith("event="):
        event = attrs.get("event")
    return LogEvent(ts_raw, ts, level, service, trace_id, event, attrs)


def _int_or_none(value):
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _present_value(attrs: dict, event: str | None) -> bool | None:
    """Derive an observed presence flag from readback facts."""
    rows = _int_or_none(attrs.get("rows"))
    if rows is not None:
        return rows > 0
    http = _int_or_none(attrs.get("http_status"))
    if http is not None:
        return http == 200
    result = (attrs.get("result") or "").strip().lower()
    if result in ("hit", "found", "present"):
        return True
    if result in ("miss", "not_found", "absent"):
        return False
    marker = (attrs.get("marker_found") or "").strip().lower()
    if marker == "true":
        return False
    if marker == "false":
        return True
    event_l = (event or "").lower()
    if event_l.endswith("_pii_scan"):
        return True  # a scan result implies the record still exists
    return None


def _enabled_value(attrs: dict) -> bool | None:
    enabled = (attrs.get("enabled") or "").strip().lower()
    if enabled in ("true", "1"):
        return True
    if enabled in ("false", "0"):
        return False
    return None


def _restore_values(attrs: dict) -> tuple[bool | None, bool | None]:
    present = (attrs.get("archive_present") or "").strip().lower()
    restore = (attrs.get("restore_allowed") or "").strip().lower()
    restore_bool = {"true": True, "1": True, "false": False, "0": False}.get(restore)
    return (True if present == "true" else None if present == "" else present == "true", restore_bool)


def _identifiable_value(attrs: dict) -> bool | None:
    direct = _int_or_none(attrs.get("direct_identifiers"))
    if direct is not None:
        return direct > 0
    looks_identifiable = any(
        (attrs.get(k) or "").strip() not in ("", "null")
        for k in ("email", "phone", "email_hash", "requester_name", "requester_email", "requester_phone")
    )
    if looks_identifiable:
        return True
    if all((attrs.get(k) or "").strip() in ("", "null") for k in ("email", "phone", "email_hash")) \
            and ("email" in attrs or "phone" in attrs):
        return False
    return None


def _refs_from_attrs(attrs: dict) -> list:
    from .classify import owner_refs_from_record

    return owner_refs_from_record(attrs)


def _observation_from_resource(
    *, group_keys: dict, events: list[LogEvent], file_id: str, source_path: str,
    captured_at, topology: str | None,
) -> Observation | None:
    resource_id = ""
    for ev in events:
        rid = (ev.attrs.get("resource_id") or "").strip()
        if rid:
            resource_id = rid
            break
    if not resource_id:
        return None
    service = next((ev.service for ev in events if ev.service), None)
    system = service
    attrs: dict = {}
    for ev in events:
        for key, value in ev.attrs.items():
            if key == "resource_id":
                continue
            attrs.setdefault(key, value)
    if attrs.get("system"):
        system = attrs.get("system")
    event_names = [ev.event or "" for ev in events]
    event_hint = " ".join(event_names)
    kind = classify_kind(resource_id, attrs.get("record_type"), event_hint)
    refs = _refs_from_attrs(group_keys)
    refs += [r for r in _refs_from_attrs(attrs) if (r.kind, r.value) not in {(x.kind, x.value) for x in refs}]
    present = _present_value(attrs, event_hint)
    enabled = _enabled_value(attrs)
    restore_present, restore_allowed = _restore_values(attrs)
    if restore_present is not None:
        present = present if present is not None else restore_present
    identifiable = _identifiable_value(attrs)
    result = (attrs.get("result") or "").strip().lower()
    redacted = True if result == "redacted" else None
    anonymized = True if result == "anonymized" else None
    if result == "identifiable":
        identifiable = True
    if redacted or anonymized:
        identifiable = False
    observed_at = next((ev.ts for ev in events if ev.ts is not None), None)
    attributes = dict(attrs)
    attributes["events"] = ",".join(e for e in event_names if e)
    if topology:
        attributes["topology"] = topology
    return Observation(
        file_id=file_id,
        source_path=source_path,
        source_kind="log",
        captured_at=captured_at,
        system=system,
        resource_id=resource_id,
        kind=kind,
        observed_at=observed_at,
        refs=refs,
        present=present,
        enabled=enabled,
        restore_allowed=restore_allowed,
        identifiable=identifiable,
        redacted=redacted,
        anonymized=anonymized,
        retention_until=parse_iso(attrs.get("retention_until")),
        account_status=attrs.get("account_status"),
        attributes=attributes,
    )


def parse_log_file(path: Path, file_id: str, dataset_relative: str) -> EvidenceFile:
    events: list[LogEvent] = []
    bad_lines = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        ev = _parse_line(line)
        if ev is None:
            bad_lines += 1
            continue
        events.append(ev)
    notes = [f"lines={len(events)}"] + ([f"skipped={bad_lines}"] if bad_lines else [])

    # A captured_at for log files: earliest event timestamp.
    captured_at = min((ev.ts for ev in events if ev.ts is not None), default=None)

    records: list[Observation] = []
    groups: dict[str, list[LogEvent]] = {}
    order: list[str] = []
    for idx, ev in enumerate(events):
        group_key = ev.trace_id if ev.trace_id else f"__line{idx}__"
        if group_key not in groups:
            groups[group_key] = []
            order.append(group_key)
        groups[group_key].append(ev)

    for group_key in order:
        group = groups[group_key]
        group_keys: dict[str, str] = {}
        for ev in group:
            for key, value in ev.attrs.items():
                if key in _OWNER_KEYS and value and value.strip():
                    group_keys.setdefault(key, value.strip())
        resource_events = [ev for ev in group if (ev.attrs.get("resource_id") or "").strip()]
        if not resource_events:
            continue
        by_rid: dict[str, list[LogEvent]] = {}
        for ev in resource_events:
            rid = ev.attrs["resource_id"].strip()
            by_rid.setdefault(rid, []).append(ev)
        for rid, ev_list in by_rid.items():
            obs = _observation_from_resource(
                group_keys=group_keys, events=ev_list, file_id=file_id,
                source_path=dataset_relative, captured_at=captured_at, topology=None,
            )
            if obs:
                records.append(obs)
    return EvidenceFile(
        file_id=file_id,
        path=dataset_relative,
        origin="service_readback",
        captured_at=captured_at,
        parser_kind="log",
        records=records,
        notes=notes,
    )
