# Phase 3 implementation report

Date: November 3, 2026. Scope: approved selected-paper hybrid retrieval, grounded
question answering, citation validation and chat. Phases 1 and 2 remain published
at `063b8b6` and `cffa5e6`. The user reviewed Phase 3 and authorized its commit
and push on November 6, 2026. Git history records publication. Phase 4 has not started.

## Delivered behavior

Users select saved papers, ask a question and inspect locally retrieved passages.
BM25 and dense Chroma search each filter the selected active papers before ranking.
The same MiniLM model embeds the question; existing PDF vectors are reused.
Equal-weight RRF uses constant 60 and one-based ranks over 20 candidates per method.
Context selection retains at most eight chunks/16,000 passage characters, dropping
exact/subsumed same-page duplicates without discarding distinct numeric results.
RRF scores are not presented as answer confidence.

LangChain runnable composition carries canonical chunks as LangChain Documents,
builds a versioned prompt and invokes the reused official Codex gateway. Remote
inference requires explicit UI consent followed by Generate cited answer. The model
returns structured claims/source IDs or missing-evidence acknowledgment. One bounded
repair is permitted for malformed output or invalid IDs. Unresolved responses are
withheld; SDK failures do not trigger model/provider substitution.

Source checks resolve IDs only against current retrieved, selected, active canonical
chunks. Paper labels, one-based PDF pages and passages come from SQLite. A changed
corpus or tampered context is rejected before inference and checked again afterward.
The UI resets session answers/evidence and consent on selection/corpus changes.
Earlier assistant answers are not documentary evidence. Follow-ups use only the
last bounded user question; ambiguous references request clarification.

## Evidence isolation

EvidenceGateway inherits Phase 1 account/model/turn handling and adds mandatory
request-scoped checks. A discovery runtime makes no model request and inventories
capabilities. A separate hardened runtime disables discovered MCP servers, plugins
and skills, disables hooks/notifications and web/shell/image/memory/subagent features,
and replaces inherited instructions for this worker only. User configuration and
authentication are not edited or copied. Only official service hosts are accepted.

The effective config must match a named restricted read-only profile for the
worker's temporary directory and curated platform defaults, with tool networking
disabled. The actual thread must report that profile, the exact model/provider,
no inherited instruction sources and denied approvals. Its MCP inventory can contain
only explicitly disabled entries with no exposed tools/resources. Unknown or unsafe
states fail closed before evidence is submitted. Unexpected turn activity is still
rejected by the inherited gateway.

Application-process LangChain tracing and worker telemetry exporters are disabled.
The public pinned SDK lacks high-level config-inspection helpers; a single adapter
uses its official low-level client through the high-level client's internal reference.
Raw responses preserve newer permission metadata absent from its typed response.
This dependency is explicit, version checked and tested; it must be revalidated
before SDK upgrades. No API key, alternative SDK, model or authentication was added.

The synthetic filesystem test confirmed an inside control file was readable and an
outside canary was denied. A synthetic document-instruction attack was resisted in
a live turn without reported tool use. These tests support the specific boundary;
they do not prove general adversarial safety or eliminate hallucinations.

## Files created or modified

| Files | Change |
| --- | --- |
| `src/retrieval/vector.py`, `hybrid.py`, `adapters.py` | New filtered semantic search, RRF/context selection and LangChain retrieval adapter |
| `src/retrieval/bm25.py` | Add keyword query scoring with filtering and small-corpus score handling |
| `src/generation/prompts.py`, `chains.py`, `citations.py` | New versioned prompts, grounded answer service, bounded repair and canonical citation checks |
| `src/generation/isolation.py` | New mandatory effective-config/thread permission gate |
| `src/generation/llm.py` | Small extension hooks for the stricter worker; retain original auth/model/turn/runnable behavior |
| `src/persistence.py`, `src/config.py`, `src/schemas.py` | Add canonical lookup/corpus version, retrieval limits and typed answer/source contracts |
| `src/ui/chat.py`, `src/ui/documents.py` | New local search/consent/answer/source UI connected to existing document management |
| `src/phase3_verification.py` | New explicit worker/isolation and optional synthetic live RAG verifier |
| `pyproject.toml` | Add verification entry point and direct-pin existing LangSmith tracing dependency; no new installed versions |
| `tests/test_retrieval.py`, `test_retrieval_integration.py` | Sparse/dense/RRF/filter/context tests and actual MiniLM integration |
| `tests/test_answer_chain.py`, `test_chat_ui.py` | Grounded-chain/validation/repair/consent and chat state tests |
| `tests/test_isolation.py`, `test_phase3_verification.py` | Fail-closed runtime, endpoint, MCP inventory, safe error and installed-CLI tests |
| `README.md`, `PROJECT_PROGRESS.md`, `docs/GIT_WORKFLOW.md`, this report | Current usage, decisions, results and approval boundary |

Existing ingestion modules, embedding implementation, ingestion fingerprint,
architecture reference/diagram, Phase 1 verifier/tests and both historical dependency
locks remain unchanged. No existing PDF collection needs rebuilding for Phase 3.

## Final validation

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q --tb=short --junitxml=reports/phase3-all-tests.xml
```

**181 passed, 0 failed, 0 errors, 0 skipped; 13.05 seconds.**

Publication revalidation on November 6, 2026: **181 passed, 0 failed, 0 errors,
0 skipped; 16.35 seconds**, using the same full-suite options and writing
`reports/phase3-publication-tests.xml`. All original Phase 1/2 tests passed.
The published ingestion implementation and fingerprint, original verifier/tests,
and historical dependency locks remain unchanged. No working code was changed
during this publication review.

| Test group | Passed |
| --- | ---: |
| Original gateway/verification | 32 |
| Original repository hygiene | 46 |
| Original PDF/index/lifecycle | 29 |
| Original document UI | 4 |
| Original actual MiniLM embedding integration | 1 |
| Phase 3 retrieval | 18 |
| Phase 3 answer chain | 14 |
| Phase 3 isolation | 30 |
| Phase 3 chat UI | 4 |
| Phase 3 verifier/CLI | 2 |
| Phase 3 actual MiniLM retrieval integration | 1 |
| **Total** | **181** |

The original 112 Phase 1/2 tests still pass. Pytest uses fake model responses and
never makes LLM requests. Both actual embedding tests ran from cached public weights
with HF Hub networking disabled. The default pytest command skips those two tests
unless `--run-embedding-integration` is supplied.

Separate explicit live verification:

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m src.phase3_verification --live --report reports/phase3-live.json
```

Implementation live result on November 3 at 16:40 UTC: **passed**, using `gpt-6.1-sol`, ChatGPT-managed
Codex sign-in and official SDK/runtime `0.163.0`. It verified effective settings,
thread permissions, allowed control/denied canary reads, a structured injection/nonce
probe, a real local-MiniLM hybrid RAG answer with canonical paper/page citation,
and explicit insufficient evidence for an unreported carbon footprint. Only generated
synthetic papers/passages were submitted. Normally three turns are used, up to five
if either RAG answer needs its bounded repair; no performance/quality benchmark is claimed.

Publication live revalidation on November 6: **passed**, with the same exact model,
sign-in method and SDK/runtime. The check again verified restricted worker settings,
synthetic allowed/denied file reads, the injection/nonce probe, a real MiniLM hybrid
answer with a canonical PDF citation and missing-evidence acknowledgment. No tool
activity was reported and only generated evidence was submitted. The local result
is `reports/phase3-publication-live.json` (ignored). The Streamlit health/HTML checks
again returned HTTP 200, dependency consistency passed, and no remote-history
divergence was found after fetching `origin/main`.

Other checks: normal package build/install and installed CLI help passed; `pip check`
reported no broken requirements; the actual local Streamlit health and HTML routes
returned HTTP 200. Source syntax, dependency pins, local documentation links,
ignore boundaries and Git state are checked before handoff. Raw JSON/XML reports
remain local and ignored. This Markdown report is intended for version control.

## Issues found and addressed

- Empty config tables merge with inherited tables rather than removing servers.
  Explicit per-server/plugin disable entries are constructed and re-audited.
- Quoted names in dotted CLI override keys can create a different server entry.
  Literal names are quoted inside TOML values instead; dotted/quoted-name tests cover this.
- Effective permission-profile tables include null metadata fields. Validation
  normalizes only null metadata, while rejecting extra filesystem grants/inheritance.
- The MCP status API lists disabled configurations too. Validation requires their
  explicit disabled state and empty capabilities; active/starting/unknown entries fail.
- Strict endpoint checks initially rejected a supported official-host path. They
  now validate the exact HTTPS host, standard port and absence of credentials/query
  overrides, with hostile-host/HTTP/nonstandard-port cases covered.
- Parent-process tracing could export evidence independently of SDK environment
  controls. Explicit tracing contexts now disable that path.
- Five upstream PyMuPDF/SWIG deprecation warnings remain. No application test fails.

SDK startup and the local HTTP check required approved OS execution permission in
the desktop sandbox. No model, authentication or permission requirement was silently
substituted when checks failed during development.

## Limits and next approval gate

Citation correctness here means structural traceability; claim support remains a
human/evaluation concern. Phase 6 will measure retrieval, faithfulness and hallucinations
on a labeled dataset. No improvement percentage is invented.

Ordinary questions can favor one selected paper. Balanced per-paper/category evidence
cards and comparison synthesis remain Phase 4. PDF layout/OCR/figure/table limitations,
basic-versus-comprehensive recovery boundaries and trusted Joblib assumptions remain.
Chat history is session-only; broad adversarial tests, real-paper benchmarks and manual
browser upload transport were not run. macOS was tested; the explicit canary verifier
uses `/bin/cat`. SDK/account/managed settings can change and must be rechecked.

Recommended commit message:
`feat: add phase 3 hybrid retrieval and cited research chat`

**Phase 3 publication is approved. Stop before Phase 4 until separately approved.**
