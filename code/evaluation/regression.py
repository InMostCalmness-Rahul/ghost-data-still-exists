"""Non-writing diagnostics for deterministic public-sample regression."""

from __future__ import annotations

import csv
import json
import sys
from dataclasses import dataclass
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = CODE_DIR.parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from ghostdata.csvio import load_audit_log, load_identities, load_requests
from ghostdata.engine import _steps_to_json, evaluate_case
from ghostdata.identities import IdentityIndex
from ghostdata.ledger import EvidenceLedger
from ghostdata.matcher import build_user_evidence_index


StepKey = tuple[str, str, str, str, str]


@dataclass(frozen=True)
class DiffResult:
    case_id: str
    expected_status: str
    actual_status: str
    expected_steps: list[dict]
    actual_steps: list[dict]
    matched_steps: list[StepKey]
    missing_steps: list[StepKey]
    extra_steps: list[StepKey]


def _step_key(step: dict) -> StepKey:
    return (
        step["phase"],
        step["system_id"],
        step["resource_id"],
        step["operation"],
        step["state"],
    )


def _load_expected() -> dict[str, tuple[str, list[dict]]]:
    path = REPO_ROOT / "dataset" / "sample_output.csv"
    expected: dict[str, tuple[str, list[dict]]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            expected[row["case_id"]] = (
                row["deletion_status"],
                json.loads(row["steps_json"]),
            )
    return expected


def _multiset_diff(
    expected_steps: list[dict], actual_steps: list[dict]
) -> tuple[list[StepKey], list[StepKey], list[StepKey]]:
    expected_counts: dict[StepKey, int] = {}
    actual_counts: dict[StepKey, int] = {}
    for step in expected_steps:
        key = _step_key(step)
        expected_counts[key] = expected_counts.get(key, 0) + 1
    for step in actual_steps:
        key = _step_key(step)
        actual_counts[key] = actual_counts.get(key, 0) + 1

    matched: list[StepKey] = []
    missing: list[StepKey] = []
    extra: list[StepKey] = []
    for key in sorted(set(expected_counts) | set(actual_counts)):
        common = min(expected_counts.get(key, 0), actual_counts.get(key, 0))
        matched.extend([key] * common)
        missing.extend([key] * (expected_counts.get(key, 0) - common))
        extra.extend([key] * (actual_counts.get(key, 0) - common))
    return matched, missing, extra


def run_diff(case_ids: list[str] | None = None) -> list[DiffResult]:
    """Evaluate samples and return grouped, non-writing step differences."""
    ledger = EvidenceLedger().build()
    identity_index = IdentityIndex(load_identities(), load_audit_log())
    expected = _load_expected()
    wanted = set(case_ids) if case_ids else None
    results: list[DiffResult] = []

    for case in load_requests("sample_deletion_requests.csv"):
        if wanted is not None and case.case_id not in wanted:
            continue
        if case.case_id not in expected:
            continue
        user_index = build_user_evidence_index(ledger, identity_index, case.audit_at)
        actual = evaluate_case(case, ledger, user_index, identity_index)
        actual_steps = json.loads(_steps_to_json(actual.steps))
        expected_status, expected_steps = expected[case.case_id]
        matched, missing, extra = _multiset_diff(expected_steps, actual_steps)
        results.append(DiffResult(
            case_id=case.case_id,
            expected_status=expected_status,
            actual_status=actual.deletion_status,
            expected_steps=expected_steps,
            actual_steps=actual_steps,
            matched_steps=matched,
            missing_steps=missing,
            extra_steps=extra,
        ))
    return results


def _print_steps(label: str, steps: list[dict]) -> None:
    print(f"{label}:")
    for step in steps:
        print(f"  {json.dumps(step, sort_keys=True)}")


def print_diff(results: list[DiffResult], show_steps: bool = False) -> None:
    """Print a grouped diff report without creating files."""
    status_matches = sum(r.expected_status == r.actual_status for r in results)
    exact_steps = sum(not r.missing_steps and not r.extra_steps for r in results)
    print(f"sample cases: {len(results)}")
    print(f"status matches: {status_matches}/{len(results)}")
    print(f"exact step-key matches: {exact_steps}/{len(results)}")
    for result in results:
        print(
            f"{result.case_id}: status {result.expected_status} -> "
            f"{result.actual_status}; expected={len(result.expected_steps)} "
            f"actual={len(result.actual_steps)} matched={len(result.matched_steps)} "
            f"missing={len(result.missing_steps)} extra={len(result.extra_steps)}"
        )
        if result.missing_steps:
            print(f"  missing: {result.missing_steps}")
        if result.extra_steps:
            print(f"  extra: {result.extra_steps}")
        if show_steps:
            _print_steps("  expected steps", result.expected_steps)
            _print_steps("  actual steps", result.actual_steps)
