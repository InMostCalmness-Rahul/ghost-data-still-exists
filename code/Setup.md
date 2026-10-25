# Ghost Data Still Exists — Setup Guide

This guide explains how to install, configure, test, and run the project.
Commands are written for Windows PowerShell and should be run from the
repository root:

```powershell
cd C:\path\to\hackerrank-orchestrate-october26
```

The project is a command-line application. It does not start an HTTP server or
require a web framework.

## 1. Requirements

### Required

- Windows, macOS, or Linux
- Python 3.12 or newer
- Access to the repository's `dataset/` directory
- `uv` 0.12 or newer
- Dependencies declared in [`pyproject.toml`](./pyproject.toml)

### Required for image OCR

- Tesseract OCR 5.x
- Tesseract language data for the languages used by the evidence

### Optional for runtime model assistance

- A Gemini API key
- An OpenRouter API key
- A Groq API key
- Network access to the selected provider

Runtime model assistance is optional. The deterministic engine still runs
without network access, credentials, or provider SDKs.

## 2. Python environment

Create and synchronize the project environment with `uv`:

```powershell
uv sync --project .\code
```

Run commands through the locked environment:

```powershell
uv run --project .\code python --version
```

`uv.lock` records the resolved versions. Do not install project dependencies
with `pip`; `requirements.txt` remains only as a legacy compatibility list for
tools that require that format.

The Python dependencies are:

| Package | Purpose |
|---|---|
| `Pillow` | Reads PNG screenshots for OCR |
| `pypdf` | Extracts text from PDFs |
| `pytesseract` | Python bridge to Tesseract |
| `PyMuPDF` | Renders PDF pages for OCR fallback |
| `python-dotenv` | Loads the uncommitted `code/.env` for CLI runs |

## 3. Install Tesseract OCR

### Windows with winget

```powershell
winget install --id tesseract-ocr.tesseract --exact `
  --source winget --accept-source-agreements `
  --accept-package-agreements
```

Verify the installation:

```powershell
tesseract --version
tesseract --list-langs
```

If `tesseract` is not on `PATH`, configure the executable explicitly:

```powershell
$env:TESSERACT_CMD = "C:\Program Files\Tesseract-OCR\tesseract.exe"
```

The code also checks the standard Windows installation paths automatically.

### Language data

Select OCR languages with a `+`-joined value:

```powershell
$env:GHOSTDATA_OCR_LANG = "eng"
```

For multiple installed languages:

```powershell
$env:GHOSTDATA_OCR_LANG = "eng+spa+fra"
```

If a requested language is not installed, the parser falls back to an
available installed language and records both the requested and used languages
in the evidence attributes. It does not invent OCR facts.

## 4. Optional provider configuration

Copy [`.env.example`](./.env.example) as a reference. Do not commit a real
`.env` file or place keys in source code, prompts, reports, or `log.txt`.

Set credentials in the current PowerShell session:

```powershell
$env:GEMINI_API_KEY = "replace-with-your-key"
$env:OPENROUTER_API_KEY = "replace-with-your-key"
$env:GROQ_API_KEY = "replace-with-your-key"
```

Configure models if the defaults are not appropriate:

```powershell
$env:GEMINI_MODEL = "gemini-2.5-flash"
$env:OPENROUTER_MODEL = "openai/gpt-4o-mini"
$env:GROQ_MODEL = "llama-3.3-70b-versatile"
```

The runtime provider order is:

```text
Gemini -> OpenRouter -> Groq
```

The independent usage-verification order is:

```text
Groq -> OpenRouter -> Gemini
```

Provider-reported token counts are recorded as returned. Missing values remain
missing; the project does not estimate token usage. Provider failures expose
only a safe HTTP status/class, never response bodies or credentials, and the
deterministic result is preserved.

## 5. Check the installation

Run the built-in summary command:

```powershell
python code\main.py summary
```

Confirm that:

- Evidence files are discovered.
- Activity rows are loaded.
- PDFs and PNGs are parsed or explicitly marked unavailable.
- No path or dependency error is reported.

## 6. Run tests

Run the complete unit suite:

```powershell
uv run --project .\code python -m unittest discover -s code\tests -t code
```

Run the CLI self-test:

```powershell
uv run --project .\code python code\main.py selftest
```

The test suite covers parsers, identity resolution, ownership safeguards,
state semantics, policy handling, OCR dispatch, runtime provider routing, and
keyless fallback behavior, plus output-contract validation and atomic writing.

## 7. Run deterministic sample evaluation

Validate sample evidence and identity coverage:

```powershell
uv run --project .\code python code\main.py validate-samples
```

Evaluate the 32 public samples without writing an output file:

```powershell
uv run --project .\code python code\main.py evaluate-samples
```

Inspect differences for every sample:

```powershell
uv run --project .\code python code\main.py diff-samples
```

Inspect one or more cases in detail:

```powershell
uv run --project .\code python code\main.py diff-samples case_26
uv run --project .\code python code\main.py diff-samples case_07 case_31
```

The deterministic engine remains authoritative for status, ownership, evidence
citations, remediation, and verification steps.

Before an output file is replaced, the validator rejects malformed headers,
duplicate or unsorted case IDs, invalid JSON, unsupported operation/state
combinations, out-of-order phases, unknown citations, and citations on proposed
remediation steps.

## 8. Run the optional runtime agent loop

Run the 32 sample cases with optional provider assistance:

```powershell
uv run --project .\code python code\main.py runtime-samples
```

The runtime loop is bounded to four model calls per case. The model may suggest
only evidence-investigation actions. It cannot directly set:

- user ownership;
- deletion status;
- record absence;
- evidence citations;
- remediation steps; or
- final output rows.

Successful provider calls are recorded in:

```text
code\evaluation\runtime_usage.jsonl
```

Run independent per-case usage reconciliation:

```powershell
uv run --project .\code python code\main.py runtime-samples --verify-usage
```

The verifier checks usage-ledger arithmetic through the Groq-first fallback
chain. It does not replace provider-reported token metadata.

Without credentials, this command completes using deterministic processing and
reports zero provider calls.

## 9. Environment variables

| Variable | Required | Purpose |
|---|---:|---|
| `TESSERACT_CMD` | No | Full path to `tesseract.exe` |
| `GHOSTDATA_OCR_LANG` | No | OCR languages, for example `eng+spa` |
| `GEMINI_API_KEY` | No | Gemini runtime provider |
| `GEMINI_MODEL` | No | Gemini model override |
| `OPENROUTER_API_KEY` | No | OpenRouter fallback provider |
| `OPENROUTER_MODEL` | No | OpenRouter model override |
| `GROQ_API_KEY` | No | Groq fallback and usage verifier |
| `GROQ_MODEL` | No | Groq model override |
| `GHOST_AUDIT_LLM_MODE` | No | Configuration marker; deterministic mode is safe default |
| `GHOST_AUDIT_VERIFY_USAGE` | No | Configuration marker for usage verification |

The CLI loads `code/.env` automatically when present, without overriding
already-exported environment variables. Provider calls still require the
explicit `runtime-samples` command; deterministic evaluation never contacts a
provider implicitly.

## 10. Server and deployment information

There is no application server to start:

- Do not run `uvicorn`, Flask, Django, or Streamlit.
- Run the CLI commands from the repository root.
- The evidence pipeline reads local files under `dataset/`.
- Runtime providers are contacted only when the runtime command is used and a
  provider key is available.

For a long-running process, use an external scheduler or job runner to invoke
the CLI. Do not add a web server unless the project requirements change.

## 11. Output and safety restrictions

The current CLI intentionally does not run the final 518-case evaluation or
generate the root `output.csv` until the readiness checklist is complete.

Do not:

- modify files under `dataset/`;
- commit API keys or credentials;
- log provider secrets;
- treat model output or activity claims as evidence;
- use OCR alone as proof of ownership, deletion, absence, or completion;
- run the final evaluation before the output validator and readiness checks are
  complete.

See the project-level [`TODO.md`](../TODO.md), [`AGENTS.md`](../AGENTS.md), and
the architecture reports under [`evaluation/`](./evaluation/) for the current
milestones and constraints.

## 12. Cleanup

Remove generated Python caches before packaging:

```powershell
Get-ChildItem -Directory -Recurse -Filter __pycache__ |
  Remove-Item -Recurse -Force
```

Do not include `.venv`, `dataset/`, API keys, runtime logs containing secrets,
or nested archives in the submission package.
