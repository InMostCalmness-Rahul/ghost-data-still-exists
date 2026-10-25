# Usage Report

## Controlled full evaluation (final 518-case run)

| Metric | Value |
|---|---|
| Primary provider | Gemini (`gemini-3.5-flash-lite`, from `GEMINI_MODEL`) |
| Fallback provider | OpenRouter (`openrouter/free`, from `OPENROUTER_MODEL`) |
| Groq | Removed from active chains (HTTP 403 error code 1010, account-side) |
| Actual successful provider calls during final evaluation | 0 |
| Failed provider calls during final evaluation | 0 |
| Actual prompt tokens | 0 |
| Actual completion tokens | 0 |
| Actual total tokens | 0 |
| Provider cost | $0.00 |
| Deterministic fallback cases | 518/518 |
| Runtime mode | Deterministic engine with optional model assistance disabled |
| Live model assistance during final run | None |

The full 518-case output was produced entirely by the deterministic engine.
No live model calls were made during the final evaluation, so no tokens were
consumed and no provider cost was incurred. No token estimates were fabricated.

## Provider availability (from live probes)

- Gemini: Available — returns usable responses (model `gemini-3.5-flash-lite`)
- OpenRouter: Available — returns usable responses (model `openrouter/free`)
- Groq: Unavailable — HTTP 403 error code 1010 (account/auth/permissions)

## Usage tracking

Usage accounting is separate from provider selection. The `UsageLedger` records
actual provider, model, and token usage from successful calls. When no live
LLM call occurs, usage is 0 and is reported honestly as such. No token counts
or costs are fabricated.

## Phase 1 implementation status

Runtime tool results are retained by the agent and consumed by the engine.
Candidate observations are accepted only when present in the deterministic
ledger, satisfy the case audit cutoff, and have a unique owner-role identity
link. No LLM claim alone can establish ownership, deletion, absence,
remediation, or completion.
