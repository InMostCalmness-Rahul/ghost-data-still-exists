from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from evaluation.validator import OutputValidationError, validate_results, write_results
from ghostdata.remediation import Operation, Phase, State, Step


def result(case_id: str = "case_001", status: str = "COMPLETE", steps=None):
    return SimpleNamespace(
        case_id=case_id,
        deletion_status=status,
        steps=steps or [],
    )


class TestOutputValidator(unittest.TestCase):
    def test_valid_complete_result_writes_csv_round_trip(self):
        item = result(
            steps=[
                Step(
                    1,
                    Phase.VERIFICATION,
                    "account_service",
                    "account_001",
                    Operation.VERIFY_RECORD_ABSENT,
                    State.ABSENT,
                    "evidence_54",
                )
            ]
        )
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.csv"
            write_results(output, [item], expected_case_ids=["case_001"])
            with output.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["case_id"], "case_001")
            self.assertEqual(json.loads(rows[0]["steps_json"])[0]["evidence_id"], "evidence_54")

    def test_rejects_duplicate_or_unsorted_cases(self):
        with self.assertRaises(OutputValidationError):
            validate_results([result("case_002"), result("case_002")])
        with self.assertRaises(OutputValidationError):
            validate_results([result("case_002"), result("case_001")])

    def test_rejects_invalid_operation_state_pair(self):
        item = result(
            status="INCOMPLETE",
            steps=[
                Step(
                    1,
                    Phase.FINDING,
                    "account_service",
                    "account_001",
                    Operation.DELETE_RECORD,
                    State.PRESENT,
                    "evidence_54",
                )
            ],
        )
        with self.assertRaises(OutputValidationError):
            validate_results([item])

    def test_rejects_unknown_citation_and_remediation_citation(self):
        unknown = result(
            steps=[
                Step(
                    1,
                    Phase.VERIFICATION,
                    "account_service",
                    "account_001",
                    Operation.VERIFY_RECORD_ABSENT,
                    State.ABSENT,
                    "not-in-manifest",
                )
            ],
        )
        with self.assertRaises(OutputValidationError):
            validate_results([unknown])

        cited_remediation = result(
            status="INCOMPLETE",
            steps=[
                Step(
                    1,
                    Phase.REMEDIATION,
                    "account_service",
                    "account_001",
                    Operation.DELETE_RECORD,
                    State.ABSENT,
                    "evidence_54",
                )
            ],
        )
        with self.assertRaises(OutputValidationError):
            validate_results([cited_remediation])

    def test_rejects_non_verification_complete_result(self):
        item = result(
            steps=[
                Step(
                    1,
                    Phase.FINDING,
                    "account_service",
                    "account_001",
                    Operation.REPORT_REMAINING_RECORD,
                    State.PRESENT,
                    "evidence_54",
                )
            ],
        )
        with self.assertRaises(OutputValidationError):
            validate_results([item])

    def test_writer_does_not_leave_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "output.csv"
            with self.assertRaises(OutputValidationError):
                write_results(
                    output,
                    [result(
                        status="INCOMPLETE",
                        steps=[
                            Step(
                                1,
                                Phase.REMEDIATION,
                                "account_service",
                                "account_001",
                                Operation.DELETE_RECORD,
                                State.ABSENT,
                                "evidence_54",
                            )
                        ],
                    )],
                )
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
