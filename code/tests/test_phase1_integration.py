from __future__ import annotations

import json
import unittest
from copy import deepcopy

from ghostdata.csvio import load_audit_log, load_identities, load_requests
from ghostdata.engine import _observation_candidate, _steps_to_json, _validated_discoveries, evaluate_case
from ghostdata.identities import IdentityIndex
from ghostdata.ledger import EvidenceLedger
from ghostdata.matcher import build_user_evidence_index
from ghostdata.runtime.agent import RuntimeAgent, RuntimeAgentConfig
from ghostdata.runtime.providers import ModelResponse, ModelUsage


class MockInvestigationRouter:
    def __init__(self, query: str) -> None:
        self.query = query
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        action = (
            {"action": "search_evidence", "args": {"query": self.query}}
            if self.calls == 1
            else {"action": "STOP", "args": {}}
        )
        return ModelResponse(
            "mock",
            "mock-model",
            json.dumps(action),
            ModelUsage("mock", "mock-model", 1, 1, 2),
        )


class TestPhase1Integration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ledger = EvidenceLedger().build()
        cls.identities = IdentityIndex(load_identities(), load_audit_log())

    def test_valid_discovery_reaches_planner_and_changes_output(self):
        for case in load_requests("sample_deletion_requests.csv"):
            users = self.identities.resolve_email(case.email)
            if len(users) != 1:
                continue
            user_id = next(iter(users))
            index = build_user_evidence_index(self.ledger, self.identities, case.audit_at)
            initial = index.for_user(user_id)
            for target in initial:
                omitted = deepcopy(index)
                omitted.by_user[user_id] = [
                    obs for obs in initial
                    if (obs.file_id, obs.resource_id) != (target.file_id, target.resource_id)
                ]
                before = evaluate_case(case, self.ledger, omitted, self.identities)
                agent = RuntimeAgent(
                    MockInvestigationRouter(target.resource_id),
                    RuntimeAgentConfig(max_calls_per_case=2, mode="assist"),
                )
                after = evaluate_case(
                    case,
                    self.ledger,
                    omitted,
                    self.identities,
                    runtime_agent=agent,
                )
                if _steps_to_json(before.steps) != _steps_to_json(after.steps):
                    self.assertEqual(agent.router.calls, 2)
                    self.assertEqual(len(agent.last_tool_results), 1)
                    return
        self.fail("No valid owner-linked discovery changed a public-case plan")

    def test_candidate_gate_rejects_fabricated_unsupported_and_post_audit(self):
        case = None
        user_id = None
        post_audit = None
        for candidate_case in load_requests("sample_deletion_requests.csv"):
            candidate_users = self.identities.resolve_email(candidate_case.email)
            if len(candidate_users) != 1:
                continue
            candidate_user = next(iter(candidate_users))
            candidate_post = next(
                (
                    obs for obs in self.ledger.observations()
                    if any(
                        candidate_user in self.identities.resolve_ref(ref.kind, ref.value)
                        for ref in obs.refs
                        if ref.role == "owner"
                    )
                    and (
                        (obs.captured_at and obs.captured_at > candidate_case.audit_at)
                        or (obs.observed_at and obs.observed_at > candidate_case.audit_at)
                    )
                ),
                None,
            )
            if candidate_post is not None:
                case, user_id, post_audit = candidate_case, candidate_user, candidate_post
                break
        self.assertIsNotNone(case)
        self.assertIsNotNone(user_id)
        self.assertIsNotNone(post_audit)
        valid = next(
            obs for obs in self.ledger.observations()
            if any(
                user_id in self.identities.resolve_ref(ref.kind, ref.value)
                for ref in obs.refs
                if ref.role == "owner"
            )
            and obs.captured_at is not None
            and obs.captured_at <= case.audit_at
        )
        fabricated = _observation_candidate(valid)
        fabricated["evidence_id"] = "evidence_fabricated"
        self.assertEqual(
            _validated_discoveries(
                [{"result": {"candidates": [fabricated]}}],
                user_id,
                self.identities,
                case.audit_at,
                self.ledger,
            ),
            [],
        )

        unsupported = next(
            obs for obs in self.ledger.observations()
            if not any(ref.role == "owner" for ref in obs.refs)
        )
        self.assertEqual(
            _validated_discoveries(
                [{"result": {"candidates": [_observation_candidate(unsupported)]}}],
                user_id,
                self.identities,
                case.audit_at,
                self.ledger,
            ),
            [],
        )

        self.assertEqual(
            _validated_discoveries(
                [{"result": {"candidates": [_observation_candidate(post_audit)]}}],
                user_id,
                self.identities,
                case.audit_at,
                self.ledger,
            ),
            [],
        )


if __name__ == "__main__":
    unittest.main()
