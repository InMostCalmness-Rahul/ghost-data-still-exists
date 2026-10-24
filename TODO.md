# Ghost Data Still Exists — Project Checklist

This is the single project checklist.  
`[x]` done, `[~]` partly done or blocked, `[ ]` not started.

## Current status

- [x] The solution remains deterministic and offline-first.
- [x] No files under `dataset/` were changed.
- [x] Full unit suite: **62 tests passed**.
- [x] Public sample status matches: **32/32**.
- [ ] Public sample exact-step matches: **0/32**.
- [ ] The full 518-case evaluation has not been run.
- [ ] Root `output.csv` has not been generated.
- [ ] The submission package and final evaluation reports have not been created.

## Sequential work checklist

### 1. Add a non-writing sample diff diagnostic — [x] Done

- **Why:** Later fixes needed a quick way to separate status problems from missing, extra, or differently ordered steps.
- **Files:** `code/evaluation/regression.py`, `code/main.py`, regression tests.
- **Completed:** Added `diff-samples [case_ids...]`. It compares expected and actual status and step keys using phase, system, resource, operation, and state. Selected cases also show complete step details, including evidence IDs. It never writes output files.
- **Done when:** The command runs for all 32 samples and selected cases without changing artifacts.

### 2. Fix deletion-intent classification — [x] Done

- **Why:** This queue is a deletion-audit queue, but explicit access, correction, export, opt-out, and other non-deletion requests must remain out of scope.
- **Files:** `code/ghostdata/intent.py`, `code/tests/test_classify.py`.
- **Completed:** Deletion is the default for this queue; explicit non-deletion language wins. Curly apostrophes and the required multilingual and narrow-scope cues are handled. Dataset tests confirm that only `case_533` through `case_542` are unauthorized, while all public samples are authorized.
- **Done when:** Intent tests pass without using case-specific prediction shortcuts.

### 3. Correct audit-time state and privacy semantics — [~] Partly done

- **Why:** Activity claims are not proof, future evidence must be ignored, and already-redacted or anonymized records must not be reported as exposed.
- **Files:** `code/ghostdata/state.py`, `code/ghostdata/absence.py`, `code/ghostdata/json_records.py`, `code/ghostdata/sqlsnapshots.py`, `code/ghostdata/models.py`, related tests.
- **Completed:** Deterministic evidence ranking, audit-time cutoffs, claim-versus-evidence handling, explicit `DISABLED` and `BLOCKED` process states, identifier-presence handling, and redacted/anonymized semantics for supported JSON, service-export, SQL, and log records.
- **Still needed:** Complete authoritative-snapshot coverage and justified absence checks for activity-only candidates.
- **Done when:** Complete, partial, empty, unsupported, redacted, anonymized, and unknown states are distinct and tested; unknown state never proves `COMPLETE`.

### 4. Apply all policy rules and produce ordered remediation — [~] Partly done

- **Why:** Every relevant record and recreation risk needs the correct finding, remediation, and later verification in a deterministic order.
- **Files:** `code/ghostdata/remediation.py`, `code/ghostdata/engine.py`, `code/ghostdata/csvio.py`, related tests.
- **Completed:** Dataset policy loading, retention and legal-hold handling, tombstone treatment, backup restore handling, and data-flow disabling are represented.
- **Still needed:** Broader policy combinations, complete remediation coverage, and exact phase/operation ordering.
- **Done when:** Every emitted step is policy-supported, unique, correctly ordered, and either evidence-backed or correctly left as a future action.

### 5. Cover every supported evidence schema — [x] Done

- **Why:** An unrecognized collection, table, owner field, or presence field can silently hide personal data.
- **Files:** `code/ghostdata/coverage.py`, `code/ghostdata/json_records.py`, `code/ghostdata/state.py`, `code/ghostdata/engine.py`, schema coverage tests.
- **Completed:** Inventoried observed JSON collections, service blocks, and SQL tables. Added a coverage contract that fails when a new unsupported collection or table appears. Added `owner_email`, export presence handling, standalone JSON source fallback, and `export_service` normalization. Case 08 now reports the expected `export_001` finding.
- **Done when:** The coverage test continues to fail loudly for newly observed unsupported schemas.

### 6. Restore safe absence verification — [~] Partly done and currently blocked

- **Why:** Activity rows can nominate candidate resources, but they cannot prove ownership, deletion, or absence.
- **Files:** `code/ghostdata/matcher.py`, `code/ghostdata/absence.py`, `code/ghostdata/engine.py`, related tests.
- **Completed:** `LINK_RESOURCE_IDENTITY` activity is retained only as a diagnostic candidate. `DELETE_RECORD` results never establish ownership or absence. Existing ownership safeguards remain green.
- **Blocked by:** `account_001`, `account_002`, and `account_008` appear only in activity claims in the inspected participant-visible evidence. No corroborating owner-linked observation or explicit identity-bearing link was found, so their expected absence steps cannot be emitted safely.
- **Done when:** A candidate has both a grounded owner link and an authoritative same-system snapshot at or before `audit_at`; the absence step cites that snapshot. Otherwise it remains unresolved and is not emitted.

### 7. Handle PDF and PNG evidence explicitly — [~] Partly done

- **Why:** Business documents and screenshots must not silently disappear or be treated as proof when they cannot be read.
- **Files:** `code/ghostdata/pdfdocs.py`, `code/ghostdata/ledger.py`, `code/ghostdata/models.py`, `code/ghostdata/engine.py`, ledger tests.
- **Completed:** Optional `pypdf` extraction preserves PDF file IDs and capture times. `evidence_58` now supports the `support_001` finding. All 11 PNGs are represented as explicit `UNREADABLE` observations and cannot silently prove completion.
- **Still needed:** Determine whether any remaining screenshot-dependent cases need a supported OCR path, without weakening the unreadable-evidence safeguard.
- **Done when:** Every supported PDF produces provenance-preserving observations, every unreadable PNG remains explicit, and unreadable evidence cannot produce false `COMPLETE`.

### 8. Investigate remaining public-sample differences — [~] Partly done

- **Why:** Matching statuses is not enough; missing findings, remediation steps, verification steps, citations, states, and ordering still affect solution quality.
- **Files:** `code/evaluation/regression.py`, `code/ghostdata/classify.py`, `code/ghostdata/engine.py`, `code/ghostdata/remediation.py`, related tests.
- **Completed:** Added grouped non-writing diagnostics and fixed the general 64-character hexadecimal hash rule for email-shaped fields. This raised status matches to 32/32 without case-specific shortcuts.
- **Still needed:** Group and fix remaining exact-step differences by general cause: candidate absence evidence, replica drift, historical identity, policy coverage, verification coverage, citations, and ordering.
- **Done when:** Each change has a regression test, all 32 statuses remain correct, and exact-step accuracy improves as far as participant-visible evidence allows.

### 9. Build a safe output validator and writer — [ ] Pending

- **Why:** A malformed CSV or unsupported step can invalidate an otherwise correct audit.
- **Files:** New `code/evaluation/validator.py`, `code/ghostdata/engine.py`, `code/main.py`, validator tests.
- **To do:** Write CSV using `csv.writer`; validate the exact header, row count, sorted unique case IDs, statuses, JSON arrays, step numbering, allowed phase/operation/state combinations, deterministic ordering, citation IDs, empty evidence IDs for proposed work, and `COMPLETE` verification-only rows. Make multi-user identity resolution deterministic or explicitly flag conflicts.
- **Done when:** Deliberately malformed outputs are rejected, and a CSV round trip preserves every row and step.

### 10. Establish readiness, then run the final evaluation — [ ] Pending and not yet authorized

- **Why:** The full run should happen only after correctness and output safety checks are reproducible.
- **Files:** `code/evaluation/`, `code/tests/`, `code/main.py`, root `README.md`, `code/README.md`, `TODO.md`.
- **To do:** Run unit tests, validator dry-run checks, public-sample evaluation, and CLI checks; record real results in `code/evaluation/readiness.md`. Only after readiness is approved, add and run the controlled 518-case command that validates before writing root `output.csv`. Then create the required evaluation and usage reports, clean `__pycache__`, package `code.zip`, and make documentation agree.
- **Done when:** There are exactly 518 validated rows, the output is reproducible, required reports are complete, and the package contains no dataset, virtual environment, nested archive, or generated cache.
- **Important restriction:** Do not run the 518-case evaluation, generate `output.csv`, or package the submission before this checklist reaches the readiness milestone.

### 11. Optional: add contradiction and uncertainty reporting — [ ] Pending

- **Why:** Conflicting observations and unresolved ownership should remain visible instead of becoming silent guesses.
- **Files:** `code/ghostdata/models.py`, `code/ghostdata/state.py`, `code/ghostdata/engine.py`, tests.
- **Done when:** Contradictions and unresolved evidence appear in diagnostics and cannot silently produce `COMPLETE`.

### 12. Optional: add bounded investigation guards — [ ] Pending

- **Why:** Deterministic search limits prevent repeated searches and unpredictable stopping behavior.
- **Files:** A focused investigation utility under `code/ghostdata/`, `code/ghostdata/engine.py`, tests.
- **Done when:** Repeated searches are bounded, stopping rules are deterministic, and the offline path remains dependency-light.

### 13. Optional: add a provider-independent LLM interface — [ ] Deferred

- **Why:** A bounded future interface could assist with ambiguous intent or OCR, but it is not needed for deterministic correctness.
- **Files:** Optional `code/ghostdata/llm/` interface/configuration, documentation, usage reporting.
- **Done when:** LLM use is optional, credentials come only from environment variables, calls are cached and measured, and keyless execution remains fully functional.

### 14. Optional: complete evaluation and usage documentation — [ ] Pending

- **Why:** The submission requires reproducible accuracy and usage reporting.
- **Files:** `code/evaluation/evaluation_report.md`, `code/evaluation/usage_report.md`.
- **Done when:** Reports contain only measured final-run metrics, custom cases, failure analysis, and actual provider/model/token/cost details—or explicitly record zero model calls.

## Recommended starting point

1. [ ] **Build the output validator and safe writer (Task 9):** it prevents malformed or unsupported results from reaching later evaluation.
2. [ ] **Investigate exact-step differences (Task 8):** use the existing diagnostics to improve missing verification and remediation steps without weakening ownership safeguards.
3. [ ] **Finish readiness checks (Task 10):** only after validation and sample behavior are stable should the controlled 518-case run be considered.
