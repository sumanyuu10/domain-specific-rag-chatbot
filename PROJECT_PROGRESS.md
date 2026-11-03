# Project progress

Last updated: November 3, 2026.

## Current phase

**Phase 2 — PDF ingestion, document management, and persistent local indexes.**
Implementation and automated validation are complete. The user reviewed and
approved Phase 2 and authorized its commit and push on November 3, 2026.
Git history records publication. **Do not begin Phase 3 without approval.**

## Completed phases

### Phase 1 — published

- Isolated Python environment and exact tested dependency pins.
- Official Codex Python SDK with the existing ChatGPT-managed Codex sign-in and
  exact `gpt-6.1-sol` model, including a successful live synthetic check.
- Reusable LangChain runnable gateway, structured output, account/model checks,
  timeout/cancellation, temporary runtime cleanup, and safe failure messages.
- 78 regression tests and repository hygiene/documentation.
- Published commit: `063b8b6` (`feat: complete phase 1 environment and Codex verification`).

The gateway, verifier, Phase 1 tests, and historical dependency lock remain intact.
See [the Phase 1 report](reports/PHASE1_REPORT.md).

### Phase 2 — completed and approved

- Streamlit local web app: multiple PDF uploads, saved-paper library, paper
  selection, original/cleaned page preview, warnings, and confirmed deletion.
- Up to 12 papers; 25 MB and 200-page limits per PDF; duplicate bytes skipped
  without parsing or re-embedding. No minimum batch size.
- PyMuPDF reader compatible with LlamaIndex's document-reader contract, preserving
  PDF page positions, paper identity, filename, title, and extraction diagnostics.
- Conservative cleaning and line-geometry reading-order heuristic for columns.
- LlamaIndex token-aware chunking: 220 MiniLM tokens, 40 overlap; final input-size
  validation with special tokens prevents accepted truncated embeddings.
- Actual local CPU Sentence Transformers MiniLM embeddings through LlamaIndex,
  pinned model revision, normalized 384-dimensional vectors, cosine Chroma index.
- One canonical SQLite catalog with chunk IDs shared by Chroma and rank-bm25.
  BM25 snapshots restore or rebuild from canonical records without re-embedding.
- Local persistence, lock-serialized lifecycle operations, processing/deleting
  states, failed-ingestion cleanup, interrupted-operation cleanup on reopening,
  and full logical deletion of each paper's stored application data.
- Fingerprint rejection of incompatible settings with preservation of existing data.
- Dependency pins, fresh-install/run instructions, and a curated Phase 2 report.

Latest validation: **112 tests passed, none skipped**, including actual MiniLM
with `HF_HUB_OFFLINE=1` after its initial public download. This includes all 78
Phase 1 tests, 29 PDF/index/lifecycle tests, four Streamlit tests, and one actual
embedding integration test. Dependency consistency and the local Streamlit
HTTP smoke test passed. See [the Phase 2 report](reports/PHASE2_REPORT.md).

Publication revalidation: all 112 tests passed again with no failures or skipped
tests; dependency consistency passed. The Phase 1 gateway, verifier, regression
tests and dependency lock are unchanged from the published Phase 1 commit.
No new live Codex inference or manual browser upload test was performed for
publication. The existing manual-test limitations below remain explicit.

No LLM inference or paper transmission occurred in Phase 2. The user has approved
publication of Phase 2 only; Phase 3 implementation has not started.

## Pending phases

| Phase | Approved work | Status |
| --- | --- | --- |
| 3 | Selected-paper sparse/dense retrieval, RRF, grounded answers, citation validation | Awaiting approval; resolve Codex evidence-isolation gate first |
| 4 | Paper-balanced comparison, evidence cards, agreement/disagreement synthesis | Pending |
| 5 | UI/source refinement, comprehensive recovery and failure handling | Pending |
| 6 | Labeled dataset, three-mode retrieval evaluation, faithfulness/hallucination review, optional Ragas, final guide/demo | Pending |

The approved architecture remains in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
Basic ingestion consistency is implemented now so Phase 2 can safely persist and
delete papers; comprehensive corruption/recovery testing remains Phase 5.

## Implemented functionality and components

| Component | Files | Purpose |
| --- | --- | --- |
| Frontend | `app.py`, `src/ui/documents.py`, `.streamlit/config.toml` | Local uploads, preview, paper selection and deletion |
| Source contract | `src/schemas.py`, `src/config.py` | Canonical records, errors, fixed defaults and pipeline fingerprint |
| PDF processing | `src/ingestion/pdf.py`, `cleaning.py` | Original/cleaned page text and extraction warnings |
| Chunking | `src/ingestion/chunking.py` | LlamaIndex token-aware, page-scoped deterministic chunks |
| Embedding/indexing | `src/embeddings.py`, `src/ingestion/indexing.py` | One MiniLM service and one LlamaIndex Chroma writer |
| Lifecycle/catalog | `src/ingestion/pipeline.py`, `src/persistence.py` | Persistence, caps, duplicates, locking and cleanup |
| Sparse index | `src/retrieval/bm25.py` | Actual rank-bm25 snapshot over canonical chunks |
| Existing generation | `src/generation/llm.py`, `src/verification.py` | Unchanged official SDK gateway and LangChain adapter |
| Verification | `tests/`, `reports/PHASE2_REPORT.md` | Automated results and explicit limits |

## Important technical decisions

- Preserve Python, Streamlit, LangChain, LlamaIndex, ChromaDB, Sentence Transformers,
  BM25 and eventual RRF. No providers, frameworks, microservices or authentication
  systems have been substituted or added.
- LlamaIndex owns ingestion and vector writing; LangChain owns the existing LLM
  boundary and future retrieval/answer chains. Canonical IDs avoid duplicate corpora.
- Use `sentence-transformers/all-MiniLM-L6-v2` at revision
  `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; embeddings run on CPU.
- Keep pages within their original PDF positions. Do not merge across pages.
  Metadata is preserved separately and excluded from embedding text.
- Persist PDFs, pages, chunks, Chroma and BM25 locally. The only Phase 2 network
  requirement is the first public embedding-model download; no hosted inference.
- Generation remains only `gpt-6.1-sol` through signed-in Codex and the official
  Python SDK. Never replace the model or authentication without approval.
- Python 3.11+ is the target; Python 3.12.14/macOS Apple Silicon was tested.
  Use a normal local package install. Phase 1 pins were preserved; Phase 2 adds
  tested direct/transitive pins in its own lock file.
- Changing the embedding/chunking fingerprint requires the original configuration
  or a new empty data folder; automatic reindexing is not implemented.
- Keep each phase separate; review/test before any approved commit and push.

## Known issues and limits

- PDF reading order is heuristic. Scans, figures, equations and complex tables
  are not interpreted reliably. Previews show actual indexed text. Tests use
  synthetic papers, not a benchmark proving real-paper extraction accuracy.
- Phase 2 preserves citation metadata but does not validate answers/citations,
  implement retrieval/RRF or measure hallucinations and retrieval quality.
- The initial public model download hit a desktop sandbox permission error in
  Hugging Face's default Xet cache. Setting `HF_XET_CACHE` to the ignored local
  model folder resolved it; see README. Cached real-model processing passed offline.
- Five upstream PyMuPDF/SWIG deprecation warnings remain; no test failures remain.
- Before Phase 3 sends real excerpts to Codex, inspect inherited MCP/skill/hook
  configuration and complete evidence-isolation tests. Phase 1 synthetic success
  and read-only execution do not establish complete isolation.
- SDK runtime startup may require OS execution permission. Codex account access
  and usage allowance can change; no new entitlement claim is made by Phase 2.
- Joblib snapshots are trusted local application data; never import untrusted ones.
  Deletion is logical application deletion, not forensic erasure or backup removal.
- No full manual browser upload transport test was run; Streamlit AppTest exercised
  the actual upload action with an UploadedFile-compatible synthetic object, and
  the real local server's health/HTML endpoints were checked separately.
- `.gitignore` covers private documents, credentials, data/index/model files,
  environments and generated output. It cannot detect secrets pasted into source.

## Next development steps

1. Review the Phase 2 commit and validation report in GitHub after publication.
2. Obtain explicit approval for Phase 3.
3. At Phase 3 entry, complete the evidence-isolation gate before sending any real
   excerpts; implement only its approved filtered hybrid retrieval/answer scope.

Phase 3 will extend `src/retrieval/bm25.py`, add `vector.py`, `hybrid.py` and
`adapters.py`, and add `src/generation/prompts.py`, `chains.py` and `citations.py`.
`src/ui/chat.py` will connect selected papers to the answer chain; shared schemas,
canonical chunk lookup and the application entry point will be extended as needed.
The existing Codex gateway will be reused, subject to its evidence-isolation gate.
No Phase 3 source files have been created.

Expected Phase 3 checks cover selected-paper filtering, deterministic RRF,
canonical metadata, bounded context, missing-evidence answers, invalid citations,
untrusted document instructions, gateway failures and chat/source display.
Per-paper comparison synthesis remains Phase 4; measured retrieval and
hallucination evaluation remains Phase 6.

Recommended commit message:
`feat: add phase 2 PDF ingestion and persistent indexes`

**Stop here: Phase 2 complete and approved for publication; Phase 3 awaits approval.**
