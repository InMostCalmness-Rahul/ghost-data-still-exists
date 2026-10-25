"""Append-only runtime usage ledger and independent usage reconciliation."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .providers import ModelResponse, ProviderRouter, RuntimeModelError


@dataclass(frozen=True)
class UsageRecord:
    case_id: str
    call_kind: str
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    verified: bool = False
    verifier_provider: str | None = None
    verification_note: str | None = None


class UsageLedger:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path
        self.records: list[UsageRecord] = []

    def record(self, case_id: str, call_kind: str, response: ModelResponse) -> UsageRecord:
        usage = response.usage
        record = UsageRecord(
            case_id, call_kind, usage.provider, usage.model,
            usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
        )
        self.records.append(record)
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(asdict(record), sort_keys=True) + "\n")
        return record


class UsageVerifier:
    """Ask an independent provider to reconcile per-case usage arithmetic.

    Provider-reported token counts remain authoritative. The verifier confirms
    that the ledger record is internally consistent; it cannot override usage
    metadata or manufacture missing provider counts.
    """

    def __init__(self, router: ProviderRouter | None = None) -> None:
        self.router = router or ProviderRouter(("gemini", "openrouter"))

    def verify(self, case_id: str, records: list[UsageRecord]) -> UsageRecord | None:
        payload = json.dumps([asdict(record) for record in records], sort_keys=True)
        messages = [
            {
                "role": "system",
                "content": (
                    "Reconcile token ledger arithmetic. Reply only JSON with "
                    '{"valid":true|false,"note":"short"}; do not infer missing counts.'
                ),
            },
            {"role": "user", "content": f"case_id={case_id}\nledger={payload}"},
        ]
        response = self.router.complete(messages)
        try:
            result: Any = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise RuntimeModelError("usage verifier returned invalid JSON") from exc
        valid = result.get("valid") is True if isinstance(result, dict) else False
        note = result.get("note") if isinstance(result, dict) else "invalid verifier response"
        if not valid:
            raise RuntimeModelError(f"usage verification failed: {note}")
        usage = response.usage
        return UsageRecord(
            case_id, "usage_verification", usage.provider, usage.model,
            usage.prompt_tokens, usage.completion_tokens, usage.total_tokens,
            verified=True, verifier_provider=usage.provider, verification_note=str(note),
        )
