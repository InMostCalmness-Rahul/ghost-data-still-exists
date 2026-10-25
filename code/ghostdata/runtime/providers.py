"""Small, dependency-light adapters for Gemini, OpenRouter, and Groq.

The adapters use the providers' HTTPS APIs directly so the deterministic
engine remains importable without provider SDKs. Credentials are read only
from environment variables and are never included in exceptions or logs.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


class RuntimeModelError(RuntimeError):
    """A provider failed or returned an unusable response."""


@dataclass(frozen=True)
class ModelUsage:
    provider: str
    model: str
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


@dataclass(frozen=True)
class ModelResponse:
    provider: str
    model: str
    text: str
    usage: ModelUsage


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    api_key_env: str
    model_env: str
    default_model: str
    endpoint: str


PROVIDERS = {
    "gemini": ProviderConfig(
        "gemini", "GEMINI_API_KEY", "GEMINI_MODEL", "gemini-2.5-flash",
        "https://generativelanguage.googleapis.com/v1beta/models",
    ),
    "openrouter": ProviderConfig(
        "openrouter", "OPENROUTER_API_KEY", "OPENROUTER_MODEL",
        "openai/gpt-4o-mini", "https://openrouter.ai/api/v1/chat/completions",
    ),
    "groq": ProviderConfig(
        "groq", "GROQ_API_KEY", "GROQ_MODEL", "llama-3.3-70b-versatile",
        "https://api.groq.com/openai/v1/chat/completions",
    ),
}


def _usage(provider: str, model: str, raw: dict[str, Any]) -> ModelUsage:
    prompt = raw.get("prompt_tokens")
    completion = raw.get("completion_tokens")
    total = raw.get("total_tokens")
    return ModelUsage(
        provider=provider,
        model=model,
        prompt_tokens=prompt if isinstance(prompt, int) else None,
        completion_tokens=completion if isinstance(completion, int) else None,
        total_tokens=total if isinstance(total, int) else None,
    )


_MAX_ERROR_BODY = 500


def _sanitize_error_body(raw: bytes | None) -> str:
    """Return a truncated provider error reason; never log keys or URLs."""
    if raw is None:
        return ""
    try:
        text = raw.decode("utf-8", errors="replace")
    except (UnicodeDecodeError, AttributeError):
        return "<unreadable error body>"
    text = "".join(ch if ch.isprintable() or ch in "\n\r\t" else " " for ch in text)
    text = " ".join(text.split())
    if len(text) > _MAX_ERROR_BODY:
        text = text[:_MAX_ERROR_BODY] + "\u2026"
    return text


def _post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = b""
        reader = getattr(exc, "read", None)
        if callable(reader):
            try:
                error_body = reader() or b""
            except (OSError, ValueError):
                error_body = b""
        error_text = _sanitize_error_body(error_body)
        # Never include the request URL: the Gemini API key travels in the query
        # string, and authorization headers carry bearer tokens. Provider error
        # bodies contain the actual failure reason (for example quota exhaustion
        # or invalid credentials) without revealing secrets.
        if error_text:
            raise RuntimeModelError(
                f"provider request failed: HTTP {exc.code}; {error_text}"
            ) from exc
        raise RuntimeModelError(f"provider request failed: HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeModelError(f"provider request failed: {exc.__class__.__name__}") from exc
    try:
        result = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeModelError("provider returned invalid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeModelError("provider returned a non-object response")
    return result


def _openai_response(config: ProviderConfig, key: str, messages: list[dict[str, str]]) -> ModelResponse:
    model = os.environ.get(config.model_env, config.default_model)
    result = _post_json(
        config.endpoint,
        {"Authorization": f"Bearer {key}"},
        {"model": model, "messages": messages, "temperature": 0, "max_tokens": 400},
    )
    choices = result.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeModelError(f"{config.name} returned no choices")
    message = choices[0].get("message", {})
    text = message.get("content") if isinstance(message, dict) else None
    if not isinstance(text, str):
        raise RuntimeModelError(f"{config.name} returned no text")
    raw_usage = result.get("usage", {})
    return ModelResponse(config.name, model, text, _usage(config.name, model, raw_usage))


def _gemini_response(config: ProviderConfig, key: str, messages: list[dict[str, str]]) -> ModelResponse:
    model = os.environ.get(config.model_env, config.default_model)
    contents = []
    for message in messages:
        role = "model" if message["role"] == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": message["content"]}]})
    result = _post_json(
        f"{config.endpoint}/{model}:generateContent?key={key}",
        {},
        {"contents": contents, "generationConfig": {"temperature": 0, "maxOutputTokens": 400}},
    )
    candidates = result.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise RuntimeModelError("gemini returned no candidates")
    parts = candidates[0].get("content", {}).get("parts", [])
    text = "".join(p.get("text", "") for p in parts if isinstance(p, dict))
    if not text:
        raise RuntimeModelError("gemini returned no text")
    raw_usage = result.get("usageMetadata", {})
    normalized = {
        "prompt_tokens": raw_usage.get("promptTokenCount"),
        "completion_tokens": raw_usage.get("candidatesTokenCount"),
        "total_tokens": raw_usage.get("totalTokenCount"),
    }
    return ModelResponse("gemini", model, text, _usage("gemini", model, normalized))


class ProviderRouter:
    """Route runtime requests through configured providers in priority order."""

    def __init__(self, order: tuple[str, ...] = ("gemini", "openrouter")) -> None:
        unknown = set(order) - set(PROVIDERS)
        if unknown:
            raise ValueError(f"unknown providers: {sorted(unknown)}")
        self.order = order

    def complete(self, messages: list[dict[str, str]]) -> ModelResponse:
        failures: list[str] = []
        for name in self.order:
            config = PROVIDERS[name]
            key = os.environ.get(config.api_key_env)
            if not key:
                failures.append(f"{name}: credential unavailable")
                continue
            try:
                if name == "gemini":
                    return _gemini_response(config, key, messages)
                return _openai_response(config, key, messages)
            except RuntimeModelError as exc:
                failures.append(f"{name}: {exc}")
        raise RuntimeModelError("; ".join(failures))
