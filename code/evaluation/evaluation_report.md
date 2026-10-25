# Evaluation Report

## Controlled full evaluation

The full evaluation was run through `main.py evaluate-full` after the
readiness checks passed. All provider routing uses Gemini -> OpenRouter ->
deterministic fallback; Groq has been removed from active chains.

| Metric | Result |
|---|---:|
| Validated output rows | 518 |
| Expected request rows | 518 |
| Output contract validation | Passed |
| Status accuracy against a full expected-output file | Not available |
| Total steps | 2,354 |
| `COMPLETE` rows | 171 |
| `INCOMPLETE` rows | 337 |
| `NOT_APPLICABLE` rows | 10 |
| Reproducibility | Passed; identical SHA-256 hashes |
| Structural validation errors | 0 |

The challenge dataset does not provide a separate expected output for all 518
cases, so a full-case accuracy percentage cannot be computed from the
repository alone. Public-sample accuracy remains the available accuracy
baseline: 32/32 statuses, 1/32 step-key matches, and 1/32 full exact-step
matches.

See `usage_report.md` for runtime provider usage. The deterministic full run
does not require model calls.

## Independent structural validation of output.csv

An independent validator checked all required structural conditions:

| Check | Result |
|---|---|
| CSV parses with standard parser | Passed |
| Header matches `case_id,deletion_status,steps_json` | Passed |
| Exactly 518 data rows | Passed |
| All 518 case IDs present exactly once | Passed |
| No unexpected case IDs | Passed |
| Rows correctly sorted by case_id | Passed |
| Every status is allowed (COMPLETE/INCOMPLETE/NOT_APPLICABLE) | Passed |
| Every steps_json cell parses as JSON | Passed |
| Every steps_json value is an array | Passed |
| Every step has required keys and correct types | Passed |
| Step numbering is sequential from 1 | Passed |
| Phase and operation values are valid | Passed |
| Evidence references satisfy project rules | Passed |
| Step ordering follows specification (FINDING->REMEDIATION->VERIFICATION) | Passed |
| COMPLETE/INCOMPLETE/NOT_APPLICABLE semantics | Passed |
| No credentials, stack traces, or debug messages | Passed |

## Custom evaluation tests (3)

The following custom tests were run as part of finalization:

1. **Provider routing test**: Verified Gemini is tried first, OpenRouter is used
   when Gemini fails, Groq is absent from both `ProviderRouter` and
   `UsageVerifier` default orders, and both providers failing raises
   `RuntimeModelError` without referencing Groq. (9 tests in `test_runtime.py`)

2. **Secret redaction test**: Verified API keys and request URLs are never
   included in provider error messages. Gemini query-string keys are redacted.
   (1 test in `test_runtime.py`)

3. **Output round-trip test**: Verified that `write_results` produces a CSV that
   survives a full parse/validate cycle with zero structural errors across all
   518 rows. (Independent `validate_output.py` script)

## Important failures and limitations

- **Public sample exact-step matches**: Only 1/32 full exact-step matches.
  The remaining step-level gaps reflect evidence that is not safely available
  in the participant-facing dataset (activity-only and co-location-only
  ownership attribution were deliberately removed because they violate the
  evidence-attribution rules). These gaps do not affect status accuracy
  (32/32).

- **Groq provider**: Groq returns HTTP 403 error code 1010 (account/auth/
  permissions level). Groq has been removed from active fallback and usage
  verification chains. This is not a code defect; it requires account-side
  resolution.

- **Full-case accuracy**: Cannot be computed from the repository alone because
  the challenge dataset does not provide expected output for all 518 cases.

## Improvements made during finalization

- Removed Groq from all active provider fallback and usage-verification chains
  (`ProviderRouter`, `UsageVerifier`, `.env.example`, README).
- Added 9 provider-routing and secret-redaction tests to `test_runtime.py`.
- Simplified provider documentation to reflect Gemini -> OpenRouter ->
  deterministic fallback ordering.
- Ran full 518-case evaluation and generated validated root `output.csv`.
- Added independent structural validation of `output.csv` (0 errors).

## Verification status

- Verified results: 91/91 unit tests pass; 32/32 public sample status matches;
  518/518 output rows structurally valid; 0 validation errors.
- Assumptions: Full-case accuracy cannot be verified without hidden canonical
  answers; Groq failure is account-side and outside code scope.
