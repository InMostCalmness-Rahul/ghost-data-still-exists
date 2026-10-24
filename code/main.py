"""Ghost Data Still Exists - CLI entry point.

Available commands:

* ``selftest``         - run the built-in unit tests for parsers and identity resolution
* ``summary``          - parse the whole evidence tree and report coverage by source
* ``validate-samples`` - resolve every public sample case and compare the evidence
                         recovered with what sample_output.csv cites
* ``evaluate-samples`` - run the deterministic decision engine on public samples
                         without writing output artifacts

The final 518-case output run is intentionally not exposed by this CLI until
the output validator and final-run readiness checks are complete.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in (None, ""):  # allow "python code/main.py ..."
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ghostdata.csvio import load_audit_log, load_identities  # noqa: E402
from ghostdata.identities import IdentityIndex  # noqa: E402
from ghostdata.ledger import EvidenceLedger  # noqa: E402
from ghostdata.matcher import build_user_evidence_index  # noqa: E402


def command_selftest() -> int:
    import unittest

    from pathlib import Path as _Path

    loader = unittest.TestLoader()
    suite = loader.discover(_Path(__file__).resolve().parent / "tests")
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    return 0 if result.wasSuccessful() else 1


def command_summary() -> int:
    ledger = EvidenceLedger().build()
    print(f"evidence files parsed: {len(ledger.files)}")
    print(f"activity claim rows:   {len(ledger.activity)}")
    by_kind = Counter(ef.parser_kind for ef in ledger.files)
    records_by_kind = Counter(obs.kind for obs in ledger.observations())
    for kind, count in sorted(by_kind.items()):
        with_records = sum(1 for ef in ledger.files if ef.parser_kind == kind and ef.records)
        print(f"  {kind:8s} files={count:3d} with_records={with_records:3d}")
    print("record categories:")
    for kind, count in sorted(records_by_kind.items()):
        print(f"  {kind:22s} {count}")
    problematic = [
        ef for ef in ledger.files
        if ef.parser_kind in ("sql", "json", "log", "txt") and not ef.records
    ]
    if problematic:
        print("files parsed with zero records:")
        for ef in problematic:
            print(f"  {ef.file_id} ({ef.parser_kind}) notes={ef.notes[:3]}")
    return 0


def command_validate_samples() -> int:
    ledger = EvidenceLedger().build()
    identities = IdentityIndex(load_identities(), load_audit_log())
    user_index = build_user_evidence_index(ledger, identities)

    from ghostdata.csvio import load_requests
    from ghostdata.paths import dataset_dir, repo_root

    requests = load_requests("sample_deletion_requests.csv")
    sample_output_path = dataset_dir() / "sample_output.csv"

    def cited_files(case_id: str) -> set[str]:
        import csv as _csv

        with sample_output_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in _csv.DictReader(fh):
                if row["case_id"] == case_id:
                    import re as _re

                    return set(_re.findall(r"evidence_\d+", row["steps_json"], flags=_re.IGNORECASE))
        return set()

    resolved_direct = resolved_via_history = unresolved = 0
    rows: list[dict] = []
    cited_hits = cited_misses = extra_files_total = 0
    resource_hits = resource_misses = 0
    import csv as _csv
    import re as _re

    for request in requests:
        users = identities.resolve_email(request.email)
        role_route = ""
        if users:
            if any(identities.profiles[u].current_email == request.email.strip().lower() for u in users):
                role_route = "current_email"
                resolved_direct += 1
            elif any(u for u in users):
                role_route = "historical_email"
                resolved_via_history += 1
        else:
            unresolved += 1
        obs = user_index.for_user(next(iter(users))) if users else []
        usable = []
        for o in obs:
            checker = EvidenceLedger.usable_at(request.audit_at)
            if checker(o):
                usable.append(o)
        found_files = {o.file_id for o in usable}
        found_resources = {o.resource_id for o in usable}
        cited = cited_files(request.case_id)
        hit = cited & found_files
        cited_hits += len(hit)
        cited_misses += len(cited - found_files)
        extra_files_total += len(found_files - cited)

        expected_resources: set[str] = set()
        import csv as _csv
        with sample_output_path.open("r", encoding="utf-8-sig", newline="") as fh:
            for row in _csv.DictReader(fh):
                if row["case_id"] == request.case_id:
                    expected_resources = set(_re.findall(r'"resource_id":"([^"\\]+)"', row["steps_json"]))
        r_hit = expected_resources & found_resources
        resource_hits += len(r_hit)
        resource_misses += len(expected_resources - found_resources)
        rows.append(
            {
                "case_id": request.case_id,
                "email": request.email,
                "audit_at": request.audit_at.isoformat() if request.audit_at else None,
                "resolved_users": sorted(users),
                "route": role_route or ("NONE" if not users else ""),
                "evidence_files_for_user": sorted(found_files),
                "sample_output_cited": sorted(cited),
                "cited_covered": sorted(hit),
                "cited_missing": sorted(cited - found_files),
                "extra_files": sorted(found_files - cited),
                "expected_resources": sorted(expected_resources),
                "resources_recovered": sorted(r_hit),
                "resources_missing": sorted(expected_resources - found_resources),
                "resource_count": len(usable),
            }
        )

    total_cited = cited_hits + cited_misses
    coverage = (cited_hits / total_cited * 100.0) if total_cited else 100.0
    print(f"sample cases: {len(requests)}")
    print(f"email resolved via current identity: {resolved_direct}")
    print(f"email resolved via history (audit log): {resolved_via_history}")
    print(f"unresolved email: {unresolved}")
    print(f"identity ambiguities (value -> multiple users): {len(identities.ambiguities)}")
    print(f"sample_output cited evidence ids: {total_cited}")
    print(f"  recovered within audit_at: {cited_hits} (coverage {coverage:.1f}%)")
    print(f"  not recovered: {cited_misses}")
    print(f"additional files also referencing the user: {extra_files_total}")
    print(f"resource-id coverage: {resource_hits}/{resource_hits + resource_misses}")
    miss_rows = [r for r in rows if r["cited_missing"]]
    if miss_rows:
        print("cases with missing citations:")
        for r in miss_rows:
            print(f"  {r['case_id']}: missing={r['cited_missing']} route={r['route']} "
                  f"missing_resources={r['resources_missing']}")

    out_path = repo_root() / "code" / "evaluation" / "sample_validation_m1.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(
            {
                "cases": rows,
                "identity_ambiguities": [
                    {"value": a.value, "kind": a.kind, "users": a.users} for a in identities.ambiguities
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"detailed report written: {out_path}")
    return 0


def command_evaluate_samples() -> int:
    """Evaluate the deterministic engine against the 32 public samples."""
    import csv

    from ghostdata.csvio import load_requests
    from ghostdata.engine import _steps_to_json, evaluate_case

    ledger = EvidenceLedger().build()
    identity_index = IdentityIndex(load_identities(), load_audit_log())
    expected: dict[str, tuple[str, list[dict]]] = {}
    sample_output = Path(__file__).resolve().parents[1] / "dataset" / "sample_output.csv"
    with sample_output.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            expected[row["case_id"]] = (row["deletion_status"], json.loads(row["steps_json"]))

    status_matches = 0
    step_matches = 0
    full_matches = 0
    requests = load_requests("sample_deletion_requests.csv")

    for case in requests:
        user_index = build_user_evidence_index(ledger, identity_index, case.audit_at)
        result = evaluate_case(case, ledger, user_index, identity_index)
        actual_steps = json.loads(_steps_to_json(result.steps))
        expected_status, expected_steps = expected[case.case_id]
        status_match = result.deletion_status == expected_status
        steps_match = actual_steps == expected_steps
        status_matches += status_match
        step_matches += steps_match
        full_matches += status_match and steps_match

    total = len(requests)
    print(f"sample cases: {total}")
    print(f"status matches: {status_matches}/{total}")
    print(f"exact step matches: {step_matches}/{total}")
    print(f"full matches: {full_matches}/{total}")
    return 0 if full_matches == total else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Ghost Data Still Exists deterministic audit agent")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("selftest", help="run unit tests")
    sub.add_parser("summary", help="parse all evidence and summarize")
    sub.add_parser("validate-samples", help="validate parsing + identity resolution on sample cases")
    sub.add_parser(
        "evaluate-samples",
        help="evaluate the decision engine on 32 samples without writing output",
    )
    args = parser.parse_args(argv)
    if args.command == "selftest":
        return command_selftest()
    if args.command == "summary":
        return command_summary()
    if args.command == "validate-samples":
        return command_validate_samples()
    if args.command == "evaluate-samples":
        return command_evaluate_samples()
    parser.error(f"unsupported command: {args.command}")
    return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
