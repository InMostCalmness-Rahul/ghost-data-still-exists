# TODO

Legend: `[x]` completed, `[ ]` pending, `[~]` partially complete or blocked.

## Status

- [x] Critical-fix batch implemented.
- [x] Full unit suite passes: 54 tests.
- [x] Code folder reorganized; generated caches and the empty evaluation placeholder removed.
- [x] `code/README.md` maintained with architecture and commands.
- [ ] Public sample regression reaches the required correctness level: current baseline is 19/32 status matches and 1/32 exact-step match.
- [ ] Final 518-case evaluation is authorized and run.
- [ ] Root `output.csv` is generated and validated.
- [ ] Submission package and required evaluation/usage reports are complete.

## 1. Critical Fixes

### 1. [x] Remove unsupported resource attribution
- **Why:** Activity claims, timestamps, shared systems, co-location, and content-only identifiers are not ownership proof.
- **Files:** `code/ghostdata/engine.py`, `code/ghostdata/matcher.py`, `code/ghostdata/models.py`, `code/tests/test_matcher.py`.
- **Done when:** Activity-only, temporal-only, same-system, same-file, and content-only identifiers cannot bind a resource; direct owner-role references still resolve; negative tests pass.
- **Result:** Completed and validated by matcher tests and the full suite.

### 2. [x] Make deletion intent authorization safe
- **Why:** Unmatched text previously defaulted to deletion authorization.
- **Files:** `code/ghostdata/intent.py`, `code/tests/test_classify.py`.
- **Done when:** Explicit deletion requests remain authorized; access, correction, export, opt-out, vague, and unsupported requests are not authorized.
- **Result:** Completed and validated by intent tests and the full suite.

### 3. [~] Correct audit-time state and absence semantics
- **Why:** State selection, activity claims, incomplete snapshots, and process-state handling affect whether deletion is truly proven.
- **Files:** `code/ghostdata/state.py`, `code/ghostdata/absence.py`, `code/ghostdata/models.py`, related tests.
- **Done when:** Evidence ranking is deterministic; future evidence is excluded; claims never prove absence; complete, partial, empty, and unsupported snapshots are distinguished; process states remain separate from record absence.
- **Completed:** Deterministic ranking, audit cutoffs, claim handling, and distinct `DISABLED`/`BLOCKED` states.
- **Pending:** Authoritative snapshot completeness and multimodal evidence handling.

### 4. [~] Ensure complete policy-driven remediation
- **Why:** The planner can still omit, duplicate, or misorder steps and needs broader policy coverage.
- **Files:** `code/ghostdata/remediation.py`, `code/ghostdata/engine.py`, `code/ghostdata/csvio.py`, related tests.
- **Done when:** Retention, legal hold, tombstone, delete, redact, anonymize, backup, and data-flow rules are applied from the dataset policy; steps are justified, allowed, unique, and correctly ordered.
- **Completed:** Policy loading from `dataset/deletion_rules.csv`; focused backup and data-flow behavior.
- **Pending:** Complete step ordering and all policy combinations.

## 2. Next Steps

### 5. [ ] Add PDF evidence extraction without unnecessary dependencies
- **Why:** Four PDFs are reported as text-extractable, but the current ledger emits no PDF observations.
- **Files:** `code/ghostdata/ledger.py`, a PDF parser module if needed, `code/ghostdata/models.py`, parser tests.
- **Done when:** Supported PDFs produce provenance-preserving observations with correct file IDs and timestamps, or are explicitly reported unavailable; audit-time tests pass.

### 6. [ ] Represent PNG/OCR limitations explicitly
- **Why:** PNG files must not silently appear equivalent to evidence proving absence.
- **Files:** `code/ghostdata/ledger.py`, `code/ghostdata/engine.py`, `code/ghostdata/absence.py`, related tests.
- **Done when:** Screenshot-dependent evidence is marked unreadable or unresolved and cannot produce a false `COMPLETE` result.

### 7. [ ] Build a non-destructive output validator
- **Why:** The final contract needs centralized validation before evaluation or submission.
- **Files:** New `code/evaluation/validator.py`, validator tests.
- **Done when:** The validator rejects malformed headers, missing/extra cases, invalid statuses or steps, bad numbering/order, invalid citations, and incorrect `NOT_APPLICABLE` rows.

### 8. [ ] Build non-writing regression diagnostics
- **Why:** Current regression measures status and exact steps but not all attribution, citation, field, and sequence failures.
- **Files:** `code/tests/test_regression_m2.py`, new `code/evaluation/regression.py`, diagnostic tests.
- **Done when:** A 32-case run reports status, exact-step, field, ordering, attribution, and citation mismatches without overwriting artifacts.

### 9. [~] Connect and verify the intended CLI path
- **Why:** The documented CLI does not yet expose the complete M2 evaluation pipeline.
- **Files:** `code/main.py`, `code/ghostdata/engine.py`, CLI tests.
- **Done when:** A controlled sample invocation runs the intended deterministic pipeline, validates output, and cannot accidentally run the 518-case evaluation.
- **Completed:** Added `python code/main.py evaluate-samples`; it runs all 32 public samples without writing output and reports status, exact-step, and full-match counts.
- **Pending:** Connect the future output validator and final validated-output path.

### 10. [ ] Establish final-run readiness checks
- **Why:** A reproducible go/no-go review is required before the full evaluation.
- **Files:** `code/evaluation/`, `code/tests/`, `code/main.py`, documentation.
- **Done when:** Unit tests, targeted tests, all 32 samples, output validation, citation validation, and CLI checks pass with remaining blockers documented.

### 10a. [x] Keep the code folder free of generated artifacts
- **Why:** Generated caches and empty placeholders should not obscure the implementation or enter a submission package.
- **Files:** `code/`, packaging instructions.
- **Done when:** Only source, tests, documentation, reports, and intentionally retained diagnostics remain under `code/`.
- **Result:** Completed for the current tree. Repeat cleanup before packaging.

## 3. Optional Improvements

### 11. [ ] Add contradiction and uncertainty reporting
- **Why:** Conflicting observations and unresolved ownership should remain visible instead of becoming silent guesses.
- **Files:** `code/ghostdata/models.py`, `code/ghostdata/state.py`, `code/ghostdata/engine.py`, tests.
- **Done when:** Contradictions and unresolved evidence are represented in diagnostics and cannot silently produce `COMPLETE`.

### 12. [ ] Add deterministic investigation budgets and duplicate-search guards
- **Why:** Bounded investigation prevents repeated searches and non-deterministic stopping behavior.
- **Files:** New investigation utility under `code/ghostdata/`, `code/ghostdata/engine.py`, tests.
- **Done when:** Repeated searches are bounded, stopping conditions are deterministic, and the engine remains offline and dependency-light.

### 13. [ ] Add optional provider-independent LLM interfaces
- **Why:** The approved hybrid architecture allows future bounded assistance, but no provider is required for deterministic correctness.
- **Files:** Optional provider interface/configuration modules, documentation, usage reporting.
- **Done when:** LLM assistance is optional, credentials come only from environment variables, deterministic validation remains authoritative, and keyless execution uses the offline path.

### 14. [ ] Complete evaluation and usage documentation
- **Why:** Submission requires reproducible evaluation and usage reports.
- **Files:** `code/evaluation/evaluation_report.md`, `code/evaluation/usage_report.md`.
- **Done when:** Reports contain only reproducible final-run metrics, custom cases, failure analysis, and actual model/token/cost details where applicable.

## Recommended Starting Point

1. [ ] **Repair authoritative snapshot and multimodal evidence handling** — the parser still omits PDFs/PNGs and cannot reliably distinguish absent data from missing extraction.
2. [ ] **Refine policy-driven remediation and deterministic ordering** — remaining public sample failures include step and state correctness issues.
3. [ ] **Add output validation and non-writing regression diagnostics** — prevent malformed or unsupported results from reaching the final run.

These three pending tasks build on the completed ownership and intent safeguards and can proceed without provider integrations or the final 518-case evaluation.
