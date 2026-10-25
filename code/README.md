# Ghost Data Still Exists — Hybrid Deletion Audit Agent

This directory contains the implementation for the HackerRank Orchestrate
October 2026 challenge, **Ghost Data Still Exists**.

The implementation is a hybrid deletion-audit agent. Deterministic parsers,
identity rules, audit-time state reconstruction, policy handling, and output
steps are authoritative. A bounded runtime model loop can investigate
deterministic evidence through a closed action menu, while guardrails prevent
model output from deciding ownership, deletion status, absence, citations,
remediation, or final rows. Without usable credentials or network access, the
same deterministic path remains the safe fallback.

## Current status

- Full unit suite: **78 tests passed**.
- Public sample regression: **32/32 status matches**, **7/32 exact step-key
  matches**, and **1/32 full exact-step matches**.
- Evidence inventory: 94 files and 4,011 activity-claim rows.
- JSON, log, text, and SQL evidence parsers are implemented.
- Current JSON collections, service-export blocks, and SQL tables are checked
  by `ghostdata/coverage.py`; new uncovered schema items fail the test suite.
- PDF evidence is text-extracted with `pypdf` and falls back to Tesseract OCR
  through PyMuPDF page rendering when text extraction yields no supported
  identifiers. PNG evidence is OCR-processed with Tesseract. OCR text is
  retained for diagnostics, but only validated identifiers become observations;
  OCR alone never proves ownership, deletion, absence, or completion.
- The controlled 518-case evaluation has been run and produced 518 validated
  rows in the root `output.csv`: 171 `COMPLETE`, 337 `INCOMPLETE`, and 10
  `NOT_APPLICABLE`, with 2,354 total steps.
- A repeat run produced the same SHA-256 output hash, confirming deterministic
  reproducibility.
- Runtime providers are routed Gemini -> OpenRouter -> deterministic fallback.
- Per-case usage can be independently reconciled Gemini -> OpenRouter -> deterministic fallback.
- Runtime investigation tools now return bounded, provenance-preserving
  evidence candidates. Only candidates that exist in the ledger, satisfy the
  audit cutoff, and have a unique deterministic owner link are fed back into
  state reconstruction.
- Output rows now pass a validator before atomic CSV replacement. The validator
  checks the contract header, sorted unique case IDs, JSON shape, allowed
  operation/state pairs, phase ordering, citations, and safe empty evidence
  IDs for proposed remediation.
- The latest `gemini-3.8-flash` probe returned HTTP 429; OpenRouter and Groq
  fallbacks returned HTTP 403. The deterministic path remains available.

The regression result is a correctness baseline, not a submission result.
Activity-only and co-location-only ownership attribution were deliberately
removed because they violate the evidence-attribution rules.

## Folder layout

```text
code/
├── main.py                 # CLI entry point
├── Setup.md                # uv setup, OCR, provider, testing, and CLI guide
├── pyproject.toml          # uv project metadata and dependencies
├── uv.lock                # Reproducible dependency resolution
├── .env.example            # Empty optional provider configuration template
├── .gitignore              # Code-folder secret/cache/runtime exclusions
├── ghostdata/              # Production package
│   ├── csvio.py            # Dataset and policy loaders
│   ├── ledger.py           # Evidence manifest and normalized ledger
│   ├── identities.py       # Current and historical identity resolution
│   ├── matcher.py          # Evidence-to-user ownership matching
│   ├── state.py            # Audit-time state reconstruction
│   ├── absence.py          # Absence and evidence sufficiency checks
│   ├── remediation.py      # Policy-backed ordered steps
│   ├── engine.py           # Case orchestration and serialization
│   └── runtime/            # Optional Gemini/OpenRouter/Groq runtime layer
├── tests/                  # Unit, state, runtime, and output-contract tests
└── evaluation/             # Validator, reports, and diagnostic artifacts
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
   `pdfdocs.py` preserves PDF provenance, invokes Tesseract for PNGs and PDF
   fallback rendering, and emits explicit unreadable observations when OCR is
   unavailable. Install Python dependencies with `uv sync --project code` and
   install the Tesseract engine separately. Set `TESSERACT_CMD` when the
   executable is not on PATH, and set `GHOSTDATA_OCR_LANG` to a `+`-joined
   language list such as `eng+spa`. If requested language data is unavailable,
   the parser records the requested and actually used language and falls back
   to an installed language.
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
   serializes steps into the required JSON shape. `evaluation/validator.py`
   validates every result before `csv.writer` atomically replaces an output.

## Commands

Run commands from the repository root through the locked `uv` environment:

```powershell
uv run --project .\code python -m unittest discover -s code\tests -t code
uv run --project .\code python code\main.py selftest
uv run --project .\code python code\main.py summary
uv run --project .\code python code\main.py validate-samples
uv run --project .\code python code\main.py evaluate-samples
uv run --project .\code python code\main.py diff-samples
uv run --project .\code python code\main.py diff-samples case_26
uv run --project .\code python code\main.py runtime-samples
uv run --project .\code python code\main.py runtime-samples --verify-usage
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

`run_evaluation()` is the controlled writer path. It sorts and validates all
results, requires the request case-ID set, rejects unsupported steps or
citations, and writes through a temporary file before replacement. The final
518-case CLI remains intentionally gated until readiness approval.

`runtime-samples` runs the bounded provider loop for the 32 samples when
credentials are available, then runs the deterministic engine for conclusions.
The runtime loop may suggest only bounded evidence-investigation actions; it
cannot set ownership, deletion status, absence, or final steps. Provider
responses and token metadata are appended to
`code/evaluation/runtime_usage.jsonl` only when a provider call succeeds.
Provider credentials are read from `GEMINI_API_KEY`, `OPENROUTER_API_KEY`, and
`GROQ_API_KEY`. Model names can be changed with the matching `*_MODEL`
variables. `--verify-usage` sends each case's recorded usage ledger to a
Groq-first independent verifier, falling back to OpenRouter and Gemini. The
verifier reconciles arithmetic only; provider-reported token metadata remains
authoritative.

The provider order is Gemini -> OpenRouter -> Groq. Usage verification uses
Groq -> OpenRouter -> Gemini. Credentials and model names are read from
environment variables or the uncommitted `code/.env`; see [`Setup.md`](./Setup.md) and
[`.env.example`](./.env.example). The runtime path is explicit and bounded; the deterministic path remains the
safe fallback when live provider access fails.

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
[`TODO.md`](../TODO.md). Task 2's intent contract is
dataset-backed: exactly `case_533` through `case_542` are non-authorized in
the full request file, while all 32 public samples are treated as deletion
audits. The next milestone is to repair authoritative snapshot semantics and
represent PDF/PNG extraction gaps explicitly, then refine remediation ordering
and add a non-destructive output validator before any full evaluation run.

Do not generate the final `output.csv`, package the submission, or run the
518-case evaluation until the readiness checks in `TODO.md` are complete.
