# Runtime Architecture Options Report

**Date**: 2026-10-25  
**Status**: DRAFT FOR REVIEW — design only; no production code changed  
**Prepared by**: Section 1 drafted by *Nemotron 3 Ultra Free*; Sections 2–10 drafted by *DeepSeek V4.1 Flash* (OpenCode harness, model `opencode/deepseek-v4.1-flash-free`)  
**Repository**: C:\Users\rahul\OneDrive\Desktop\CTS\hackerrank-orchestrate-october26

> **Provenance note.** This document was started by Nemotron 3 Ultra Free, which completed the initial
> LLM-provider comparison and then failed repeatedly while appending further sections. The failure mode
> (`504 Upstream idle timeout exceeded`) is reported by the user and was not independently recorded in the
> repository, so it is noted here as user-reported rather than verified. DeepSeek V4.1 Flash resumed from
> the saved file, re-verified the load-bearing factual claims, corrected claims that did not hold up, and
> appended Sections 2–10. Corrections to Section 1 are marked inline with **[corrected 2026-10-25]** rather
> than silently rewritten, so the review trail stays visible.
>
> **Verification key used throughout:** `VERIFIED` = reproduced in this environment or read from a
> primary/official source during this session; `UNVERIFIED` = plausible or documented but not reproduced
> here; `BLOCKED` = attempted and could not be completed; `ASSUMED` = user-supplied or design choice.

---

## Executive Summary

This report investigates the runtime architecture options for the "Ghost Data Still Exists" challenge. The investigation covers six areas: LLM provider options, local model feasibility, agent architecture comparison, evidence tooling, execution constraints, and production project structure.

### Executive recommendation

**Build a deterministic audit engine with bounded, optional LLM assistance, behind a provider-independent adapter.** Primary runtime model: Gemini `gemini-3.8-flash` (free tier verified free of charge). Fallback: OpenRouter free models that declare tool support. If no credential or network is available, the run still produces a complete, schema-valid `output.csv` in deterministic-only mode. Local inference is not adopted (4 GiB VRAM measured — it fits a 3–4B model, not a capable one).

### Key findings

| Area | Status | Summary |
|------|--------|---------|
| **LLM Providers** | **PASS (comparison)** | Gemini primary, OpenRouter fallback, Grok optional/not investigated. SDKs install; official pricing verified; live inference **UNVERIFIED** (no key present). |
| **Local Models** | **BLOCKED as primary** | Measured: GTX 1650 **4096 MiB** VRAM, **7.87 GiB** RAM. 1–4B fits but is inadequate for 15-field cited output; 7–8B does not fit. Ollama absent. |
| **Agent Architecture** | **PASS** | Deterministic engine + bounded LLM assist (closed action menu). Multi-agent rejected. |
| **Evidence Tools** | **PARTIAL** | PDF: `pypdf` extracts all 4 PDFs (verified). Local OCR: **BLOCKED** (no Tesseract). Vision API: viable, **UNVERIFIED** (no key). SQLite/FastAPI: omitted by decision. |
| **Execution Constraints** | **UNVERIFIED** | No repository rule guarantees network or credentials at evaluation → keyless run treated as mandatory. |
| **Project Structure** | **PASS (proposal)** | Additive structure mapped onto the current tree; `code/main.py` entry point preserved; nothing moved. |

### Gate status

| Gate | Status |
|------|--------|
| A. Provider comparison | **PASS** |
| A1/A2. Gemini / OpenRouter live inference | **UNVERIFIED** (no credentials) |
| B. Provider-independent configuration | **PASS** |
| C. Local-model feasibility | **PASS (investigation) / BLOCKED (primary)** |
| D. Architecture decision | **PASS** |
| E. Evidence processing | **PDF PASS · local OCR BLOCKED · vision UNVERIFIED** |
| F. Execution constraints | **UNVERIFIED** |
| G. Project structure | **PASS (proposal)** |
| H. Security & reliability | **PASS (design)** |
| I. Evaluation plan | **PASS (design, not executed)** |

---

## 1. LLM Provider Comparison

### 1.1 Google Gemini API (Primary Candidate)

**Verified Facts (re-probed 2026-10-25 by DeepSeek V4.1 Flash):**
- SDK: `google-genai` **2.33.0** imports successfully; `google-generativeai` **0.8.6** also imports but emits a deprecation warning that all support has ended. Use `google-genai`.
- Installation: `pip install google-genai` — **works** (verified).
- API key: required (`GEMINI_API_KEY` or `GOOGLE_API_KEY`). Neither is set in this environment.
- `GET https://generativelanguage.googleapis.com/v1beta/models` without a key returns **403 "Method doesn't allow unregistered callers"** (verified) — so model listing and any live call **cannot be verified without a key**.
- Tool/function calling and structured output: official documentation pages exist (`/gemini-api/docs/function-calling`, `/gemini-api/docs/structured-output`). Feature existence is documented; **runtime behaviour is UNVERIFIED** because no key was available and none was requested.

**Pricing — VERIFIED from the official pricing page (`/gemini-api/docs/pricing`, fetched 2026-10-25, per 1M tokens):**

| Model | Free tier | Paid (Standard) | Notes |
|---|---|---|---|
| `gemini-3.8-flash` | **Free of charge** | $0.75 input / $3.75 output (through 2026-12-31; $1.50 / $7.50 from 2027-01-01) | Most capable Flash tier; free-tier content may be used to improve products |
| `gemini-3.5-flash-lite` | **Free of charge** | $0.30 input / $2.50 output | Cost-optimised for high-volume agentic tasks |
| `gemini-3.1-pro-preview` | Not available | $2.00 / $12.00 (≤200k prompt) | Pro tier has no free quota |
| `gemini-4-argon` | **Not available** | $2.00 / $10.00 (through 2026-11-30) | Flagship reasoning model, paid only |

**Corrections to the earlier draft [corrected 2026-10-25]:**
- The draft stated "free tier: 15 RPM, 1M TPM for gemini-1.5-flash". Per-model rate-limit numbers are rendered dynamically on the docs page and were **not** retrievable; that figure referred to a superseded model generation and is **removed**. Exact free-tier RPM/TPM/RPD must be read from AI Studio or the rate-limits page while signed in → **UNVERIFIED**.
- The draft stated "2M context (gemini-1.5-flash)". Context windows are per-model and must be read from the live model card (`models.get`) → **UNVERIFIED**.
- Batch API is advertised at **50% cost reduction** (free tier excluded from Batch for Flash models per the pricing table) — relevant if we ever batch 518 cases.

**Assumptions (user-supplied, not verified here):**
- The user holds a Google AI Studio API key.
- Free tier is sufficient for development; a 518-case run may exceed daily quota (quota size **UNVERIFIED**).

### 1.2 OpenRouter (Fallback Candidate)

**Verified Facts (re-probed 2026-10-25):**
- API: OpenAI-compatible (`https://openrouter.ai/api/v1`). `GET /api/v1/models` is public and returned **HTTP 200** without credentials.
- SDK: `openai` **3.37.0** installed; works against OpenRouter via `base_url` override.
- Catalogue at probe time: **466 models**, of which **20** have zero prompt *and* zero completion price, and **17 of those 20 declare `tools`** in `supported_parameters` (i.e. function calling). Counts churn — re-read at runtime, never hardcode.
- Free models declaring tool support (id / context length / structured outputs / input modalities):

| Model id | Context | Structured | Inputs |
|---|---|---|---|
| `nvidia/nemotron-3-ultra-550b-a55b:free` | 1,000,000 | – | text |
| `nvidia/nemotron-3-super-120b-a12b:free` | 262,144 | yes | text |
| `nvidia/nemotron-3.5-super-vl:free` | 1,000,000 | yes | text, image, video |
| `google/gemma-4-31b-it:free` | 262,144 | yes | image, text, video |
| `google/gemma-4-26b-a4b-it:free` | 262,144 | yes | image, text, video |
| `thinkingmachines/inkling:free` | 1,048,576 | – | text, image, audio |
| `thinkingmachines/inkling-small:free` | 1,048,576 | – | text, image, audio |
| `recursive/flint-v1.0:free` | 262,144 | yes | text |
| `xingchen-agi/xing4.0-29b-a4b:free` | 262,144 | yes | text |
| `poolside/laguna-s-2.1:free` | 262,144 | – | text |
| `poolside/laguna-xs-2.1:free` | 262,144 | – | text |
| `cohere/north-mini-code:free` | 256,000 | – | text |
| `dots-studio/dots-3-note-preview:free` | 512,000 | yes | text, image |
| `liquid/lfm-2.5-2.6b:free` | 65,536 | yes | text |
| `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free` | 256,000 | – | text, audio, image, video |
| `nvidia/nemotron-3.5-lightning:free` | 1,000,000 | – | text |
| `openrouter/free` (router alias) | 200,000 | yes | text, image |

- Earlier draft said "469 total / 20 free"; the free count reproduced exactly, the total moved to 466 → treat catalogue size as volatile.
- Authentication: `OPENROUTER_API_KEY` required for inference (public model list needs none). **No key was used; no inference call was made**, so tool-calling on these free models is **documented in metadata but UNVERIFIED in practice**.
- Vision-capable free options exist (`nemotron-3.5-super-vl`, `gemma-4-*`, `inkling`) — a genuine path for the 11 PNG screenshots without a paid key.

**Assumptions:**
- The user has an OpenRouter account (user-stated).
- Free-tier models are rate-limited and may be slower / less reliable; quality on a 15-field structured audit decision is **ASSUMED** to be lower than Gemini Flash.
- Free-model availability changes without notice → the provider must fail over dynamically rather than pin one id.

### 1.3 Direct Grok API (Optional Alternative)

**Status**: **UNVERIFIED** — Not investigated in detail
- xAI Grok API exists but requires separate account
- No SDK investigation performed
- Kept as optional future alternative

### 1.4 Local Inference (Ollama) — Optional Future Fallback

**Status**: **BLOCKED** — See Section 2

---

## 1.5 Provider-Independent Interface Design

> **[corrected 2026-10-25]** The sketch below is superseded by §2.2: it depends on `pydantic`, which
> this project does not need (stdlib `dataclasses` + explicit validators are sufficient), and it lacks
> capability routing, error classes, timeouts and cache keys. Kept for review history only.

```python
# Abstract base class for LLM providers
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel

class LLMMessage(BaseModel):
    role: str  # "system", "user", "assistant", "tool"
    content: str
    tool_calls: Optional[List[Dict]] = None
    tool_call_id: Optional[str] = None

class LLMResponse(BaseModel):
    content: str
    tool_calls: Optional[List[Dict]] = None
    usage: Optional[Dict[str, int]] = None
    model: str
    provider: str

class LLMProvider(ABC):
    @abstractmethod
    def complete(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Dict]] = None,
        response_schema: Optional[Dict] = None,
        temperature: float = 0.0,
        max_tokens: Optional[int] = None,
    ) -> LLMResponse:
        pass
    
    @abstractmethod
    def get_model_info(self) -> Dict[str, Any]:
        pass

# Concrete implementations:
# - GeminiProvider (google-genai)
# - OpenRouterProvider (openai SDK with base_url)
# - GrokProvider (optional)

# Factory for provider selection
def create_provider(config: Dict) -> LLMProvider:
    provider = config.get("provider", "gemini").lower()
    if provider == "gemini":
        return GeminiProvider(config)
    elif provider == "openrouter":
        return OpenRouterProvider(config)
    elif provider == "grok":
        return GrokProvider(config)
    else:
        raise ValueError(f"Unknown provider: {provider}")
```

---

## 1.6 Fallback Behavior

| Failure Type | Primary Action | Fallback Action | Max Retries |
|--------------|----------------|-----------------|-------------|
| Auth error (401/403) | Switch to fallback provider | Log error, continue with deterministic engine | 0 (no retry) |
| Rate limit (429) | Exponential backoff (1s, 2s, 4s) | Switch to fallback provider | 3 |
| Timeout | Retry with shorter timeout | Switch to fallback provider | 2 |
| Provider outage (5xx) | Exponential backoff | Switch to fallback provider | 3 |
| Malformed response | Log, retry once | Switch to fallback provider | 1 |
| Free tier exhausted | Switch to paid tier or fallback | Continue with deterministic engine | 0 |

**Safety Rules:**
- No automatic retries on 4xx errors (except 429)
- No duplicate charges — track usage per provider
- Log all provider switches with reason
- Never fabricate token counts — record actual usage when available
- Deterministic engine always available as ultimate fallback

---

## 1.7 Usage Tracking

```python
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List

@dataclass
class UsageRecord:
    timestamp: datetime
    provider: str
    model: str
    operation: str  # "complete", "embed", etc.
    input_tokens: int
    output_tokens: int
    cost_usd: float
    case_id: Optional[str] = None

class UsageTracker:
    def __init__(self):
        self.records: List[UsageRecord] = []
        self._costs: Dict[str, Dict[str, float]] = {}  # provider -> {input, output}
    
    def record(self, record: UsageRecord):
        self.records.append(record)
        # Track costs for reporting
        if record.provider not in self._costs:
            self._costs[record.provider] = {"input": 0.0, "output": 0.0}
        self._costs[record.provider]["input"] += record.input_tokens
        self._costs[record.provider]["output"] += record.output_tokens
    
    def get_summary(self) -> Dict:
        return {
            "total_calls": len(self.records),
            "per_provider": self._costs,
            "by_case": self._group_by_case(),
        }
```

**Critical**: Never fabricate token counts. Record actual usage from API responses only.

---

## 2. Recommended Provider Configuration

### 2.1 Proposed primary/fallback configuration (executive recommendation)

Use **Gemini `gemini-3.8-flash` as the primary runtime model** (free tier, verified free of charge today; strong structured-output and multimodal support) and **OpenRouter as the fallback tier**, selecting from the free models that declare `tools` support (preferred: `nvidia/nemotron-3-super-120b-a12b:free` for text reasoning, `nvidia/nemotron-3.5-super-vl:free` or `google/gemma-4-31b-it:free` for screenshots). Wrap both behind a **small provider interface with a capability-based router** (text-reasoning / vision / classify), and make the *audit engine itself provider-agnostic and LLM-optional*. If no provider is reachable, the run continues in **deterministic-only mode** and produces a valid `output.csv` with `llm_degraded=true` recorded in the run manifest. The LLM is an *escalation path* for ambiguity, not a required dependency for producing output.

Rationale for Gemini primary: verified free tier on a capable Flash model, native JSON-schema output, native image input, and one SDK (`google-genai`) that covers both. OpenRouter stays as fallback because it needs no code change beyond `base_url`, and its free pool already contains vision models — which is the cheapest route to the 11 unreadable PNGs.

### 2.2 Capability-based provider interface (revised)

The draft interface in §1.5 used `pydantic`. Correction: **do not add pydantic as a runtime dependency** — the existing codebase is stdlib-only (`csv`, `json`, `sqlite3`, `re`, `datetime`) and adding a validation framework for six dataclasses is not justified. Use `dataclasses` + explicit validation functions.

```python
# code/ghostdata/llm/base.py  (proposed, NOT implemented)
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

Capability = Literal["text", "vision"]

@dataclass(frozen=True)
class LLMRequest:
    capability: Capability
    system: str
    messages: list[dict]        # {"role": "user"|"assistant"|"tool", "content": ...}
    tools: list[dict] | None = None      # JSON-schema tool definitions
    response_schema: dict | None = None  # JSON schema for structured output
    temperature: float = 0.0
    max_output_tokens: int = 2048
    timeout_s: float = 45.0
    cache_key: str | None = None         # content hash; enables replay without a call

@dataclass(frozen=True)
class LLMResult:
    ok: bool
    text: str | None = None
    tool_calls: list[dict] = field(default_factory=list)
    parsed: Any | None = None            # schema-validated payload, if requested
    provider: str = ""
    model: str = ""
    usage: dict | None = None            # RAW provider usage block, never synthesised
    latency_ms: int = 0
    error_class: str | None = None       # auth|rate_limit|timeout|server|bad_response|quota|config
    error_detail: str = ""

class Provider(Protocol):
    name: str
    def supports(self, capability: Capability) -> bool: ...
    def complete(self, req: LLMRequest) -> LLMResult: ...
```

Two rules make this provider-independent in practice:

1. **Callers never see provider SDK types.** The controller receives `LLMResult` only, so switching Gemini ↔ OpenRouter touches exactly one adapter file.
2. **Usage is passed through, never computed.** `usage` is the provider's raw block (`usage_metadata` for Gemini, `usage` for OpenAI-compatible). If the provider returns nothing, record `None` — never estimate. This is what makes `evaluation/usage_report.md` honest.

### 2.3 Configuration contract (environment only)

No key, endpoint, or model id is ever written into source, the report, or the archive. Resolution order, first match wins:

| Setting | Env var | Default | Notes |
|---|---|---|---|
| Mode | `GHOST_AUDIT_LLM_MODE` | `assist` | `assist` \| `off`. `off` skips all network calls |
| Primary provider | `GHOST_AUDIT_PROVIDER` | `gemini` | `gemini` \| `openrouter` \| `none` |
| Gemini key | `GEMINI_API_KEY` *or* `GOOGLE_API_KEY` | — | never logged, never echoed |
| Gemini model | `GEMINI_MODEL` | `gemini-3.8-flash` | must be resolvable via `models.get` |
| OpenRouter key | `OPENROUTER_API_KEY` | — | fallback tier |
| OpenRouter model (text) | `OPENROUTER_MODEL_TEXT` | `nvidia/nemotron-3-super-120b-a12b:free` | must declare `tools` |
| OpenRouter model (vision) | `OPENROUTER_MODEL_VISION` | `nvidia/nemotron-3.5-super-vl:free` | image input required |
| Fallback chain | `GHOST_AUDIT_FALLBACKS` | `openrouter` | comma-separated, tried in order |
| Retry budget | `GHOST_AUDIT_MAX_RETRIES` | `2` | per provider, per request |
| Timeout | `GHOST_AUDIT_TIMEOUT_S` | `45` | hard cap per call |
| Cache dir | `GHOST_AUDIT_CACHE` | `.cache/llm` | content-addressed replay store |

Startup validation must be **fail-soft**: missing key ⇒ log `llm_disabled: no credential`, run deterministic mode, never abort the audit. A malformed *value* (e.g. `GHOST_AUDIT_TIMEOUT_S=abc`) is a config error ⇒ refuse to start with a precise message, because silently defaulting would corrupt a scored run.

### 2.4 Failure taxonomy and fallback ladder

Each class maps to exactly one behaviour. The controlling principle: **never retry something that cannot succeed, and never retry something that already cost money without recording it.**

| Error class | Detection | Primary action | Escalation | Max attempts |
|---|---|---|---|---|
| `config` | key absent, model id invalid | disable LLM, deterministic mode | none | 0 |
| `auth` (401/403) | HTTP/status code | mark provider dead for the run, rotate to next provider | deterministic mode | **0** — retrying a bad key just burns clock |
| `rate_limit` (429) | status + `Retry-After` | sleep `min(Retry-After, 20s)` once | switch provider | 2 |
| `quota` (429 with quota text / 403 quota) | message match | switch provider | deterministic mode | 1 |
| `timeout` | socket/`DeadlineExceeded` | retry once with 1.5× timeout, same provider | switch provider | 1 |
| `server` (5xx) | status code | exponential backoff 1s, 2s + jitter | switch provider | 2 |
| `bad_response` | schema/JSON validation failure | one repair attempt (re-prompt with the validation error) | switch provider | 1 |
| `tool_error` | tool returned error payload | feed error back to model once | controller marks action unusable | 1 |

Additional safeguards against duplicate charges and dead loops:

- **Circuit breaker per (provider, model):** 3 consecutive failures open the breaker for the remainder of the run. Prevents a 518-case run from grinding through a broken provider 518 times.
- **Content-addressed cache** (`cache_key = sha256(model + system + messages + schema)`): a re-run replays previous decisions with zero calls. This is not hardcoding gold labels — it is a derived cache regenerated by running the tool, and it must be excluded from `code.zip` if it embeds any dataset content, or regenerated at run time.
- **Per-case call cap** (design: 6 calls/case) plus a **global budget cap** (`GHOST_AUDIT_MAX_CALLS`, default 1200). Hitting the cap degrades to deterministic mode for the remaining cases rather than failing.
- **No parallel fan-out without a shared counter.** Concurrency, if used at all, goes through one semaphore so the daily quota cannot be overshot by racing workers.
- **Deterministic temperature (`0.0`)** and pinned model ids so a given case produces a stable answer on replay.

### 2.5 What the LLM is allowed to decide

Keeping the blast radius small is the whole point of the hybrid design (§4). The model may only answer these four bounded questions, each with a JSON schema:

1. **Intent** — does `request_text` authorise deletion, or is it access/correction/export/marketing/other? (output: `{authorizes_deletion: bool, reason: str}`)
2. **Attribution** — given a resource and a set of candidate identity links, is this resource the subject's? (output: `{verdict: "SAME_PERSON"|"DIFFERENT_PERSON"|"INSUFFICIENT", basis_evidence_ids: [...]}` — verdict must cite evidence ids that were actually supplied)
3. **Unreadable evidence** — extract fields from a PDF/PNG that no parser handled (output: `{fields: {...}, confidence: "low"|"medium"|"high"}`)
4. **Next investigation action** — choose ONE action from a closed menu (§4.3), or `STOP`.

Everything else — policy lookup, step construction, ordering, citation validation, schema validation, CSV writing — stays deterministic. The model never writes `steps_json` directly, never assigns `deletion_status`, and never invents an `evidence_id`.

### 2.6 Cost model (structure only — no fabricated numbers)

`evaluation/usage_report.md` needs per-model call counts, token totals, averages and cost. Until a keyed run happens, **we have no usage numbers and will not invent any**. The report will therefore be generated from the durable usage ledger, with the arithmetic defined now:

```
cost_usd = (input_tokens  / 1_000_000) * price_in
         + (output_tokens / 1_000_000) * price_out
```
prices read from a single versioned table transcribed from the official pricing pages (Gemini rows above are verified as of 2026-10-25; OpenRouter free models are `0.00`). Any model with no verified price row is reported as `cost: unknown` rather than guessed. If the final run is deterministic-only, the report states exactly that: zero model calls, zero tokens, zero cost.

**Gate 2.1 (provider feasibility): PASS for configuration design; runtime inference UNVERIFIED for both providers (no credentials used).**

---

## 3. Local-Model Feasibility

The earlier draft marked this **BLOCKED — "insufficient"**. That verdict was too strong and rested on a VRAM figure that had never been measured. It has now been measured, and the honest verdict is narrower: **technically feasible for small quantised models, not recommended for this task's reasoning quality.**

### 3.1 Hardware — measured, not assumed

| Fact | Value | How verified (2026-10-25) |
|---|---|---|
| GPU | NVIDIA GeForce GTX 1650 | `nvidia-smi --query-gpu=name,memory.total,driver_version` |
| VRAM | **4096 MiB (4.00 GiB)** | same command — matches the earlier WMI `AdapterRAM` reading of 4,293,918,720 B, so the two independent sources agree |
| Driver | 591.74 | `nvidia-smi` |
| System RAM | **7.87 GiB** (8,451,309,568 B) | `Win32_ComputerSystem.TotalPhysicalMemory` |
| Second GPU | Intel UHD Graphics, 1 GiB shared | WMI `Win32_VideoController` |
| CUDA compute capability | 7.5 (Turing) — **documented spec, not probed** | GTX 1650 product spec |
| Ollama | **not installed** | `shutil.which('ollama')` → `None` |
| Local inference libs | `torch`, `llama_cpp`, `onnxruntime`, `transformers`, `ctranslate2` all **absent** | import probe |

Note on the earlier `AdapterRAM` reading: WMI `AdapterRAM` is a 32-bit field and under-reports cards with more than 4 GiB. Here `nvidia-smi` independently confirms 4096 MiB, so no correction is needed for *this* machine — but a future "8 GB" reading from WMI alone should not be trusted.

### 3.2 What actually fits in 4 GiB

Rough arithmetic (model weights only; KV cache and context grow on top):

| Class | Q4 weights | Fits in 4 GiB VRAM? | Realistic use here |
|---|---|---|---|
| 1–2B | ~0.8–1.4 GB | yes, comfortable | intent classification; field extraction from short text |
| 3–4B | ~2.0–2.5 GB | yes, tight (little room for 8k+ context) | simple classification, brittle JSON |
| 7–8B | ~4.4–4.9 GB | **no** — partial CPU offload | would thrash: 7.87 GiB total RAM is shared with Windows, Python, and the evidence ledger |
| 13B+ | ~7–8 GB+ | no | not viable |

Two hard constraints beyond VRAM: (a) 7.87 GiB system RAM means any CPU-offloaded layer competes with the parser/ledger that already holds 94 evidence files and 4,011 activity rows; (b) the task needs **15-field structured output with tool calls and cited evidence ids** — small models routinely emit schema-valid-JSON-but-wrong-ids, which is exactly the failure the deterministic validators would have to reject anyway.

### 3.3 Verdict

- **As primary runtime: not recommended.** Capability is the binding constraint, not RAM. A 3–4B model at Q4 could plausibly do intent classification (§2.5 item 1) and nothing else worth the integration cost.
- **As optional offline fallback: conditional PASS.** If a 1–3B instruct model is later wanted for intent classification only, `llama.cpp` (GGUF, CPU or partial GPU) is the lowest-friction path and needs no admin rights. It must be strictly optional and must never be required to produce `output.csv`.
- **Do not install anything yet.** Ollama is absent, no weights are present, and installing a multi-GB runtime is a user decision that buys nothing while a hosted free tier exists.

### 3.4 How the user can verify GPU specs independently

On this machine, any of these (the first is what this report used):

```powershell
nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv
nvidia-smi -q -d MEMORY | Select-String "Total"
dxdiag            # Display tab -> "Display Memory (VRAM)"
```

Or: Task Manager → Performance → GPU → *Dedicated GPU memory*. If `nvidia-smi` is not found, the NVIDIA driver is missing or not on `PATH`; WMI (`Get-CimInstance Win32_VideoController`) is then the fallback, with the 4 GiB caveat above.

**Gate 3.1 (local-model feasibility): PASS as an investigation (hardware measured, capability assessed); NOT ADOPTED as a runtime dependency.**

---

## 4. Agent Architecture

### 4.1 The three candidates, compared against what actually failed

The current M2 engine is a **linear** pipeline: parse → match → decide → emit. Its measured result on the 32 public cases is **22/32 status match (68.8%) and 1/32 exact-match steps (3.1%)**. The failures cluster into seven categories, and each architecture option is judged on whether it can plausibly fix them:

| # | M2 failure | Why the linear engine fails | Fixable by adaptive investigation? |
|---|---|---|---|
| 1 | Deleted-account binding (`account_6440` → `user_21`) | activity-window heuristic over-reaches; no corroboration step | **yes** — needs a targeted "find corroboration" action |
| 2 | COMPLETE-case compliance detection | pipeline never asks "is every required end-state satisfied?" | **yes** — needs an explicit obligation check |
| 3 | system-id normalisation | hardcoded `SYSTEM_ID_MAP` in `engine.py` | **no** — deterministic table issue |
| 4 | backup/restore risk | single `RESTORE_BACKUP` row mis-joined | partly — needs "find restore path" action |
| 5 | anonymised-analytics binding | no way to prove unlinkability | **yes** — needs a verification action |
| 6 | step ordering / excess steps | planner emits by heuristic order | **no** — deterministic ordering fix |
| 7 | multimodal gaps (11 PNGs, 4 PDFs) | no extractor | **yes** — needs an extraction action (now PDF-capable) |

So four of seven are genuinely *adaptive-investigation* problems; three are plumbing. That split is the entire argument for the architecture below: make the plumbing deterministic, and use the model only where search strategy is the problem.

| Criterion | (a) One tool-using agent + controller | (b) Multi-agent framework | (c) Deterministic engine + optional LLM assist |
|---|---|---|---|
| Fixes failure classes 1,2,5,7 | yes | yes | yes, via *bounded* escalation |
| Deterministic output for the same input | **at risk** — free-form ReAct loops vary run to run | worse (agent handoffs compound nondeterminism) | **yes** — LLM answers are schema-bounded and cacheable |
| Reproducible `steps_json` ordering | must be enforced separately anyway | hard | inherent |
| Cost for 518 cases | unbounded unless capped | highest (N agents × M turns) | lowest — model called only on ambiguity |
| Offline behaviour if no API key | run produces nothing useful | run produces nothing | **degrades to valid output** |
| Debuggability of a wrong answer | transcript-only | transcript × agents | decision + evidence ids + rule id |
| Implementation cost against existing M0–M1 | medium | high | **low** — M0–M1 parsers/ledger/identity index are reused as-is |
| Dependency footprint | none extra | framework dependency + config surface | none extra |

**Multi-agent is rejected.** There is no independent-subtask structure here — every case is a single subject with one shared evidence pool. Splitting "investigator" from "policy agent" from "verifier" agents would multiply token spend and failure surface while the *authoritative* logic (policy lookup, ordering, citation validity) stays deterministic code regardless. It also makes "why did this case get INCOMPLETE?" much harder to answer in the AI interview.

**Recommendation: (c), with a bounded investigation controller.** Concretely: deterministic engine + a controller loop that is *closed* — the model chooses from a fixed action menu, the controller validates and executes, and the loop terminates on evidence saturation or budget. This keeps §6.5's requirement ("`COMPLETE` only when every relevant copy has the required treatment…") enforceable in code rather than in prose.

### 4.2 Layer responsibilities (the determinism boundary)

| Layer | Owns | Determinism requirement |
|---|---|---|
| Evidence tools | locate → parse → normalise one artifact | pure: same bytes ⇒ same facts |
| Provenance store | every fact carries `(evidence_id, locator, extractor, observed_at)` | pure |
| Identity index | current + historical identifier resolution | pure |
| **Investigation controller** | budget, duplicate suppression, stop conditions | pure control flow |
| **LLM (assist)** | intent, ambiguous attribution, unreadable evidence, next action | **non-deterministic by nature** → answers cached by content hash, schema-validated, never trusted for ids |
| Policy engine | `deletion_rules.csv` → required end-state per record | pure |
| Remediation planner | ordered actions from gaps (flows → restores → records) | pure |
| Verification | post-remediation checks + `COMPLETE` proofs | pure |
| Output validator | schema, phases, numbering, citation existence, ≤ `audit_at` | pure, **blocking** |

The critical invariant: **the LLM can influence *where we look*, never *what we conclude*.** A model answer that fails its schema, cites an `evidence_id` not present in the supplied context, or contradicts a deterministic observation is discarded and logged — the case then falls back to the deterministic rule path.

### 4.3 Closed action menu for the controller (bounded ReAct)

The model's only degree of freedom is picking one of these per turn:

| Action | Args | Purpose | Budget weight |
|---|---|---|---|
| `search_evidence` | query terms / identifier / system / time window | candidate evidence retrieval | 1 |
| `read_evidence` | `evidence_id` | full parse of one artifact | 1 |
| `resolve_identity` | identifier (email/user_id/phone/hash/account_id) | expand current+historical identifiers | 1 |
| `find_corroboration` | `resource_id`, candidate subject | second independent link for an attribution | 2 |
| `check_recreate_path` | `system_id`/`resource_id` | sync/import/restore/index paths | 1 |
| `extract_multimodal` | `evidence_id` (PDF/PNG) | OCR/PDF/vision extraction | 2 |
| `report_obligation_gap` | `record_ref`, rule id | record an unmet policy end-state | 0 (no I/O) |
| `STOP` | reason | declare saturation | 0 |

Rules enforced by the controller, not by the prompt:

- A repeated `(action, args)` pair is rejected without consuming budget (kills search loops).
- `STOP` is mandatory once **any** stop condition fires: all candidate resources have a policy verdict; the last 2 turns produced no new evidence id; budget exhausted; or the only remaining question needs a credential/modality that is unavailable.
- Every non-`STOP` action must return new *facts*, else it counts as a failed turn (2 failed turns ⇒ forced `STOP`).
- Findings may only cite `file_id` / `activity_id` / `audit_id` that the controller actually surfaced during this case — this makes §6.6's "never cite evidence captured after `audit_at`" a mechanical test rather than a hope.

### 4.4 Why this also fixes the M2 failures that are not "search" problems

Failure classes 3 and 6 (system-id normalisation, ordering/excess steps) cannot be fixed by any amount of investigation. They need three concrete changes that belong in the deterministic layer:

1. **System ids come from the data, not a hardcoded map.** Build the `system_id` vocabulary from `evidence_files.csv` + `system_activity.csv` + parsed record paths, and assert that every emitted `system_id` exists in that vocabulary.
2. **Ordering is a sort key, not a template.** `(phase_rank, operation_rank, system_id, resource_id)` where ranks are the literal row order in §6.4 of `AGENTS.md`; `step_no` is assigned after sorting.
3. **No step without an obligation.** The planner derives steps from *policy gaps* (a rule says ABSENT, state is PRESENT ⇒ one `DELETE_RECORD` + one `VERIFY_RECORD_ABSENT`), which structurally prevents the "excess steps" class.

**Gate 4.1 (architecture decision): PASS — (c) deterministic engine + bounded LLM assist recommended; multi-agent rejected with reasons.**

---

## 5. Evidence Processing

### 5.1 PDF — PASS (verified this session)

`pypdf` **6.21.2** extracts text from all four corpus PDFs (they are ReportLab-generated with FlateDecode streams, not scans):

| PDF | Pages | Extracted chars |
|---|---|---|
| `account_history_report_20260718.pdf` | 2 | 720 |
| `delivery_correction_attachment.pdf` | 2 | 839 |
| `legal_retention_register_20260529.pdf` | 2 | 1003 |
| `security_retention_extract.pdf` | 1 | 617 |

Positively identified facts in that text: support ref `CS-4827` / `support_001`, `priya.raman@gmail.com`, `+91 98765 73142`, order `ORD-20264827`, `audit_record_003` / `user_03`, disputed orders for `user_08/user_12/user_17/user_21`, and `ingrid.dahl@outlook.com` / `ORD-20261260`. This resolves the `case_07` `evidence_58` gap that M2 recorded as unreadable.

Caveat: text extraction order is layout-dependent (ReportLab emits `Tj`/`TJ` in draw order), so label/value pairs come out as `Detail\n<value>` sequences rather than a table. The extractor must therefore emit **positional or label-anchored** facts, and anything ambiguous must be marked `confidence: low` rather than guessed.

### 5.2 PNG — local OCR BLOCKED; vision API is the viable path

| Fact | Result |
|---|---|
| `pytesseract` 0.3.13 | installed |
| Tesseract binary | **absent** (`shutil.which('tesseract')` → `None`) ⇒ `pytesseract` is unusable |
| Images | 11 PNGs, RGB, 1500–1800 px wide (e.g. `marketing_profile_console.png` 1500×920; `account_admin_console_20260926.png` 1800×1200) |
| Any text layer / metadata? | none found; they are rendered UI screenshots, so pixels are the only content |

Two viable routes, in preference order:

1. **Vision-capable API (recommended).** Gemini `gemini-3.8-flash` accepts images natively; OpenRouter free vision models (`nvidia/nemotron-3.5-super-vl:free`, `google/gemma-4-31b-it:free`) are a zero-cost fallback. Extraction prompt must demand **verbatim field transcription plus a bounding description**, and every extracted field is stored with `extractor=vision`, `confidence`, and the `evidence_id` — never as ground truth.
2. **Local Tesseract (optional, user action).** Install the Windows Tesseract build (~50 MB, free/open-source) and set `TESSERACT_CMD`. Fully offline, no quota, weaker on stylised UI fonts. Only worth it if the evaluation environment has no network.

Consistency check that makes vision output trustworthy: run one image through **both** routes during development and diff the transcribed fields; the 22 screenshots-with-known-content cases are the natural calibration set. If they disagree on identifiers, the field is marked unresolved rather than averaged.

Impact: `case_31`/`case_32` previously depended on `deleted_account_reference_20260310.png`; their account ids (`account_4857`, `account_8858`) are already recoverable from the parsed bundle, so the PNG is corroboration rather than a hard dependency. **No case is currently blocked on OCR** — the gap is completeness of findings, not producibility of a row.

### 5.3 Evidence search, identity resolution, historical state

- **Search:** an in-memory inverted index over parsed facts (identifier → evidence ids, resource id → evidence ids, system → evidence ids) beats a database at this scale (94 files, ~4k activity rows). Rebuild per run, <1 s, fully deterministic.
- **Identity resolution:** reuse the existing `IdentityIndex` (current snapshot + `user_audit_log` history, 32/32 sample emails resolved). Add explicit **tier labels** to every link: `DIRECT` (identifier observed in the artifact under the owner role), `CORROBORATED` (two independent non-claim signals), `CLAIM_ONLY` (activity/status assertion), `UNRESOLVED`.
- **Historical state at `audit_at`:** keep the existing `EvidenceLedger.usable_at(audit_at)` filter as the *only* way to obtain evidence, so post-`audit_at` artifacts are structurally unreachable.
- **Provenance:** append-only JSONL, one line per extracted fact: `{evidence_id, locator, extractor, extractor_version, observed_at, tier, confidence, payload}`. This is what lets the validator prove that a cited `evidence_id` both exists and was usable at `audit_at`.

### 5.4 SQLite and FastAPI — assessed, not adopted

| Component | Verdict | Reason |
|---|---|---|
| SQLite | **Not needed now** | Dataset is small and read-only per run; an in-memory index + JSONL provenance satisfies auditability. Add only if incremental/resumable runs over 518 cases become necessary — and then as a single local file, never a server. |
| FastAPI | **Rejected** | The contract is a CLI that writes `output.csv`. A web service adds a process to supervise, ports to bind, and an attack surface, for zero scoring benefit. |
| Agent framework (LangGraph/CrewAI/etc.) | **Rejected** | The controller is ~200 lines of loop + budget logic; a framework would obscure determinism and add a dependency chain the evaluation may not have network access to install. |

**Gate 5.1 (PDF): PASS. Gate 5.2 (PNG/OCR local): BLOCKED. Gate 5.3 (vision API): UNVERIFIED (no credentials). Gate 5.4 (search/identity/provenance design): PASS. Gate 5.5 (SQLite/FastAPI): PASS as a decision to omit.**

---

## 6. Execution Constraints: Network, Credentials, Evaluation Environment

### 6.1 What the repository actually says

Searched `AGENTS.md`, `problem_statement.md`, and `README.md` for rules on network access, external calls, and credentials. Complete set of relevant statements:

| Source | Statement | Implication |
|---|---|---|
| `problem_statement.md` §Evaluation | "Your `code.zip` must include one token-usage file: `evaluation/usage_report.md`… model providers and names, model calls, input and output tokens…" | Runtime **model use is anticipated and reportable**; a zero-call run is permitted but must be reported as such |
| `problem_statement.md` §Token Usage | "Do not include API keys, credentials, or sensitive configuration values in the submission." | Keyless execution must be supported |
| `AGENTS.md` §6.7 | "Be runnable from the terminal. Read the provided files from `dataset/`. Write the completed `output.csv` at the repository root… Read secrets from environment variables only." | CLI contract; secrets from env only |
| `AGENTS.md` §6.8, §6.9 | usage report required; "Do not include … API keys, credentials … in `code.zip`" | same |
| `README.md` §rules | "no API keys, credentials, real personal data, or sensitive configuration values are included" | same |

**No statement anywhere guarantees network access during grading, and none forbids it.** That absence is decisive for design purposes: the safe assumption is *no network and no credentials*.

### 6.2 Verdict and the resulting design constraint

**Gate 6.1 (evaluation environment network/credentials): UNVERIFIED.** Cannot be resolved from repository content. Registered as an open question for the organisers (§10.4).

Consequences, adopted as hard requirements:

1. **Keyless run must produce a complete, schema-valid `output.csv` for all 518 cases.** The deterministic path is the *baseline*, not the fallback-of-last-resort.
2. **No key may ever be required for the engine to start.** Missing credential ⇒ `llm_disabled` in the run manifest, one line in the log, continue.
3. **No secret may reach disk.** Config is read from env inside the process; nothing is written to `.env` by the program, logged, or serialised into provenance. A startup redaction filter masks anything matching common key shapes (`AIza…`, `sk-…`, `sk-or-v1-…`) before any log write.
4. **Network calls must be bounded and optional.** One provider timeout must not consume the run — the global deadline (design: 30 min for 518 cases) is checked before each call, and expiry flips the run to deterministic mode.
5. **Any cached LLM output shipped in `code.zip` must be reproducible.** If we ship the content-addressed cache to make grading keyless *and* LLM-informed, it must be regenerable by a documented command and must not contain gold labels. Safer default: **do not ship the cache**; ship the deterministic baseline, and let the LLM path be demonstrated in `evaluation/` with recorded evidence.

### 6.3 Residual risk

If grading runs offline and the shipped default were "LLM-required", the submission would score zero. That single risk dominates every other consideration in this report and is why §4 puts determinism in the engine and non-determinism behind a capability the engine can live without.

**Gate 6.1: UNVERIFIED. Gate 6.2 (offline-safe design): PASS on paper — must be proven by test T-12 (§9) before any implementation is called complete.**

---

## 7. Proposed Project Structure (compared with the current repository)

### 7.1 Current repository — measured

```
code/
  main.py                      CLI entry point (currently modified, uncommitted)
  ghostdata/
    paths.py csvio.py models.py normalize.py timeutil.py      # infra
    json_records.py logfiles.py sqlsnapshots.py textdocs.py   # parsers (M1, tested)
    ledger.py identities.py                                   # evidence ledger + identity index
    classify.py intent.py matcher.py state.py absence.py      # M2 decision path
    remediation.py engine.py                                  # policy + orchestration
  tests/  (9 files, 44 unit tests passing at M1; M2 regression 22/32)
  evaluation/
    design_gate_report.md  sample_validation_m1.json
    runtime_architecture_options.md   main.py (0 bytes — stray empty file)
```

Nothing is committed; `log.txt` is untracked. The M0–M1 layer (parsers, ledger, identity index, 44 unit tests) is the reusable asset. The M2 layer (`intent.py`, `state.py`, `absence.py`, `remediation.py`, `engine.py`) carries the seven failure classes and three hardcoded shortcuts that must go: `matcher.py` `SERVICE_EXPORT_FILES = {"evidence_92"}`, `absence.py` `AUTHORITATIVE_SNAPSHOTS`, `engine.py` `SYSTEM_ID_MAP`.

### 7.2 Proposed structure — additive, entry point preserved

```
code/
  main.py                          # KEEP as the only documented entry point
  ghostdata/
    # --- keep unchanged (M0-M1) ---
    paths.py csvio.py models.py normalize.py timeutil.py
    json_records.py logfiles.py sqlsnapshots.py textdocs.py
    ledger.py identities.py
    # --- keep, modify ---
    classify.py                    # MODIFY: data-driven system vocabulary (drops SYSTEM_ID_MAP)
    matcher.py                     # REWRITE: tiered attribution, no SERVICE_EXPORT_FILES
    # --- new ---
    multimodal/pdf_text.py         # pypdf adapter -> facts with locators
    multimodal/vision.py           # vision-API adapter (optional)
    multimodal/types.py            # MediaFact dataclass
    llm/base.py                    # Provider protocol, LLMRequest/LLMResult, error classes
    llm/gemini.py                  # google-genai adapter
    llm/openrouter.py              # openai-SDK adapter (base_url)
    llm/router.py                  # capability routing, fallback ladder, circuit breaker
    llm/cache.py                   # content-addressed replay cache
    llm/usage.py                   # durable usage ledger (raw provider usage only)
    investigation/controller.py    # bounded loop, closed action menu, stop rules
    investigation/actions.py       # action executors (pure, budget-metered)
    investigation/budget.py        # per-case + global caps
    evidence/store.py              # provenance JSONL + inverted index
    policy/rules.py                # deletion_rules.csv -> obligations (replaces absence.py)
    policy/planner.py              # obligation -> ordered remediations (replaces remediation.py)
    verify/checks.py               # remediation -> verification steps; COMPLETE proofs
    emit/steps.py                  # step construction + total ordering + numbering
    emit/validate.py               # BLOCKING schema/citation/phase validator
    emit/csv.py                    # deterministic output.csv writer
    engine.py                      # REWRITE: orchestration only, no business rules
  tests/                           # keep 9 unit files; add provider/controller/validator tests
  config/schema.py                 # env parsing + fail-soft validation
  evaluation/
    evaluation_report.md  usage_report.md  design_gate_report.md
    runtime_architecture_options.md  custom_cases/ (>=3 synthetic)
  README.md                        # setup + keyless run + keyed run
  requirements.txt                 # pinned: pypdf, google-genai, openai (all optional at runtime)
  .env.example                     # NAMES ONLY, no values
```

Mapping to the existing code is deliberately conservative: **11 files kept, 2 modified, 12 added, 1 rewritten orchestration, 2 M2 modules retired** (`absence.py` → `policy/rules.py`; `state.py` absorbed into `policy/` + `verify/`). The `ghostdata` package name and `code/main.py` CLI stay, so submission conventions and the existing M1 tests keep working.

### 7.3 `code.zip` contents and exclusions

Include: `code/**` (sources, tests, config), `README.md`, `requirements.txt`, `.env.example`, `evaluation/*.md`, `evaluation/custom_cases/`.
Exclude: `dataset/`, `output.csv` (submitted separately per §6.9), `.env`, `.cache/`, `__pycache__`, `*.pyc`, `code.zip` itself, agent traces, any virtualenv.
Remove before packaging: the stray empty `code/evaluation/main.py`.

**Gate 7.1 (structure): PASS as a proposal; no files were reorganized.**

---

## 8. Security and Reliability

### 8.1 Secrets

| Concern | Control |
|---|---|
| Where keys live | process environment only (`GEMINI_API_KEY`/`GOOGLE_API_KEY`, `OPENROUTER_API_KEY`); `.env` is user-created and git-ignored |
| Where keys must never appear | source, `README.md`, `log.txt`, provenance JSONL, run manifest, `evaluation/*.md`, `code.zip` |
| Redaction | a logging filter rewrites any token matching `AIza[0-9A-Za-z\-_]{35}`, `sk-[A-Za-z0-9]{20,}`, `sk-or-v1-[A-Za-z0-9]{20,}` to `[REDACTED]` **before** the record is written |
| Leak detection at packaging | pre-zip scan over the archive contents for the same patterns + a literal check that the resolved key value (if set) appears nowhere; abort packaging on any hit |
| Key in error messages | provider exceptions are stringified after the redaction filter; request headers are never logged |
| Least privilege | separate keys for dev and any graded run; keys are revocable and never embedded in the archive |

### 8.2 Configuration validation

- Parse once at startup into an immutable `RunConfig`; every value has a type, a default, and a validator.
- **Fail-soft** for *absent* credentials (⇒ `llm_disabled`, deterministic mode).
- **Fail-fast** for *malformed* values (`GHOST_AUDIT_TIMEOUT_S=abc`, unknown `GHOST_AUDIT_PROVIDER`) because silently defaulting would make a scored run irreproducible.
- Emit the effective config (keys redacted, model ids in clear) into the run manifest so `usage_report.md` and the AI interview can state exactly what ran.

### 8.3 Logging

| Stream | Format | Purpose | Contains |
|---|---|---|---|
| `log.txt` (repo root) | Markdown per `AGENTS.md` §5 | agent/development transcript | prompts, actions, decisions — append-only |
| run log (stderr / `--log-file`) | JSON lines | operational trace of an audit run | case id, action, latency, provider, error class — **never** key values |
| provenance JSONL | JSON lines | evidence facts + tiers | evidence id, locator, extractor, confidence |
| usage ledger | JSON lines | one record per model call | raw provider usage, model, provider, case id |

Structured JSONL is chosen over `print` because the validator and `usage_report.md` generator both need to aggregate it mechanically. Correlation id = `case_id` everywhere, so a single case can be reconstructed end-to-end.

### 8.4 Dependencies

Pinned in `requirements.txt`; each is installed today and version-checked: `pypdf==6.21.2` (required), `google-genai==2.33.0` (optional), `openai==3.37.0` (optional), `Pillow` (optional, image preprocessing). Degradation is explicit:

| Missing | Effect |
|---|---|
| `pypdf` | PDFs become `unparsed` — degrade, log, continue (tests T-09) |
| `google-genai` | Gemini provider unavailable ⇒ OpenRouter or deterministic |
| `openai` | OpenRouter unavailable ⇒ Gemini or deterministic |
| all of the above | deterministic-only run, still valid `output.csv` |

The audit core must remain importable with **zero third-party packages**, so a bare `python code/main.py` works on a clean machine.

### 8.5 Cost and usage safety

- Raw usage only, per §2.2 — `usage=None` when the provider omits it; totals computed from the ledger, never estimated.
- **Idempotency key** per call (`sha256` of model + messages + schema) so a retried call that actually succeeded is served from cache instead of being billed twice; the ledger records `cache_hit: true`.
- Global call cap and per-case cap (§2.4) so an unexpected loop cannot run up a bill.
- Free-tier exhaustion is a *routing* event, not an error: mark the provider spent, move to the next, and if none remain, finish deterministically.
- No automatic paid upgrade. Spending money requires an explicit user action documented in the README.

### 8.6 Safe failure

One rule: **a case never crashes the run**. Every case is processed inside a boundary that converts an exception into `(status=INCOMPLETE, steps=[findings known so far], diagnostics=[error])`, records the error class, and continues. Rationale: a missing row is scored as wrong *and* breaks the 518-row contract (§6.3), while a conservative `INCOMPLETE` row with a documented gap is at least contract-valid. The run manifest reports `cases_ok` / `cases_degraded` / `cases_failed` so degradation is visible rather than silent.

**Gate 8.1 (security/reliability): PASS as a design; redaction and pre-zip leak scan must be implemented and tested (T-13) before packaging.**

---

## 9. Evaluation Plan

### 9.1 Test matrix

Every row is runnable **without any API key** by injecting a fake provider transport (a stub that returns scripted `LLMResult`s or raises scripted errors). This is deliberate: fallback logic that can only be tested with a live key would be untested on most runs.

| ID | Scenario | Method | Pass criterion |
|---|---|---|---|
| T-01 | Provider switching | stub: primary returns `auth`, fallback returns OK | call served by fallback; ledger shows provider switch with reason |
| T-02 | Auth failure | stub raises 401 | **zero** retries on primary; run continues; `llm_disabled` not set if fallback works |
| T-03 | Rate limit | stub raises 429 with `Retry-After: 1` | one bounded sleep then success; ≤2 attempts; no duplicate success recorded |
| T-04 | Timeout | stub sleeps past `timeout_s` | exactly one retry, then failover; wall clock bounded |
| T-05 | Malformed response | stub returns non-JSON / schema-invalid | one repair attempt, then failover; **no** malformed value reaches the engine |
| T-06 | Tool-call failure | tool executor raises | error fed back once; controller marks action unusable; no loop |
| T-07 | Unproductive search | model repeats the same action 3× | 2nd repeat rejected without budget cost; forced `STOP` after 2 failed turns |
| T-08 | Safe stopping | evidence saturated | `STOP` fires; output row still emitted; reason recorded |
| T-09 | Missing dependency | hide `pypdf` | PDFs degrade to `unparsed`, run completes, gap recorded |
| T-10 | Partial PDF text | truncated/corrupt PDF | no exception escapes; partial facts kept with `confidence: low` |
| T-11 | OCR unavailable | vision provider absent **and** no Tesseract | image-dependent findings marked `UNRESOLVED`; **no invented field values** |
| T-12 | Keyless end-to-end | `env -u GEMINI_API_KEY -u OPENROUTER_API_KEY` full run on 32 samples | 32/32 rows, schema-valid, no network attempted |
| T-13 | Secret leak scan | plant a fake key, run packaging scan | scan aborts; `[REDACTED]` in logs; planted value absent from archive |
| T-14 | CSV contract | validate emitted file | exact header `case_id,deletion_status,steps_json`; 518 rows; sorted; one row per `case_id`; statuses in the allowed set; `steps_json` parses |
| T-15 | Step contract | validator over every row | phases ordered FINDING→REMEDIATION→VERIFICATION; `step_no` 1..n contiguous; operations/states from §6.4 only; per-phase sort by operation rank then `system_id`, `resource_id` |
| T-16 | Citation contract | validator over every row | every non-empty `evidence_id` exists in `evidence_files.csv` (or is an `activity_id`/`audit_id` present in the bundle) **and** its capture time ≤ `audit_at`; `COMPLETE` rows cite ≥1; `INCOMPLETE` remediation/verification cite `""` |
| T-17 | Log preservation | hash `log.txt` before/after a run | prefix unchanged; only appends |

### 9.2 Attribution tests — the non-negotiable ones

These are **negative** tests: they assert that weak signals do *not* create ownership. They encode the rule that an activity claim, temporal proximity, or co-location alone is never proof.

| ID | Trap | Expected |
|---|---|---|
| A-01 | Resource appears only in a `DELETE ... SUCCESS` activity row for the right-looking window | link tier `CLAIM_ONLY`; **does not** by itself authorise policy enforcement; gap recorded |
| A-02 | Two subjects' records co-resident in one export, no owner identifiers (the `evidence_92` shape) | **no** cohort inference; both `UNRESOLVED` unless independently anchored |
| A-03 | Decoy identity with near-matching name in the same artifact (`user_8741`, `user_9116`, `user_7204` in `evidence_54`) | never merged into the subject; verdict `DIFFERENT_PERSON` |
| A-04 | Deleted account visible only as a 404 readback with no lookup key (`account_6440`) | `UNRESOLVED` unless a non-claim co-resident record (`audit_record_3737` → `user_21`) or `LINK_RESOURCE_IDENTITY` anchors it |
| A-05 | Historical email in the request (`requested_at` ≠ snapshot time) | resolves via audit log; 3/32 sample cases exercise this |
| A-06 | Model asked to confirm a candidate link with no evidence ids supplied | verdict must be `INSUFFICIENT`; a `SAME_PERSON` with empty `basis_evidence_ids` is rejected by the schema check |

### 9.3 Regression and generalisation tests

- **Regression (32 public cases, `dataset/sample_output.csv`)** — used **only** as a regression signal, never as a lookup table. Baseline to beat: 22/32 status (M2). Target: ≥30/32 status, and step-level exact match ≥60% (the 3.1% baseline is dominated by ordering/noise, so step-level is measured per-field as well as exact).
- **Generalisation (≥3 participant-authored cases, required by §6.8)** — constructed by mutation of public evidence with **new** identifiers, not copied answers: (1) unfamiliar log syntax with a renamed field set; (2) contradictory snapshot vs activity claim; (3) active sync/restore that recreates a deleted record after the workflow reported COMPLETE. These live in `evaluation/custom_cases/` with expected outputs derived by hand from the rules, and are the cases reported in `evaluation_report.md`.
- **Determinism** — the 32-case regression is run twice and the `steps_json` diffed byte-for-byte; any drift is a failure (it would mean temperature, ordering, or dict iteration leaked into output).

**Gate 9.1 (evaluation plan): PASS as a design (T-01…T-17, A-01…A-06 specified). Gate 9.2 (tests executed): NOT RUN — this is a design gate; no production implementation exists to test.**

---

## 10. Final Gate Summary

### 10.1 Gate status

| Gate | Status | Basis |
|---|---|---|
| **A. Provider comparison (Gemini / OpenRouter / Grok)** | **PASS** (comparison) | SDKs import (verified versions); pricing read from official page; OpenRouter catalogue queried live (466 models / 20 free / 17 with tools) |
| A1. Gemini live inference, tools, structured output | **UNVERIFIED** | no key in environment; `/v1beta/models` returns 403 unauthenticated |
| A2. OpenRouter live inference | **UNVERIFIED** | no key; only the public model list was exercised |
| A3. Direct Grok API | **UNVERIFIED** | not investigated — optional, and adds no capability the other two lack |
| **B. Recommended provider configuration** | **PASS** | primary/fallback selected, capability router, error taxonomy, budget caps, usage pass-through defined |
| **C. Local-model feasibility** | **PASS as investigation / BLOCKED as primary** | GTX 1650 4096 MiB + 7.87 GiB RAM measured; 7–8B does not fit; 3–4B fits but is not adequate for 15-field cited output |
| **D. Agent architecture** | **PASS** | three options compared; (c) deterministic engine + bounded LLM assist recommended; multi-agent rejected with reasons |
| **E1. PDF extraction (pypdf)** | **PASS** | all 4 corpus PDFs extract (617–1003 chars each), incl. the `evidence_58` gap from M2 |
| **E2. Local OCR (Tesseract)** | **BLOCKED** | binary absent; `pytesseract` installed but non-functional |
| **E3. Vision API for 11 PNGs** | **UNVERIFIED** | viable free models identified; no call made (no key) |
| **E4. Search / identity / provenance / state-at-`audit_at`** | **PASS** (design) | reuses tested M0–M1 index + ledger; tiered attribution specified |
| **E5. SQLite / FastAPI / agent framework** | **PASS (decision: omit)** | no benefit at 94 files / 4k rows; CLI contract unchanged |
| **F. Execution constraints (network + credentials)** | **UNVERIFIED** | repository silent; keyless run therefore treated as mandatory |
| **G. Project structure** | **PASS** (proposal) | additive map against current tree; entry point preserved; no files moved |
| **H. Security & reliability** | **PASS** (design) | secrets from env, redaction, pre-zip scan, retry/circuit-breaker, safe failure |
| **I. Evaluation plan** | **PASS** (design) | 17 behavioural tests + 6 attribution negative tests, all runnable without keys |
| I2. Tests actually executed for this feature set | **NOT RUN** | no implementation — out of scope for this gate |

### 10.2 Verified findings (reproduced in this session)

1. `google-genai` 2.33.0 and `openai` 3.37.0 install and import; `google-generativeai` is deprecated upstream.
2. Gemini pricing: `gemini-3.8-flash` and `gemini-3.5-flash-lite` are **free of charge** on the free tier; `gemini-4-argon` and `gemini-3.1-pro-preview` are paid-only. Paid Flash rates $0.75/$3.75 per 1M tokens through 2026-12-31.
3. Gemini API rejects unauthenticated model listing with HTTP 403 — no key was present, so no live call was possible.
4. OpenRouter `/api/v1/models` is public: 466 models, 20 free, 17 free models declare tool support, several accept image input.
5. `pypdf` 6.21.2 extracts all 4 PDFs; `tesseract` and `ollama` are absent; 11 PNGs are RGB screenshots with no text layer.
6. Hardware: GTX 1650, **4096 MiB VRAM**, driver 591.74, 7.87 GiB RAM (two independent sources agree).
7. Repository contains **no** rule granting network access or credentials at evaluation time, and the usage-report requirement implies model use is anticipated but not mandatory.

### 10.3 Required user setup actions

| # | Action | Needed for | Cost | Notes |
|---|---|---|---|---|
| 1 | Create a Google AI Studio key; export `GEMINI_API_KEY` in the shell only | primary provider + vision | $0 on free tier | **Never** paste it into chat, code, or `log.txt` |
| 2 | Confirm the free-tier limits visible in AI Studio (RPM/TPM/RPD) | capacity planning for 518 cases | $0 | numbers could not be read statically → still UNVERIFIED |
| 3 | (Optional) `OPENROUTER_API_KEY` | fallback + free vision | $0 | free models only; no paid routing |
| 4 | (Optional) install the Windows Tesseract build | offline OCR of 11 PNGs | $0 | only if grading may be offline and vision is unavailable |
| 5 | Ask organisers whether grading has network/credential access | resolves Gate F | $0 | highest-value open question; design is already safe either way |
| 6 | Approve eventual dependency additions (`pypdf`, `google-genai`, `openai`) | implementation | $0 | installed already; must be optional at runtime |

### 10.4 Unresolved decisions (need user/reviewer input)

| # | Decision | Options | Recommendation |
|---|---|---|---|
| D1 | Default `GHOST_AUDIT_LLM_MODE` for the graded run | `assist` / `off` | `assist` with deterministic fallback, **if** a keyed dry run proves stability; otherwise `off` |
| D2 | Ship the content-addressed LLM cache in `code.zip`? | ship / regenerate | **regenerate** — avoids any appearance of pre-baked answers |
| D3 | PNG strategy | vision API / local Tesseract / both | vision API primary, Tesseract optional |
| D4 | Run a live smoke test with the user's key | yes / no | yes, but only on explicit approval — it consumes real free-tier quota (no charge) |
| D5 | How much of M2 to keep | salvage `state.py` / rewrite | salvage parsers + ledger only; rewrite decision path |

### 10.5 Remaining blockers

| Blocker | Impact | Unblock by |
|---|---|---|
| No credentials in the environment | Gemini/OpenRouter inference, tools, structured output, vision all **UNVERIFIED** | user action 1 (+4) |
| No OCR binary | local reading of 11 PNGs impossible | user action 4, or vision route |
| Evaluation network/credential policy unknown | cannot tune default mode with confidence | user action 5 |
| M2 accuracy 22/32 (68.8%) | current code is not competitive | implementation milestones M1–M5 below |
| Free-tier rate-limit numbers unverified | 518-case run may hit daily quota | measure during first keyed run; add cap + resume |

### 10.6 Revised milestones (supersede those in `design_gate_report.md`)

| Milestone | Deliverable | Acceptance |
|---|---|---|
| **M1** | Evidence store + provenance JSONL + PDF adapter; delete hardcoded `SERVICE_EXPORT_FILES` / `AUTHORITATIVE_SNAPSHOTS` / `SYSTEM_ID_MAP` | all 94 files indexed with provenance; PDFs parsed; 44 existing unit tests still green |
| **M2** | Tiered attribution (`DIRECT`/`CORROBORATED`/`CLAIM_ONLY`/`UNRESOLVED`) + A-01…A-06 negative tests | decoys not merged; `account_6440` resolved only via corroboration; 0 false links on the 32 samples |
| **M3** | Policy obligations + planner + total ordering + blocking validator (T-14…T-16) | 0 schema/ordering/citation violations on 32 samples |
| **M4** | Provider adapters + router + cache + usage ledger (keyed, optional) | T-01…T-08 pass with stub transport; live smoke test recorded |
| **M5** | Bounded investigation controller wired to the four permitted LLM questions | T-07/T-08 pass; per-case calls ≤6; keyless run unaffected |
| **M6** | Regression ≥30/32 status, step-level ≥60%, 3 custom cases, determinism double-run | `evaluation_report.md` filled with measured numbers only |
| **M7** | `usage_report.md` from the real ledger, README, `.env.example`, pre-zip secret scan, package | T-13 passes; archive contains no dataset/keys |

### 10.7 Bottom line

The architecture is settled and cheap to build: **deterministic audit engine + bounded LLM assistance + provider-independent adapters + keyless fallback**. The two things that could still invalidate it are both external and both resolvable by the user: whether grading permits network/credentials (Gate F), and whether a keyed dry run behaves as documented (Gate A1/A2). Neither blocks starting M1, which is entirely offline.

**Scope confirmation:** no production audit code was modified, `output.csv` was not generated, the 518-case run was not executed, nothing was packaged or submitted, and no API key was requested, used, or exposed.