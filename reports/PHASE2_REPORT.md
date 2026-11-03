# Phase 2 implementation report

Date: November 3, 2026. Scope: approved PDF ingestion, local indexing, and document
management only. Phase 1 was already published. The user reviewed Phase 2 and
authorized its commit and push; Git history records publication. Phase 3 has
not started.

## Implemented behavior

The working Streamlit application accepts up to 12 research PDFs, indexes each
paper once, displays selectable papers and extracted page text, and deletes a
paper from its local PDF/catalog/vector/sparse stores. The file cap is 25 MB and
page cap 200. Identical bytes are deduplicated independently of filenames.

PyMuPDF extracts local page text. A thin LlamaIndex reader preserves one-based
PDF page metadata; its standard `load_data` returns LlamaIndex Documents, while
`read_pdf` also returns original/cleaned text and warnings for the catalog/UI.
Line geometry provides a column-order heuristic; previews expose limitations.
Conservative cleaning retains experimental values and technical punctuation.

LlamaIndex SentenceSplitter uses the real MiniLM tokenizer, defaults to 220 tokens
with 40 overlap, and keeps chunks within one PDF page. Deterministic IDs include
paper bytes, pipeline fingerprint, PDF page and chunk ordinal. Metadata is not
embedded. LlamaIndex's HuggingFaceEmbedding invokes local CPU Sentence Transformers
at a pinned MiniLM revision. LlamaIndex's ChromaVectorStore is the sole vector
writer. There is one embedding per chunk, normalized to 384 dimensions, with cosine
distance. SQLite and rank-bm25 use the same canonical chunks/IDs.

Chroma, PDF and catalog persistence survive reopening. BM25 restores its atomic
Joblib snapshot or rebuilds it from SQLite without embeddings. A single file lock
and explicit paper states support failure cleanup and startup cleanup of incomplete
operations. Incompatible pipeline settings are rejected while preserving data.
No question answering, hybrid query/RRF, comparison synthesis or citation-validation
feature was added. The existing LangChain/Codex gateway remains unchanged.

## Files created or modified

| Files | Change and purpose |
| --- | --- |
| `app.py`, `.streamlit/config.toml`, `src/ui/__init__.py`, `src/ui/documents.py` | New local Streamlit document-management application |
| `src/schemas.py`, `src/persistence.py` | New canonical contracts and SQLite catalog |
| `src/ingestion/__init__.py`, `pdf.py`, `cleaning.py`, `chunking.py`, `indexing.py`, `pipeline.py` | New page extraction, LlamaIndex pipeline and document lifecycle |
| `src/embeddings.py` | New lazy local MiniLM embedding service |
| `src/retrieval/__init__.py`, `src/retrieval/bm25.py` | New persistent sparse index construction; query orchestration remains later |
| `src/config.py`, `.env.example` | Add separate local-ingestion configuration; preserve fixed Codex settings |
| `pyproject.toml`, `requirements-phase2.lock` | Pin actual tested Phase 2 dependencies; retain Phase 1 pins/lock |
| `tests/conftest.py`, `test_ingestion.py`, `test_documents_ui.py`, `test_embedding_integration.py` | Synthetic fixtures and new component/integration/UI tests |
| `README.md`, `PROJECT_PROGRESS.md`, `docs/GIT_WORKFLOW.md`, this report | Current usage, decisions, test results, phase boundaries and review workflow |

No working Phase 1 gateway, verifier or existing tests were overwritten. The approved
architecture reference and diagram are unchanged. `.gitignore` required no change;
its existing rules exclude the new data, model caches and raw reports.

## Verification evidence

Final full-suite command, after the initial public model download:

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q --tb=short --junitxml=reports/phase2-all-tests.xml
```

**Result: 112 passed, 0 skipped, 0 failed, 9.56 seconds.**

Publication revalidation on November 3, 2026: **112 passed, 0 skipped, 0 failed,
9.85 seconds**, using the same full-suite command. Dependency consistency passed;
Phase 1 gateway/verifier/tests/lock files remain unchanged. This revalidation did
not repeat live Codex inference or a manual browser upload transport check.
The local Streamlit HTTP smoke check passed again. The desktop execution
sandbox initially blocked a localhost socket; the check succeeded with approved
OS execution permission, without an application change. Fetching GitHub history
likewise required network access outside the execution sandbox.

| Check | Result and scope |
| --- | --- |
| Existing Phase 1 regression and Git hygiene | All 78 passed, including installed CLI/package checks |
| PDF/index/lifecycle tests | 29 passed with real PyMuPDF, LlamaIndex, Chroma, BM25 and SQLite; deterministic test embeddings |
| Streamlit AppTest | Four passed: empty boot, paper preview/selection/delete, upload action with invalid/valid files, safe configuration error |
| Actual MiniLM integration | Passed on CPU; normalized 384-dimensional vectors, tokenizer limit, metadata contract, real Chroma query, LangChain Document compatibility, restart, duplicate and deletion |
| Twelve-paper persistence | Passed with deterministic embeddings; new Python interpreter reopened the saved catalog/Chroma/BM25 without model loading or reindexing |
| Failure cases | Corrupt/encrypted/empty/non-PDF/over-limit files; sparse/blank pages; embedding/vector/BM25 failures; interrupted operations; stale/corrupt/missing snapshots; incompatible pipeline settings |
| Dependency consistency | `pip check`: no broken requirements; direct pins match the complete lock |
| Package build/install | Normal local wheel build/install passed; Phase 1 installed CLI tests passed |
| Actual Streamlit server | Started/stopped locally; health and HTML routes returned HTTP 200 |
| Publish boundary | Data/model/index/report paths ignored; source candidates passed known-key-pattern, syntax, whitespace and local-link checks; exact staged contents are checked before committing |

The initial download-enabled real-model test also passed (122.24 seconds including
network/model setup). That is a setup observation, not a performance benchmark.
All fixtures contain synthetic research text. No private paper was uploaded to a
model provider, no LLM call was made, and no account/authentication setting changed.

Raw XML reports are local and ignored. `reports/phase2-all-tests.xml` is the final
complete run. Earlier intermediate reports may have smaller test counts. The
standard test command intentionally skips the opt-in actual-model test; the final
explicit full run above skipped nothing.

## Errors found and resolved

- PyMuPDF grouped two synthetic columns into one block. Using line bounding boxes
  fixed the observed order; a regression test checks the column sequence.
- The Hugging Face Xet downloader initially tried a cache/log location outside the
  desktop sandbox. A process-level `HF_XET_CACHE` pointing to ignored
  `data/models/xet` resolved the permission error. Same model/revision and no key.
- Streamlit paper selection initially retained a deleted final paper ID. Selection
  cleanup now runs for empty libraries too, covered by the delete test.
- The reader exposes LlamaIndex's standard list-of-Documents contract alongside a
  named extraction result for original text and diagnostics.
- Unexpected extraction errors are converted to an actionable error before any
  paper data is written. Failed batches can continue to the next valid PDF.
- A Sentence Transformers renamed-method warning in the test was fixed by using
  the current method. Five upstream PyMuPDF/SWIG deprecation warnings remain.

No required Phase 2 automated check remains blocked. Full manual browser file
upload transport and representative real-paper layout review were not performed.
AppTest supplies the upload interface; HTTP checks verify the real server separately.

## Remaining limits and approval boundary

Scans require OCR; figure/math/complex-table understanding is not provided.
Column order is heuristic. Metadata preservation is not proof of claim support.
Retrieval quality, RRF, citation correctness and hallucinations are evaluated only
once their later-phase functionality exists. No quality improvement is claimed.

Basic lifecycle recovery is implemented; comprehensive corruption recovery remains
Phase 5. Joblib snapshots must be trusted, and deletion is logical rather than
forensic. Other operating systems and hardware were not tested.

Before real excerpts reach Codex in Phase 3, finish the evidence-isolation gate
including inherited MCP/skill/hook review. The model/authentication selection is
unchanged: `gpt-6.1-sol`, signed-in Codex, official Python SDK.

Recommended commit:
`feat: add phase 2 PDF ingestion and persistent indexes`

**Phase 2 publication is approved. Stop before Phase 3 until separately approved.**
