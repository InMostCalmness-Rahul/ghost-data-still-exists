# Ghost Data Still Exists — Deterministic Audit Engine

This directory contains the implementation for the HackerRank Orchestrate
October 2026 challenge, **Ghost Data Still Exists**.

The current implementation uses a deterministic, offline-first pipeline. It
does not require an LLM, external API, network access, or credentials.
Provider integration is intentionally deferred until deterministic evidence,
policy, and output validation are reliable.

## Current status

- Full unit suite: **58 tests passed**.
- Public sample regression: **32/32 status matches** and **0/32 exact-step matches**.
- Evidence inventory: 94 files and 4,011 activity-claim rows.
- JSON, log, text, and SQL evidence parsers are implemented.
- Current JSON collections, service-export blocks, and SQL tables are checked
  by `ghostdata/coverage.py`; new uncovered schema items fail the test suite.
- PDF evidence is text-extracted with optional `pypdf` when available.
  PNG evidence is represented explicitly as `UNREADABLE`; no screenshot fact
  is inferred without OCR.
- The final 518-case evaluation has not been run.
- The root `output.csv` has not been generated.

The regression result is a correctness baseline, not a submission result.
Activity-only and co-location-only ownership attribution were deliberately
removed because they violate the evidence-attribution rules.

## Folder layout

```text
code/
├── main.py                 # CLI entry point
├── ghostdata/              # Production package
│   ├── csvio.py            # Dataset and policy loaders
│   ├── ledger.py           # Evidence manifest and normalized ledger
│   ├── identities.py       # Current and historical identity resolution
│   ├── matcher.py          # Evidence-to-user ownership matching
│   ├── state.py            # Audit-time state reconstruction
│   ├── absence.py          # Absence and evidence sufficiency checks
│   ├── remediation.py      # Policy-backed ordered steps
│   └── engine.py           # Case orchestration and serialization
├── tests/                  # Unit and public-sample regression tests
└── evaluation/             # Design reports and diagnostic artifacts
```

Generated Python caches (`__pycache__`) are intentionally excluded from the
source tree. The empty starter `evaluation/main.py` was removed because it
contained no executable evaluation logic; evaluation code belongs in dedicated
modules once the validator and non-writing diagnostics are implemented.

## Architecture

The pipeline is organized into these layers:

1. **Input loading** — `csvio.py` reads requests, identities, audit history,
   activity claims, and deletion policy.
2. **Evidence parsing** — format-specific parsers normalize supported evidence
   into `Observation` records and explicitly classify identifiable,
   redacted, anonymized, and unknown privacy states.
   `pdfdocs.py` preserves PDF provenance and emits explicit unreadable PNG
   observations when OCR is unavailable.
   Install `pypdf` in environments where PDF extraction is not already
   available; without it, the ledger records the PDF as unavailable rather than
   silently treating it as evidence.
3. **Evidence ledger** — `ledger.py` preserves file provenance and applies
   audit-time filtering.
4. **Identity resolution** — `identities.py` resolves current and historical
   identifiers to stable user IDs.
5. **Ownership matching** — `matcher.py` binds resources only through
   owner-role identity references. Activity claims and co-location remain
   diagnostic leads, not ownership proof. Hash-shaped values in identity
   fields are normalized as `email_hash` references instead of being
   misread as email addresses.
6. **Intent classification** — `intent.py` treats the deletion-audit queue as
   deletion-authorized by default, while explicit non-deletion or narrow-scope
   cues always override deletion vocabulary. Curly apostrophes are normalized
   before matching.
7. **State and absence analysis** — `state.py` and `absence.py` reconstruct
   evidence-backed state at `audit_at`. Redacted records are distinct from
   anonymized analytics records, and unknown privacy state remains `UNKNOWN`.
   Activity success claims do not prove absence.
8. **Policy and remediation** — `remediation.py` loads actions from
   `dataset/deletion_rules.csv` and creates allowed findings, remediation, and
   verification steps.
9. **Case orchestration** — `engine.py` evaluates individual cases and
   serializes steps into the required JSON shape.

## Commands

Run commands from the repository root:

```powershell
python -m unittest discover -s code/tests -t code
python code/main.py selftest
python code/main.py summary
python code/main.py validate-samples
python code/main.py evaluate-samples
python code/main.py diff-samples
python code/main.py diff-samples case_26
```

The first command runs the full test suite. `summary` parses the evidence tree.
`validate-samples` writes the M1 diagnostic file
`code/evaluation/sample_validation_m1.json`.
`evaluate-samples` runs the deterministic M2 decision engine against the 32
public samples and prints status, exact-step, and full-match counts. It does
not write an output file. It returns a non-zero exit code until every sample
matches, so it can be used as a readiness check.
`diff-samples` prints grouped expected-versus-actual step-key differences.
Passing case IDs also prints the complete expected and actual step objects,
including evidence IDs. It never writes files.

The current CLI intentionally does not run the final 518-case evaluation.
The M2 engine can be exercised by the public regression module without
overwriting submission artifacts:

```powershell
$env:PYTHONPATH = "$PWD\code"
python -c "from code.tests.test_regression_m2 import run_regression; r=run_regression(); print(sum(x.status_match for x in r), '/', len(r))"
```

## Evidence and policy rules

- Only participant-facing files under `dataset/` may be used for predictions.
- `reported_status` and activity results are claims, not proof.
- Evidence after `audit_at` is excluded.
- Owner-role references can establish resource ownership; content-only
  identifiers cannot.
- Retention, legal holds, tombstones, deletion, redaction, anonymization,
  backup, and data-flow behavior must follow `dataset/deletion_rules.csv` and
  the challenge contract.
- Proposed remediation and future verification steps use an empty
  `evidence_id`.

## Remaining work

The prioritized work is tracked in the repository-root
[`TODO.md`](../TODO.md), and the ordered implementation plan is preserved in
[`COPILOT_TASKS.md`](../COPILOT_TASKS.md). Task 2's intent contract is
dataset-backed: exactly `case_533` through `case_542` are non-authorized in
the full request file, while all 32 public samples are treated as deletion
audits. The next milestone is to repair authoritative snapshot semantics and
represent PDF/PNG extraction gaps explicitly, then refine remediation ordering
and add a non-destructive output validator before any full evaluation run.

Do not generate the final `output.csv`, package the submission, or run the
518-case evaluation until the readiness checks in `TODO.md` are complete.
