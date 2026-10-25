"""Validation and safe writing for the challenge output contract."""

from __future__ import annotations

import csv
import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

HEADER = ("case_id", "deletion_status", "steps_json")
STATUSES = {"COMPLETE", "INCOMPLETE", "NOT_APPLICABLE"}
PHASES = ("FINDING", "REMEDIATION", "VERIFICATION")
PHASE_RANK = {phase: rank for rank, phase in enumerate(PHASES)}

OPERATION_STATE = {
    "REPORT_REMAINING_RECORD": ("FINDING", "PRESENT"),
    "REPORT_EXPOSED_PII": ("FINDING", "PRESENT"),
    "REPORT_ACTIVE_DATA_FLOW": ("FINDING", "ACTIVE"),
    "REPORT_RESTORE_RISK": ("FINDING", "ACTIVE"),
    "DISABLE_DATA_FLOW": ("REMEDIATION", "DISABLED"),
    "BLOCK_RESTORE": ("REMEDIATION", "BLOCKED"),
    "DELETE_RECORD": ("REMEDIATION", "ABSENT"),
    "REDACT_RECORD": ("REMEDIATION", "REDACTED"),
    "ANONYMIZE_RECORD": ("REMEDIATION", "ANONYMIZED"),
    "VERIFY_RECORD_ABSENT": ("VERIFICATION", "ABSENT"),
    "VERIFY_RECORD_PRESENT": ("VERIFICATION", "PRESENT"),
    "VERIFY_RECORD_REDACTED": ("VERIFICATION", "REDACTED"),
    "VERIFY_RECORD_ANONYMIZED": ("VERIFICATION", "ANONYMIZED"),
    "VERIFY_DATA_FLOW_DISABLED": ("VERIFICATION", "DISABLED"),
    "VERIFY_RESTORE_BLOCKED": ("VERIFICATION", "BLOCKED"),
}


class OutputValidationError(ValueError):
    """Raised when output would violate the challenge contract."""


def _manifest_ids() -> set[str]:
    from ghostdata.ledger import load_manifest

    return {item.file_id for item in load_manifest()}


def _validate_steps(
    case_id: str,
    status: str,
    steps: Any,
    evidence_ids: set[str],
) -> None:
    if not isinstance(steps, list):
        raise OutputValidationError(f"{case_id}: steps_json must be an array")
    if status == "NOT_APPLICABLE" and steps:
        raise OutputValidationError(f"{case_id}: NOT_APPLICABLE must have no steps")
    if status == "COMPLETE" and any(
        step.get("phase") != "VERIFICATION" for step in steps if isinstance(step, dict)
    ):
        raise OutputValidationError(f"{case_id}: COMPLETE may contain verification steps only")

    expected_no = 1
    previous_phase = -1
    seen: set[tuple[str, str, str, str]] = set()
    for step in steps:
        if not isinstance(step, dict):
            raise OutputValidationError(f"{case_id}: every step must be an object")
        required = {"step_no", "phase", "system_id", "resource_id", "operation", "state", "evidence_id"}
        missing = required - set(step)
        if missing:
            raise OutputValidationError(f"{case_id}: step missing {sorted(missing)}")
        if step["step_no"] != expected_no:
            raise OutputValidationError(f"{case_id}: step numbers must be contiguous from 1")
        expected_no += 1
        operation = step["operation"]
        if operation not in OPERATION_STATE:
            raise OutputValidationError(f"{case_id}: unsupported operation {operation!r}")
        expected_phase, expected_state = OPERATION_STATE[operation]
        if step["phase"] != expected_phase or step["state"] != expected_state:
            raise OutputValidationError(
                f"{case_id}: {operation} requires {expected_phase}/{expected_state}"
            )
        phase_rank = PHASE_RANK[step["phase"]]
        if phase_rank < previous_phase:
            raise OutputValidationError(f"{case_id}: phases are out of order")
        previous_phase = phase_rank
        key = (step["phase"], step["system_id"], step["resource_id"], operation)
        if key in seen:
            raise OutputValidationError(f"{case_id}: duplicate step {key}")
        seen.add(key)
        if not all(isinstance(step[field], str) and step[field] for field in (
            "phase", "system_id", "resource_id", "operation", "state"
        )):
            raise OutputValidationError(f"{case_id}: step identity fields must be non-empty strings")
        evidence_id = step["evidence_id"]
        if not isinstance(evidence_id, str):
            raise OutputValidationError(f"{case_id}: evidence_id must be a string")
        if step["phase"] == "REMEDIATION" and evidence_id:
            raise OutputValidationError(f"{case_id}: remediation evidence_id must be empty")
        if evidence_id and evidence_id not in evidence_ids:
            raise OutputValidationError(f"{case_id}: unknown evidence_id {evidence_id!r}")


def validate_results(
    results: Iterable[Any],
    expected_case_ids: Iterable[str] | None = None,
    evidence_ids: set[str] | None = None,
) -> None:
    """Validate CaseResult objects before they are serialized."""
    result_list = list(results)
    case_ids = [result.case_id for result in result_list]
    if len(case_ids) != len(set(case_ids)):
        raise OutputValidationError("case IDs must be unique")
    if case_ids != sorted(case_ids):
        raise OutputValidationError("case IDs must be sorted")
    if expected_case_ids is not None and case_ids != sorted(expected_case_ids):
        raise OutputValidationError("output case IDs do not match the expected request set")
    known_evidence = evidence_ids if evidence_ids is not None else _manifest_ids()
    for result in result_list:
        if result.deletion_status not in STATUSES:
            raise OutputValidationError(
                f"{result.case_id}: unsupported status {result.deletion_status!r}"
            )
        _validate_steps(
            result.case_id,
            result.deletion_status,
            json.loads(result.steps_json) if hasattr(result, "steps_json") else [
                {
                    "step_no": step.step_no,
                    "phase": step.phase.value,
                    "system_id": step.system_id,
                    "resource_id": step.resource_id,
                    "operation": step.operation.value,
                    "state": step.state.value,
                    "evidence_id": step.evidence_id,
                }
                for step in result.steps
            ],
            known_evidence,
        )


def write_results(
    output_path: str | Path,
    results: Iterable[Any],
    expected_case_ids: Iterable[str] | None = None,
) -> None:
    """Validate and write output.csv atomically through csv.writer."""
    result_list = sorted(list(results), key=lambda result: result.case_id)
    validate_results(result_list, expected_case_ids=expected_case_ids)
    destination = Path(output_path)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with temporary.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(HEADER)
            for result in result_list:
                steps = [
                    {
                        "step_no": step.step_no,
                        "phase": step.phase.value,
                        "system_id": step.system_id,
                        "resource_id": step.resource_id,
                        "operation": step.operation.value,
                        "state": step.state.value,
                        "evidence_id": step.evidence_id,
                    }
                    for step in result.steps
                ]
                writer.writerow([
                    result.case_id,
                    result.deletion_status,
                    json.dumps(steps, separators=(",", ":")),
                ])
        temporary.replace(destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
