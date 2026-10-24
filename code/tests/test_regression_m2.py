"""Regression test runner against 32 public sample cases."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

import sys
sys.path.insert(0, "C:/Users/rahul/OneDrive/Desktop/CTS/hackerrank-orchestrate-october26/code")

from ghostdata.csvio import load_requests, load_identities, load_audit_log, load_activity
from ghostdata.engine import evaluate_case, _steps_to_json
from ghostdata.identities import IdentityIndex
from ghostdata.ledger import EvidenceLedger
from ghostdata.matcher import build_user_evidence_index


@dataclass
class RegressionResult:
    case_id: str
    expected_status: str
    actual_status: str
    status_match: bool
    expected_steps: list[dict]
    actual_steps: list[dict]
    steps_match: bool
    mismatches: list[str]


def load_sample_output() -> dict[str, tuple[str, list[dict]]]:
    """Load sample_output.csv and return case_id -> (status, steps)."""
    result = {}
    with open("dataset/sample_output.csv", "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            case_id = row["case_id"]
            status = row["deletion_status"]
            steps = json.loads(row["steps_json"])
            result[case_id] = (status, steps)
    return result


def compare_steps(expected: list[dict], actual: list[dict]) -> tuple[bool, list[str]]:
    """Compare two step lists, return (match, mismatches)."""
    mismatches = []

    if len(expected) != len(actual):
        mismatches.append(f"Step count mismatch: expected {len(expected)}, got {len(actual)}")
        # Still compare what we can
        min_len = min(len(expected), len(actual))
    else:
        min_len = len(expected)

    for i in range(min_len):
        exp = expected[i]
        act = actual[i]
        for field in ["step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"]:
            exp_val = exp.get(field)
            act_val = act.get(field)
            if exp_val != act_val:
                mismatches.append(f"Step {i+1} {field}: expected {exp_val}, got {act_val}")

    return len(mismatches) == 0, mismatches


def run_regression() -> list[RegressionResult]:
    """Run regression on all 32 sample cases."""
    # Build all indexes
    ledger = EvidenceLedger().build()
    identities = load_identities()
    audit_log = load_audit_log()
    activity = load_activity()
    identity_index = IdentityIndex(identities, audit_log)
    user_index = build_user_evidence_index(ledger, identity_index)

    # Load sample cases and expected output
    requests = load_requests("sample_deletion_requests.csv")
    expected = load_sample_output()

    results = []

    for case in requests:
        if case.case_id not in expected:
            continue

        expected_status, expected_steps = expected[case.case_id]

        # Build user index with this case's audit_at for co-location inference
        user_index = build_user_evidence_index(ledger, identity_index, case.audit_at)

        # Evaluate
        result = evaluate_case(case, ledger, user_index, identity_index)

        # Convert actual steps to comparable format
        actual_steps = json.loads(_steps_to_json(result.steps))

        # Compare
        status_match = result.deletion_status == expected_status
        steps_match, mismatches = compare_steps(expected_steps, actual_steps)

        reg_result = RegressionResult(
            case_id=case.case_id,
            expected_status=expected_status,
            actual_status=result.deletion_status,
            status_match=status_match,
            expected_steps=expected_steps,
            actual_steps=actual_steps,
            steps_match=steps_match,
            mismatches=mismatches,
        )
        results.append(reg_result)

    return results


def print_regression_report(results: list[RegressionResult]) -> None:
    """Print detailed regression report."""
    total = len(results)
    status_ok = sum(1 for r in results if r.status_match)
    steps_ok = sum(1 for r in results if r.steps_match)
    both_ok = sum(1 for r in results if r.status_match and r.steps_match)

    print(f"\n{'='*80}")
    print(f"REGRESSION TEST: {total} sample cases")
    print(f"{'='*80}")
    print(f"Status match:     {status_ok}/{total} ({status_ok/total*100:.1f}%)")
    print(f"Steps match:      {steps_ok}/{total} ({steps_ok/total*100:.1f}%)")
    print(f"Full match:       {both_ok}/{total} ({both_ok/total*100:.1f}%)")
    print(f"{'='*80}")

    for r in results:
        status_symbol = "OK" if r.status_match else "FAIL"
        steps_symbol = "OK" if r.steps_match else "FAIL"
        print(f"\n{r.case_id}: status {status_symbol} ({r.expected_status} -> {r.actual_status}), steps {steps_symbol}")

        if not r.status_match:
            print(f"  STATUS MISMATCH: expected {r.expected_status}, got {r.actual_status}")

        if r.mismatches:
            for m in r.mismatches[:5]:  # Show first 5 mismatches
                print(f"  - {m}")
            if len(r.mismatches) > 5:
                print(f"  ... and {len(r.mismatches) - 5} more mismatches")


def write_regression_json(results: list[RegressionResult], output_path: str) -> None:
    """Write detailed regression results to JSON."""
    data = []
    for r in results:
        data.append({
            "case_id": r.case_id,
            "expected_status": r.expected_status,
            "actual_status": r.actual_status,
            "status_match": r.status_match,
            "steps_match": r.steps_match,
            "mismatches": r.mismatches,
            "expected_steps": r.expected_steps,
            "actual_steps": r.actual_steps,
        })

    Path(output_path).write_text(json.dumps(data, indent=2), encoding="utf-8")


if __name__ == "__main__":
    results = run_regression()
    print_regression_report(results)
    write_regression_json(results, "code/evaluation/regression_m2.json")
    print("\nDetailed results written to code/evaluation/regression_m2.json")