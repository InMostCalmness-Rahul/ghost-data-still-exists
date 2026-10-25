"""Tests for provider routing, bounded actions, and usage accounting."""

from __future__ import annotations

import json
import urllib.error
import unittest
from unittest.mock import patch

from ghostdata.runtime.agent import RuntimeAgent, RuntimeAgentConfig
from ghostdata.runtime.providers import (
    ModelResponse,
    ModelUsage,
    PROVIDERS,
    ProviderRouter,
    RuntimeModelError,
    _openai_response,
)
from ghostdata.runtime.usage import UsageLedger


class FakeRouter:
    def __init__(self) -> None:
        self.calls = 0

    def complete(self, messages):
        self.calls += 1
        return ModelResponse(
            "fake", "fake-model",
            json.dumps({"action": "STOP"}),
            ModelUsage("fake", "fake-model", 3, 2, 5),
        )


class ActionRouter:
    def __init__(self) -> None:
        self.calls = 0
        self.messages = []

    def complete(self, messages):
        self.calls += 1
        self.messages.append(messages)
        action = "search_evidence" if self.calls == 1 else "STOP"
        return ModelResponse(
            "fake", "fake-model",
            json.dumps({"action": action, "args": {}}),
            ModelUsage("fake", "fake-model", 3, 2, 5),
        )


class TestRuntime(unittest.TestCase):
    def test_agent_stops_and_records_usage(self):
        router = FakeRouter()
        ledger = UsageLedger()
        agent = RuntimeAgent(router, RuntimeAgentConfig(max_calls_per_case=4, mode="assist"), ledger)
        actions = agent.investigate(
            type("Case", (), {"case_id": "case_1", "audit_at": None})(),
            {"known_observation_count": 0},
        )
        self.assertEqual(actions, [{"action": "STOP"}])
        self.assertEqual(router.calls, 1)
        self.assertEqual(len(ledger.records), 1)

    def test_agent_executes_only_the_deterministic_tool(self):
        router = ActionRouter()
        agent = RuntimeAgent(router, RuntimeAgentConfig(max_calls_per_case=4, mode="assist"))
        actions = agent.investigate(
            type("Case", (), {"case_id": "case_1", "audit_at": None})(),
            {"known_observation_count": 2},
            tool_executor=lambda action, args, context: {
                "executed": True,
                "action": action,
                "observation_count": context["known_observation_count"],
            },
        )
        self.assertEqual([item["action"] for item in actions], ["search_evidence", "STOP"])
        self.assertIn('"executed": true', router.messages[1][-1]["content"])

    @patch("ghostdata.runtime.providers._post_json")
    def test_openai_compatible_provider_uses_supplied_key(self, post_json):
        post_json.return_value = {
            "choices": [{"message": {"content": '{"action":"STOP"}'}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
        }
        _openai_response(
            PROVIDERS["groq"],
            "test-secret",
            [{"role": "user", "content": "test"}],
        )
        self.assertEqual(post_json.call_args.args[1]["Authorization"], "Bearer test-secret")

    def test_router_without_credentials_is_explicit(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(RuntimeModelError) as raised:
                ProviderRouter().complete([{"role": "user", "content": "test"}])
        self.assertIn("credential unavailable", str(raised.exception))

    @patch("ghostdata.runtime.providers.urllib.request.urlopen")
    def test_http_errors_expose_status_without_response_body(self, urlopen):
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.invalid",
            401,
            "unauthorized",
            {},
            None,
        )
        with self.assertRaises(RuntimeModelError) as raised:
            from ghostdata.runtime.providers import _post_json
            _post_json("https://example.invalid", {}, {})
        self.assertEqual(str(raised.exception), "provider request failed: HTTP 401")


if __name__ == "__main__":
    unittest.main()
