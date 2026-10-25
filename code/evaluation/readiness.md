# Evaluation Readiness

## Readiness checks

Run on 2026-10-25 with the locked `uv` environment:

| Check | Result |
|---|---|
| Unit suite | 91/91 passed |
| CLI self-test | Passed |
| Evidence summary | 94 evidence files parsed; 4,011 activity rows loaded |
| Sample evidence validation | Passed; 29/33 cited evidence IDs recovered within audit cutoffs |
| Public sample statuses | 32/32 matched |
| Public sample exact step-key matches | 1/32 |
| Public sample full exact-step matches | 1/32 |
| Output validation and atomic writer | Covered by passing validator tests |
| Provider routing (Gemini first, OpenRouter fallback, no Groq) | Verified; 9 routing/redaction tests pass |
| Independent structural validation of output.csv | 0 errors across 518 rows |

## Phase 1 integration verification

A mocked LLM response was traced through the complete pipeline using a public
sample. The initial deterministic view intentionally omitted one valid
owner-linked observation. The mock requested a search for that resource, the
tool returned its ledger-backed provenance, candidate validation accepted it,
state reconstruction included it, and the final validator accepted the
result.

- Before: one security verification step.
- After: the original security verification plus one account absence
  verification step.
- Fabricated evidence ID: rejected.
- Activity-only resource: rejected.
- Real post-audit owner-linked observation: rejected.
- Final output validation: passed.

This proves the bridge can change a plan when a valid deterministic candidate
is discovered. It does not prove that a live provider improves public-sample
accuracy.

## Readiness decision

The output contract and deterministic execution path are ready for the
controlled full run. Exact-step and citation coverage are not perfect, so the
full-run report must distinguish validated output integrity from sample
step-level accuracy. Activity-only ownership and unsupported absence claims
remain intentionally unresolved.

Provider routing is simplified to Gemini -> OpenRouter -> deterministic
fallback. Groq has been removed from active chains due to HTTP 403 error code
1010 (account-side).

The controlled command is:

```powershell
uv run --project .\code python code\main.py evaluate-full --output output.csv
```

The command validates the complete request set and writes the CSV atomically.

## Full-run result

The controlled run completed successfully:

- Rows: 518
- Steps: 2,354
- `COMPLETE`: 171
- `INCOMPLETE`: 337
- `NOT_APPLICABLE`: 10
- Reproducibility: passed; two output files had the same SHA-256 hash
