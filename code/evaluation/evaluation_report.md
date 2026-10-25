# Evaluation Report

## Controlled full evaluation

The full evaluation was run through `main.py evaluate-full` after the
readiness checks passed.

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

The challenge dataset does not provide a separate expected output for all 518
cases, so a full-case accuracy percentage cannot be computed from the
repository alone. Public-sample accuracy remains the available accuracy
baseline: 32/32 statuses, 7/32 step-key matches, and 1/32 full exact-step
matches.

See `usage_report.md` for runtime provider usage. The deterministic full run
does not require model calls.
