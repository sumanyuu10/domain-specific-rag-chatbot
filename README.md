# Domain-Specific RAG Chatbot Using Large Language Models

## Phase 1: environment setup and LLM verification

**Result: verified on November 3, 2026.** The official Codex Python SDK used the
existing ChatGPT-managed Codex sign-in to generate a response with the exact
`gpt-6.1-sol` model. A second live check exercised the implemented LangChain
adapter, structured output, a synthetic evidence passage, and a random nonce.

No API key, alternative model, authentication change, or credit purchase was used.
Only synthetic test content was submitted. Phase 2 has not started.

### Project status and phase rules

Phase 1 is complete, reviewed, and approved for its initial GitHub publication. Continue
from this code; do not regenerate the project or implement later phases early.
Work on one approved phase at a time. At the end of each phase, update this README,
the progress tracker, and the phase report, run the relevant tests, and present a
recommended commit message. Committing, pushing, and starting the next phase each
require approval.

- [Project progress and pending phases](PROJECT_PROGRESS.md)
- [Approved architecture reference](docs/ARCHITECTURE.md)
- [Git review, commit, and push instructions](docs/GIT_WORKFLOW.md)

The repository is rooted in this `domain_specific_rag` directory. Its `main`
branch is connected through `origin` to
[sumanyuu10/domain-specific-rag-chatbot](https://github.com/sumanyuu10/domain-specific-rag-chatbot).
Git history records phase commits. Do not initialize or publish the surrounding chat folder.

### Important components

| File | Purpose |
| --- | --- |
| `src/config.py` | Validates the fixed model identifier and timeout |
| `src/generation/llm.py` | Checks signed-in access, controls generation, and exposes the LangChain adapter |
| `src/verification.py` | Runs preflight or an explicitly requested synthetic inference |
| `pyproject.toml` / `requirements-phase1.lock` | Package settings and reproducible dependency versions |
| `tests/test_codex_gateway.py` | Existing offline generation, error, cancellation, and packaging checks |
| `tests/test_repository_hygiene.py` | Regression checks for private/generated paths and publishable source files |
| `PROJECT_PROGRESS.md` | Completed work, technical decisions, known issues, and the next approval gate |

### Environment

| Component | Tested version |
| --- | --- |
| Python | 3.12.14, Apple Silicon |
| Official Python SDK, `openai-codex` | 0.163.0 |
| SDK-pinned Codex runtime | 0.163.0 |
| LangChain Core | 1.7.4 |
| Pydantic | 2.14.2 |
| pytest | 9.2.0 |

Python 3.11+ is required by this project. The machine's default `/usr/bin/python3`
is 3.9.6, so the local `.venv` was created with the available bundled Python
3.12.14 interpreter. The system Python and global packages were not changed.
`requirements-phase1.lock` records the installed dependency set.

The approved later-phase stack remains Python, Streamlit, LangChain, LlamaIndex,
ChromaDB, Sentence Transformers, rank-bm25, RRF, PyMuPDF, SQLite, and optional
Ragas. Only the Phase 1 SDK/orchestration/test dependencies are installed now.

### Run the existing environment

Open a normal terminal in this project directory, then run:

```bash
.venv/bin/python -m pytest -q
.venv/bin/python -m src.verification
```

The default verification command checks authentication and model listing only;
it does **not** make a generation request. For one live synthetic inference that
consumes Codex usage:

```bash
.venv/bin/python -m src.verification --live --report reports/phase1-verification.json
```

The installed command `rag-verify-codex` offers the same options. An exit status
of zero means the requested checks passed. A failed report has a safe error code
and message; it is never presented as a successful verification.

### Set up a fresh environment

Install Python 3.11 or newer first. For example, if `python3.11` is available:

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements-phase1.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
```

Use `python3.12` instead when appropriate. The supplied `.venv` belongs to this
machine and should not be copied to another computer.

The project uses a normal local package install. After editing source files,
repeat `.venv/bin/python -m pip install --no-deps .` to refresh the installed CLI.
Running `python -m src.verification` from the project directory uses the local
source directly. A normal install avoids this desktop environment's hidden-file
flag on editable-install `.pth` files, which Python otherwise skips.

### Authentication and model selection

Use the official Codex sign-in. The installed Codex CLI's `codex login status`
can confirm its authentication method; use `codex login` if a browser sign-in is
needed. This project never opens a login flow automatically, reads `auth.json`,
copies tokens, logs account email addresses, or accepts API-key authentication.

The model is fixed to `gpt-6.1-sol`. Before each generation the gateway checks
the account type, the returned model catalog, and the newly created thread's
effective model/provider. A default, upgrade, or replacement model is not used.
SDK environment overrides shadow inherited API keys with empty values because
the official SDK merges its environment with the parent process's environment.

Optional timeout configuration uses the exported environment variable
`RAG_CODEX_TIMEOUT_SECONDS`; the default is 60 seconds. `.env.example` documents
it, but this phase does not automatically load `.env` files.

### Integration design

`CodexGateway` creates an isolated, ephemeral Codex thread for each generation.
It uses the official SDK's bundled runtime, requests read-only execution, denies
permission escalations, disables web/shell/app/plugin/memory/subagent features,
and supplies only the prepared prompt. Runtime state and logs are redirected
into a temporary local request directory that is removed afterward.

`as_runnable()` exposes this gateway as a real LangChain `RunnableLambda`.
The verifier connects a `ChatPromptTemplate` directly to that runnable and
validates the JSON response with Pydantic. Future ingestion and retrieval modules
will call this same boundary; no second model provider is introduced.

Timeout and cancellation attempt to interrupt an active turn and close the local
runtime. Runtime failures, missing sign-in, missing models, wrong effective models,
empty answers, and unexpected tool activity fail closed. There are no automatic
generation retries in Phase 1. Answers with unexpected activity are discarded.

### Test evidence

Latest first-commit revalidation: **78 offline tests passed**, dependency
consistency passed, and the live signed-in `gpt-6.1-sol` LangChain structured
check passed. No Phase 1 tests were skipped. Phase 2 remains unimplemented.

- `reports/phase1-verification.json`: local real SDK/LangChain inference result.
- `reports/phase1-tests.xml`: local offline test results.
- `reports/PHASE1_REPORT.md`: implementation, errors, limits, and approval boundary.

The JSON/XML files are generated locally and excluded from Git. The curated
Markdown report records the latest reviewed outcome for GitHub readers. The
offline suite includes the original 32 gateway tests plus repository hygiene
checks. Hygiene tests require Git, which is also needed for the commit workflow.

Offline tests inject fake SDK clients; running pytest does not consume Codex
usage. They cover authentication/model rejection, environment overrides, exact
thread settings, runtime cleanup, cancellation, timeout, unsafe output, and the
structured verification contract. The live test is an explicit CLI command.

### Important limits

- The desktop execution sandbox initially blocked SDK runtime startup. Redirecting
  state avoided the first SQLite error, but OS restrictions still required the
  verification command to run outside that execution sandbox. This is a runtime
  launch restriction, not evidence of an unsupported model or authentication mode.
- Subscription entitlement and remaining allowance can change. A successful test
  today does not guarantee future capacity or zero incremental billing under every
  workspace's settings. No billing setting was changed.
- No tool activity occurred in the successful synthetic checks. This is not a
  comprehensive adversarial isolation assessment. Inherited custom MCP/skill/hook
  configuration and stronger evidence-isolation tests must be reviewed before any
  real document excerpts are processed.
- Structured source-ID output was tested with a synthetic passage. PDF extraction,
  real citation validation, retrieval quality, hallucination evaluation, Ragas
  compatibility, and the Streamlit application are not implemented in Phase 1.
- Keep this a local prototype. Recheck the documented authentication boundary before
  any future hosted or commercial deployment.

### Files created

```text
pyproject.toml
requirements-phase1.lock
.gitignore
.env.example
README.md
PROJECT_PROGRESS.md
docs/ARCHITECTURE.md
docs/assets/architecture.png
docs/GIT_WORKFLOW.md
src/__init__.py
src/config.py
src/generation/__init__.py
src/generation/llm.py
src/verification.py
tests/test_codex_gateway.py
tests/test_repository_hygiene.py
reports/phase1-verification.json
reports/phase1-tests.xml
reports/PHASE1_REPORT.md
```

The original architecture document and earlier outputs were not modified. The
repository includes a readable copy of the approved reference and its diagram.

### First GitHub commit

Review and run the commands in [docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md).
Recommended message:

```text
feat: complete phase 1 environment and Codex verification
```

`.gitignore` excludes `.env` variants, known credential files, uploaded/private
documents, local databases/vector stores, model files, environments, caches,
build output, and raw test/inference results. `.env.example`, source, tests, and
curated documentation remain publishable. Git ignore rules cannot detect a key
pasted inside a source file; review the staged diff before committing. No real
credentials or private documents belong in this repository.

### Official documentation

- [Codex Python SDK](https://learn.chatgpt.com/docs/codex-sdk)
- [Authentication](https://learn.chatgpt.com/docs/auth)
- [App-server account and model interfaces](https://learn.chatgpt.com/docs/app-server)
- [Runtime configuration](https://learn.chatgpt.com/docs/config-file/config-reference)
- [Usage and pricing](https://learn.chatgpt.com/docs/pricing)

**Stop point:** Phase 1 is complete. Phase 2 requires the user's approval.
