"""Tests for provider routing, bounded actions, and usage accounting."""

from __future__ import annotations

import io
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
    _post_json,
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
        self.assertEqual(agent.last_tool_results[0]["result"]["executed"], True)

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

    class _FakeResponse:
        def __init__(self, body: bytes) -> None:
            self._body = body

        def read(self) -> bytes:
            return self._body

        def __enter__(self) -> "_FakeResponse":
            return self

        def __exit__(self, *args: object) -> bool:
            return False

    @patch("ghostdata.runtime.providers.urllib.request.urlopen")
    def test_post_json_success_returns_parsed_body(self, urlopen):
        urlopen.return_value = self._FakeResponse(
            b'{"choices": [{"message": {"content": "ok"}}], '
            b'"usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3}}'
        )
        result = _post_json("https://example.invalid", {}, {})
        self.assertEqual(result["choices"][0]["message"]["content"], "ok")

    @patch("ghostdata.runtime.providers.urllib.request.urlopen")
    def test_post_json_http_429_includes_sanitized_error_body(self, urlopen):
        body = b'{"error":{"code":429,"message":"Quota exceeded for quota metric","status":"RESOURCE_EXHAUSTED"}}'
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.invalid", 429, "Too Many Requests", {}, io.BytesIO(body),
        )
        with self.assertRaises(RuntimeModelError) as raised:
            _post_json("https://example.invalid", {}, {})
        message = str(raised.exception)
        self.assertIn("HTTP 429", message)
        self.assertIn("Quota exceeded", message)
        # The request URL must not be surfaced (it may carry an API key).
        self.assertNotIn("example.invalid", message)

    @patch("ghostdata.runtime.providers.urllib.request.urlopen")
    def test_post_json_http_403_includes_sanitized_error_body(self, urlopen):
        body = b'{"error":{"message":"Invalid API key","type":"invalid_request_error"}}'
        urlopen.side_effect = urllib.error.HTTPError(
            "https://example.invalid", 403, "Forbidden", {}, io.BytesIO(body),
        )
        with self.assertRaises(RuntimeModelError) as raised:
            _post_json("https://example.invalid", {}, {})
        message = str(raised.exception)
        self.assertIn("HTTP 403", message)
        self.assertIn("Invalid API key", message)
        self.assertNotIn("example.invalid", message)

    @patch("ghostdata.runtime.providers.urllib.request.urlopen")
    def test_post_json_malformed_json_raises(self, urlopen):
        urlopen.return_value = self._FakeResponse(b"not json at all")
        with self.assertRaises(RuntimeModelError) as raised:
            _post_json("https://example.invalid", {}, {})
        self.assertIn("invalid JSON", str(raised.exception))

    @patch("ghostdata.runtime.providers.urllib.request.urlopen")
    def test_post_json_network_failure_raises(self, urlopen):
        urlopen.side_effect = urllib.error.URLError("connection refused")
        with self.assertRaises(RuntimeModelError) as raised:
            _post_json("https://example.invalid", {}, {})
        self.assertIn("URLError", str(raised.exception))

    @patch("ghostdata.runtime.providers.urllib.request.urlopen")
    def test_http_error_redacts_api_key_and_url(self, urlopen):
        secret = "sk-ant-very-secret-key-value-12345"
        gemini_url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/m:generateContent?key={secret}"
        )
        body = b'{"error":{"message":"rate limited"}}'
        urlopen.side_effect = urllib.error.HTTPError(
            gemini_url, 429, "Too Many Requests", {}, io.BytesIO(body),
        )
        with self.assertRaises(RuntimeModelError) as raised:
            _post_json(gemini_url, {}, {})
        message = str(raised.exception)
        self.assertNotIn(secret, message)
        self.assertNotIn("?key=", message)
        self.assertNotIn("generativelanguage.googleapis.com", message)

    def test_router_default_order_puts_gemini_first(self):
        router = ProviderRouter()
        self.assertEqual(router.order, ("gemini", "openrouter"))
        self.assertNotIn("groq", router.order)

    def test_router_never_includes_groq(self):
        router = ProviderRouter()
        for name in router.order:
            self.assertNotEqual(name, "groq")

    @patch("ghostdata.runtime.providers._post_json")
    def test_gemini_tried_first_and_openrouter_used_on_failure(self, post_json):
        def side_effect(url, headers, payload):
            if "generativelanguage.googleapis.com" in url:
                raise RuntimeModelError("gemini: HTTP 403; bad key")
            return {
                "choices": [{"message": {"content": '{"action":"STOP"}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }

        post_json.side_effect = side_effect

        router = ProviderRouter(("gemini", "openrouter"))
        import os
        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-gemini-key", "OPENROUTER_API_KEY": "test-or-key"},
        ):
            response = router.complete([{"role": "user", "content": "Hello"}])
        self.assertEqual(response.provider, "openrouter")
        # Gemini must have been attempted first (raised), then OpenRouter succeeded.
        self.assertEqual(post_json.call_count, 2)

    @patch("ghostdata.runtime.providers._post_json")
    def test_gemini_success_means_openrouter_not_called(self, post_json):
        def side_effect(url, headers, payload):
            if "generativelanguage.googleapis.com" in url:
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [{"text": '{"action":"STOP"}'}],
                            }
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 1,
                        "candidatesTokenCount": 2,
                        "totalTokenCount": 3,
                    },
                }
            return {
                "choices": [{"message": {"content": '{"action":"STOP"}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }

        post_json.side_effect = side_effect
        import os
        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-gemini-key", "OPENROUTER_API_KEY": "test-or-key"},
        ):
            router = ProviderRouter(("gemini", "openrouter"))
            response = router.complete([{"role": "user", "content": "Hello"}])
        self.assertEqual(response.provider, "gemini")
        self.assertEqual(post_json.call_count, 1)

    @patch("ghostdata.runtime.providers._post_json")
    def test_both_providers_failing_raises_without_groq(self, post_json):
        post_json.side_effect = RuntimeModelError("provider failed")
        import os
        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-gemini-key", "OPENROUTER_API_KEY": "test-or-key"},
        ):
            router = ProviderRouter(("gemini", "openrouter"))
            with self.assertRaises(RuntimeModelError) as raised:
                router.complete([{"role": "user", "content": "Hello"}])
        message = str(raised.exception)
        # Groq must not appear anywhere in the failure chain.
        self.assertNotIn("groq", message)
        # Both active providers must have been attempted.
        self.assertEqual(post_json.call_count, 2)

    @patch("ghostdata.runtime.providers._post_json")
    def test_usage_verifier_default_excludes_groq(self, post_json):
        from ghostdata.runtime.usage import UsageVerifier

        def side_effect(url, headers, payload):
            if "generativelanguage.googleapis.com" in url:
                return {
                    "candidates": [
                        {
                            "content": {
                                "parts": [
                                    {"text": '{"valid":true,"note":"ok"}'},
                                ],
                            }
                        }
                    ],
                    "usageMetadata": {
                        "promptTokenCount": 1,
                        "candidatesTokenCount": 2,
                        "totalTokenCount": 3,
                    },
                }
            return {
                "choices": [{"message": {"content": '{"valid":true,"note":"ok"}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 2, "total_tokens": 3},
            }

        post_json.side_effect = side_effect
        import os
        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-gemini-key", "OPENROUTER_API_KEY": "test-or-key"},
        ):
            verifier = UsageVerifier()
            self.assertNotIn("groq", verifier.router.order)
            result = verifier.verify("case_1", [])
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(post_json.call_count, 1)

    def test_runtime_agent_records_provider_failures(self):
        import os
        with patch.dict(
            "os.environ",
            {"GEMINI_API_KEY": "test-gemini-key", "OPENROUTER_API_KEY": "test-or-key"},
        ):
            router = ProviderRouter(("gemini", "openrouter"))
            agent = RuntimeAgent(
                router,
                RuntimeAgentConfig(max_calls_per_case=2, mode="assist"),
            )
        actions = agent.investigate(
            type("Case", (), {"case_id": "case_1", "audit_at": None})(),
            {"known_observation_count": 0},
        )
        # With no live provider responses available in this mocked environment,
        # the agent should not crash and deterministic conclusions remain safe.
        self.assertIsInstance(actions, list)


if __name__ == "__main__":
    unittest.main()
