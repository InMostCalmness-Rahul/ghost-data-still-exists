"""Bounded runtime agentic loop whose output cannot change audit conclusions."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from .providers import ProviderRouter, RuntimeModelError
from .usage import UsageLedger


@dataclass(frozen=True)
class RuntimeAgentConfig:
    max_calls_per_case: int = 4
    mode: str = "off"
    max_context_chars: int = 12000


ToolExecutor = Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]]


class RuntimeAgent:
    """Collect bounded investigation suggestions for deterministic processing."""

    def __init__(
        self,
        router: ProviderRouter | None = None,
        config: RuntimeAgentConfig | None = None,
        usage: UsageLedger | None = None,
    ) -> None:
        self.router = router or ProviderRouter()
        self.config = config or RuntimeAgentConfig()
        self.usage = usage or UsageLedger()
        self.failures: list[str] = []

    def investigate(
        self,
        case: Any,
        context: dict[str, Any],
        tool_executor: ToolExecutor | None = None,
    ) -> list[dict[str, Any]]:
        if self.config.mode != "assist":
            return []
        bounded_context = json.dumps(context, sort_keys=True, default=str)
        bounded_context = bounded_context[: self.config.max_context_chars]
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a bounded evidence-investigation assistant. Choose only "
                    "one action per response from search_evidence, resolve_identity, "
                    "find_corroboration, check_recreate_path, extract_multimodal, STOP. "
                    "Reply only JSON: {\"action\":\"...\",\"args\":{}}. Never conclude "
                    "ownership, deletion, absence, or status."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"case_id": case.case_id, "audit_at": str(case.audit_at), "context": bounded_context},
                    sort_keys=True,
                ),
            },
        ]
        actions: list[dict[str, Any]] = []
        seen: set[str] = set()
        for _ in range(self.config.max_calls_per_case):
            try:
                response = self.router.complete(messages)
                self.usage.record(case.case_id, "agent_action", response)
            except RuntimeModelError as exc:
                self.failures.append(f"{case.case_id}: {exc}")
                break
            try:
                action = json.loads(response.text)
            except json.JSONDecodeError:
                break
            if not isinstance(action, dict) or action.get("action") not in {
                "search_evidence", "resolve_identity", "find_corroboration",
                "check_recreate_path", "extract_multimodal", "STOP",
            }:
                break
            fingerprint = json.dumps(action, sort_keys=True)
            if fingerprint in seen:
                break
            seen.add(fingerprint)
            actions.append(action)
            if action["action"] == "STOP":
                break
            tool_result: dict[str, Any] = {
                "executed": False,
                "reason": "no deterministic tool executor configured",
            }
            if tool_executor is not None:
                try:
                    tool_result = tool_executor(
                        str(action["action"]),
                        action.get("args") if isinstance(action.get("args"), dict) else {},
                        context,
                    )
                except (KeyError, TypeError, ValueError) as exc:
                    tool_result = {"executed": False, "reason": f"invalid tool request: {exc}"}
            messages.append({"role": "assistant", "content": response.text})
            messages.append({
                "role": "user",
                "content": json.dumps({"tool_result": tool_result}, sort_keys=True, default=str),
            })
        return actions
