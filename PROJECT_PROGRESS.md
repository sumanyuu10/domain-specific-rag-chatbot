# Project progress

Last updated: November 3, 2026.

## Current phase

**Phase 1 — environment setup and LLM integration verification.** Implementation
is complete and has been reviewed and approved by the user for its initial commit
and push. Phase 2 must not start until the user explicitly approves it.

## Completed phases

### Phase 1

- Created an isolated environment and pinned the tested SDK, LangChain Core,
  Pydantic, and test dependencies.
- Verified the official Codex Python SDK using the existing ChatGPT-managed
  Codex sign-in and the exact `gpt-6.1-sol` model.
- Implemented a reusable generation gateway and a real LangChain runnable adapter.
- Added access/model checks, structured-output verification, timeouts,
  cancellation, temporary runtime cleanup, and safe errors.
- Added offline tests and an explicit live CLI check using synthetic evidence.
- Prepared repository exclusions, Git hygiene tests, approved-plan documentation,
  file-purpose explanations, and a repeatable phase commit workflow.

The current checks and their limitations are recorded in
[the Phase 1 report](reports/PHASE1_REPORT.md). Generated JSON and XML reports
remain local; the curated Markdown report is suitable for version control.

Latest revalidation: **78 offline tests passed** (32 gateway/verification tests
and 46 repository-hygiene cases); the live signed-in `gpt-6.1-sol` structured
LangChain check passed; dependency consistency, staging dry-run, known secret
patterns, whitespace, dependency pins, and local documentation links passed.
No Phase 1 tests were skipped. No Phase 2 tests or features were run.

## Pending phases

These group the remaining milestones from the approved plan; they do not change
the architecture or authorize implementation.

| Phase | Approved work | Status |
| --- | --- | --- |
| 2 | PDF ingestion, page metadata, LlamaIndex chunking, local embeddings, persistent Chroma/BM25 indexes, document upload/management | Awaiting approval |
| 3 | Paper-filtered sparse/dense retrieval, RRF, grounded question answering, real citation validation | Pending |
| 4 | Paper-balanced comparison, cited evidence cards, agreement/disagreement synthesis | Pending |
| 5 | Complete source inspection/UI refinement, persistence/deletion recovery, and failure handling | Pending |
| 6 | Manually labeled dataset, three-mode retrieval evaluation, faithfulness/hallucination review, optional Ragas, final guide and demo | Pending |

## Implemented functionality and important files

| File | Purpose |
| --- | --- |
| `src/config.py` | Fixed authorized model and validated timeout configuration |
| `src/generation/llm.py` | Official SDK account/model checks, generation lifecycle, LangChain adapter |
| `src/verification.py` | Metadata-only check by default; one synthetic inference with `--live` |
| `tests/test_codex_gateway.py` | Offline integration-contract, failure, cancellation, and packaging tests |
| `tests/test_repository_hygiene.py` | Check that private/generated files are excluded and intended source files remain publishable |
| `pyproject.toml` | Package metadata, direct dependencies, test configuration, installed CLI |
| `requirements-phase1.lock` | Complete tested Phase 1 dependency set |
| `.env.example` | Non-secret example timeout setting; not loaded automatically |
| `docs/ARCHITECTURE.md` | Approved architecture reference, preserved from the existing plan |
| `docs/GIT_WORKFLOW.md` | Review, commit, and push commands; phase-by-phase rules |

## Important technical decisions

- Retain Python, Streamlit, LangChain, LlamaIndex, ChromaDB, Sentence Transformers,
  BM25, and RRF. Later-phase libraries are not installed or implemented early.
- LlamaIndex will own ingestion/indexing; LangChain owns retrieval orchestration,
  prompts, and generation. Both use one canonical chunk contract and vector store.
- Generation uses only `gpt-6.1-sol` through signed-in Codex and the official SDK.
  Do not use a different model, API key, or authentication method without approval.
- Keep PDFs, embeddings, indexes, credentials, local verification output, virtual
  environments, and build output out of Git. `.env.example` is intentionally kept.
- Use synthetic evidence for Phase 1. Do not upload real papers as part of setup.
- Python 3.11+ is the compatibility target; the existing environment is tested
  with Python 3.12.14. Use a normal package install for the CLI.
- Work on one phase at a time, update this file and README after each phase,
  and prepare a meaningful commit for user review. Never commit or push automatically.

## Known issues and limits

- The desktop execution sandbox blocks nested SDK runtime startup; live checks
  need OS execution permission or a normal terminal where Codex can run.
- Account entitlement and usage allowance can change. Recheck before generation.
- Successful synthetic turns showed no tool activity, but complete evidence
  isolation and inherited MCP/skill/hook settings still need review before real
  documents are processed. Read-only mode alone does not prove evidence isolation.
- Ragas compatibility and all actual PDF/retrieval/citation workflows remain
  unimplemented and unverified.
- `.gitignore` protects known paths and file types, not secrets pasted into source.
  Review staged changes before every commit; do not use `git add -f` for private files.
- The local `main` branch is connected to `origin` at
  `https://github.com/sumanyuu10/domain-specific-rag-chatbot.git`.
  Git history records publication; future commits and pushes require approval.

## Next development steps

1. Review the published Phase 1 snapshot, tests, and known limitations in GitHub.
2. Obtain explicit approval for Phase 2.
3. At Phase 2 entry, resolve the document-evidence isolation gate before passing
   any real paper excerpts to the model; then implement the approved ingestion
   and indexing pipeline.

**Stop here: Phase 2 has not started.**
