# Evaluation Readiness

## Readiness checks

Run on 2026-10-25 with the locked `uv` environment:

| Check | Result |
|---|---|
| Unit suite | 76/76 passed |
| CLI self-test | Passed |
| Evidence summary | 94 evidence files parsed; 4,011 activity rows loaded |
| Sample evidence validation | Passed; 29/33 cited evidence IDs recovered within audit cutoffs |
| Public sample statuses | 32/32 matched |
| Public sample exact step-key matches | 7/32 |
| Public sample full exact-step matches | 1/32 |
| Output validation and atomic writer | Covered by passing validator tests |

## Readiness decision

The output contract and deterministic execution path are ready for the
controlled full run. Exact-step and citation coverage are not perfect, so the
full-run report must distinguish validated output integrity from sample
step-level accuracy. Activity-only ownership and unsupported absence claims
remain intentionally unresolved.

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
