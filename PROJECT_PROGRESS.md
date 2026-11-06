# Project progress

Last updated: November 6, 2026.

## Current phase

**Phase 3 — selected-paper hybrid retrieval, cited answers and chat.**
Implementation and validation are complete. The user reviewed and approved Phase 3
and authorized its commit and push on November 6, 2026. Git history records
publication. Phase 4 requires separate explicit approval and has not started.

## Completed phases

### Phase 1 — published

- Official Codex Python SDK, existing ChatGPT-managed sign-in and exact
  `gpt-6.1-sol` model verified with synthetic inference.
- LangChain runnable gateway, structured output, account/model checks,
  timeout/cancellation, temporary runtime cleanup and safe error handling.
- 78 offline gateway and repository-hygiene tests.
- Commit `063b8b6`: `feat: complete phase 1 environment and Codex verification`.
- [Historical implementation report](reports/PHASE1_REPORT.md).

### Phase 2 — published

- Streamlit PDF upload/management/selection, original and cleaned page previews,
  warnings and confirmed deletion.
- PyMuPDF page reader, LlamaIndex token-aware chunks, actual local MiniLM
  embeddings and persistent Chroma/BM25 indexes over canonical SQLite records.
- Up to 12 papers, 25 MB/200-page PDF limits, duplicate detection, restart reuse,
  fingerprint checks, locking and basic interrupted-operation cleanup.
- 112 tests passed at publication, including the real MiniLM integration check.
- Commit `cffa5e6`: `feat: add phase 2 PDF ingestion and persistent indexes`.
- [Historical implementation report](reports/PHASE2_REPORT.md).

### Phase 3 — completed and approved

- Selected-paper BM25 and Chroma searches filter eligible documents before top-K.
  Query vectors use the same local MiniLM service; unchanged PDFs are not reindexed.
- Equal-weight reciprocal rank fusion: 20 candidates per method, constant 60,
  one-based ranks, stable tie handling and canonical chunk deduplication.
- Context limited to eight passages and 16,000 passage characters; remove exact
  or subsumed same-page text while retaining distinct experimental results.
- LangChain retrieval runnable returns actual LangChain Documents alongside
  canonical provenance; a runnable answer chain builds the prompt and invokes
  the existing official Codex boundary.
- Bounded questions and simple recent-user-question handling for follow-ups.
  Earlier assistant answers are never documentary evidence. Overlong dense
  questions are rejected before MiniLM truncation.
- Structured claims require retrieved source IDs. Canonical citation validation
  checks selected/active papers, exact passages, metadata and corpus version.
  One bounded format/source repair is allowed; unresolved answers are withheld.
- Missing evidence is acknowledged; unavailable credentials/runtime/model access
  or failed isolation disables generation while local retrieval stays available.
- Streamlit chat previews passages locally. An explicit consent checkbox and
  Generate cited answer action precede remote inference. Selection/corpus changes
  clear in-memory answers/evidence and reset consent. History is session-only.
- A stricter EvidenceGateway reuses Phase 1 auth/model/turn behavior through small
  extension hooks. It discovers and disables inherited capabilities, audits
  effective configuration, checks actual thread permissions/instruction sources
  and rejects active MCP capabilities before sending evidence.
- Answer workers use a temporary restricted read-only profile with tool network
  access disabled. MCP/skills/plugins/hooks, notifications, web/shell/image tools,
  memory, subagents and telemetry export are disabled for those workers.
  Official service hosts are checked; user configuration/authentication are untouched.
- LangChain tracing is disabled around application retrieval and generation to
  prevent inherited tracing settings from exporting private evidence.
- Added explicit metadata/isolation and optional live synthetic RAG verification.

**Publication revalidation on November 6: 181 tests passed, none skipped, in
16.35 seconds.** All original
112 Phase 1/2 tests still pass. Live signed-in `gpt-6.1-sol` verification passed
synthetic filesystem isolation, document-instruction attack, a real local-MiniLM
retrieval/cited answer and a missing-evidence question. The local Streamlit HTTP
smoke check and dependency consistency passed. See [the Phase 3 report](reports/PHASE3_REPORT.md).

## Pending phases

| Phase | Approved roadmap scope | Status |
| --- | --- | --- |
| 4 | Per-paper/category retrieval budgets, evidence cards, comparison tables and agreement/disagreement synthesis | Awaiting explicit approval; not started |
| 5 | UI/source refinement, comprehensive corruption/recovery and failure handling | Pending |
| 6 | Labeled dataset, three-mode retrieval evaluation, claim faithfulness/hallucination review, optional Ragas and final demo/guide | Pending |

The approved architecture reference and diagram remain unchanged in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Phase 3 adds question answering, not
Phase 4's balanced comparison engine or Phase 6's evaluation results.

## Important components

| Files | Purpose |
| --- | --- |
| `src/ingestion/`, `src/embeddings.py` | Existing LlamaIndex/PyMuPDF/local embedding pipeline, unchanged |
| `src/persistence.py`, `src/schemas.py`, `src/config.py` | Canonical source lookup, corpus version, retrieval/answer contracts and limits |
| `src/retrieval/bm25.py`, `vector.py`, `hybrid.py` | Sparse/dense search, filtering, RRF and context selection |
| `src/retrieval/adapters.py` | LangChain retrieval adapter and Documents |
| `src/generation/llm.py`, `isolation.py` | Reused SDK gateway plus strict evidence-worker checks |
| `src/generation/prompts.py`, `chains.py`, `citations.py` | Versioned prompts, orchestration, repair and source validation |
| `src/ui/documents.py`, `src/ui/chat.py` | Existing document library plus local search, consent, answers and citations |
| `src/phase3_verification.py` | Explicit synthetic SDK/isolation/RAG verification CLI |
| `tests/`, `reports/PHASE3_REPORT.md` | Regression evidence and current limitations |

## Technical decisions

- Preserve Python, Streamlit, LangChain, LlamaIndex, ChromaDB, Sentence Transformers,
  BM25 and RRF; one canonical corpus and one vector store.
- LlamaIndex owns ingestion/indexing; LangChain owns retrieval/generation
  composition. No second parser, embedding model or provider was introduced.
- Keep the MiniLM revision, ingestion fingerprint and saved Phase 2 data compatible.
  Phase 3 uses the same installed dependency versions in `requirements-phase2.lock`.
  The existing LangSmith dependency is explicitly pinned for tracing controls.
- Generation remains only `gpt-6.1-sol`, signed-in Codex, official Python SDK.
  Never substitute a model or authentication method without approval.
- The SDK is pinned to `openai-codex==0.163.0`. Necessary config/thread RPCs use
  the official SDK's low-level client through one compatibility adapter; unsupported
  versions or unverified permissions fail closed. Revalidate before SDK changes.
- PDFs, vectors, snapshots and canonical passages remain local. Only permitted
  questions, bounded retrieved passages and source labels are sent for generation.
- Gate checks and synthetic canaries establish concrete tested restrictions, not
  universal immunity to document attacks or hallucinations.
- Work on one approved phase; obtain separate approval for publication and the
  next phase. Phase 3 publication is approved; future phases require their own approval.

## Known issues and limitations

- Five upstream PyMuPDF/SWIG deprecation warnings remain; no tests are failing.
- PDF layout remains heuristic. Scans/OCR, figure interpretation, equations and
  complex tables are unsupported. Real-paper benchmark quality was not measured.
- Structural citations prove traceability, not whether every claim is supported.
  Retrieval accuracy, faithfulness and hallucination metrics remain Phase 6.
- Ordinary hybrid questions can concentrate on one selected paper; per-paper
  balanced comparison evidence collection remains Phase 4.
- Follow-up handling uses a bounded rule; ambiguous references may need a named
  paper/method. Chat history is not durable across app restarts.
- Basic lifecycle recovery is implemented; comprehensive corruption recovery is
  Phase 5. Joblib snapshots must be trusted local application data. Deletion is
  logical, not forensic erasure.
- Live tests used generated evidence only. Full manual browser file-upload
  transport and broad adversarial/representative-paper review were not performed.
- SDK runtime startup and local HTTP checks need OS execution permission in the
  desktop sandbox. Public MiniLM weights must be cached for offline processing.
- The explicit filesystem verifier uses `/bin/cat`; macOS was tested, other OSes
  were not. Account entitlement, usage limits and managed policies may change.
- `.gitignore` excludes credentials, documents, local runtime/index/model data and
  raw reports; it cannot identify arbitrary secrets pasted into source.

## Next steps and stop point

1. Review the Phase 3 commit and its validation report in GitHub after publication.
2. Obtain explicit approval before beginning Phase 4.

Phase 4 planning only: collect evidence independently for each selected paper and
each comparison category (methodology, datasets, results, conclusions, limitations).
Reuse the existing BM25/vector/RRF services with per-paper budgets. Add structured
evidence cards and comparison synthesis in `src/generation/comparison.py`, and
comparison controls/tables in `src/ui/comparison.py`. Extend shared schemas,
configuration, canonical citation validation and persistence for validated card
caching/invalidation as needed; no Phase 4 source files have been created.

The approved defaults begin with eight candidates per method/category and up to
two retained passages per category. Each paper must have evidence or an explicit
gap. Validate cards against original chunks before a LangChain synthesis request;
trace every comparison cell back to those chunks. Cache keys must include paper,
question/category, model and prompt versions, and invalidate affected cards/results
after deletion or source changes. Use the existing isolated signed-in Codex gateway.

Expected Phase 4 tests cover an intentionally dominant paper, missing categories,
agreements/disagreements with sources from the relevant papers, incomparable
experimental settings, invalid card/cell citations, cache invalidation, SDK failures,
and comparison UI. Retain the existing regression suite and use synthetic multi-paper
fixtures plus an explicit live comparison smoke check when Phase 4 is approved.

Recommended commit message:
`feat: add phase 3 hybrid retrieval and cited research chat`

**Stop here: Phase 3 complete and approved for publication; Phase 4 awaits approval.**
