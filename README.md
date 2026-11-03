# Domain-Specific RAG Chatbot Using Large Language Models

A local research assistant for AI and Computer Science papers. **Phase 2 is
implemented: PDF upload, inspection, management, and persistent local indexes.**
Question answering, hybrid retrieval/RRF, comparisons, citation validation, and
quality evaluation remain in their approved later phases.

The approved architecture is unchanged. Generation remains **GPT-6.1 Sol
(`gpt-6.1-sol`) through signed-in Codex and the official Python SDK**. Phase 2
does not call Codex or send paper text to a hosted model.

- [Project progress and approval gates](PROJECT_PROGRESS.md)
- [Approved architecture reference](docs/ARCHITECTURE.md)
- [Phase 1 verification evidence](reports/PHASE1_REPORT.md)
- [Phase 2 implementation and validation](reports/PHASE2_REPORT.md)
- [Git workflow](docs/GIT_WORKFLOW.md)

## Run the application

From this repository directory, using its existing environment:

```bash
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

Open the local URL shown in the terminal. Upload selectable-text English research
PDFs, click **Index uploaded papers**, and inspect the extracted and cleaned page
text. Select papers for future questions and comparisons. Confirm deletion to
remove a paper's PDF, catalog pages/chunks, Chroma vectors, and BM25 entries.
Close the app and restart with the same data folder to reopen the library.

A library accepts **1–12 papers**, at most **25 MB and 200 pages per PDF**. Six to
twelve is the intended research workload; a single paper is enough to start.
Identical PDF bytes are detected even if the filename changes, without parsing
or embedding again. Different byte versions are treated as separate papers.

The first indexing operation downloads the pinned public
`sentence-transformers/all-MiniLM-L6-v2` model, approximately 90 MB of weights.
No Hugging Face API key is required for this public model. Embeddings run on the
local CPU; model assets are cached in `data/models`. Downloads need internet and
may encounter public-host rate limits. After caching, local indexing can run
offline. Opening, deleting, or reopening already indexed papers never loads the
embedding model. The dependency environment itself is substantially larger than
the model; allow several GB of disk space.

The optional exported variable `RAG_DATA_DIR` selects another local data folder.
It defaults to this source checkout's `data/` when run as above. `.env.example`
documents settings; no dotenv loader reads `.env` automatically. Use an ignored
or outside-repository folder if overriding the default.

In restricted desktop sandboxes, Hugging Face's Xet downloader may need its cache
redirected into an allowed folder before the process starts:

```bash
HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m streamlit run app.py
```

This changes only a local download-cache location, not the model or sign-in.

## Set up a fresh environment

Use Python 3.11+; this combination was tested with **Python 3.12.14 on Apple
Silicon**. The system Python on the development machine is older and was not
modified. For example, with Python 3.12 installed:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --no-cache-dir -r requirements-phase2.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m pip check
.venv/bin/python -m pytest -q
.venv/bin/python -m streamlit run app.py
```

`pyproject.toml` pins direct dependencies. `requirements-phase2.lock` records the
complete tested environment; `requirements-phase1.lock` is retained as the
historical Phase 1 snapshot. Other platforms may require compatible wheels.
The environment and public model cache are not committed. After source edits,
repeat `pip install --no-deps .` with the environment's Python to refresh the
installed verification CLI. Running from the checkout uses its current source.

## How Phase 2 works

```text
Streamlit PDF upload
  → SHA-256 duplicate/capacity checks
  → PyMuPDF reader: one LlamaIndex Document per PDF page
  → original + conservatively cleaned page text in SQLite
  → LlamaIndex SentenceSplitter with MiniLM's tokenizer
  → canonical chunk records and deterministic IDs
  → LlamaIndex HuggingFaceEmbedding / local Sentence Transformers
  → LlamaIndex ChromaVectorStore / persistent local Chroma
  → rank-bm25 snapshot over the same canonical chunks
```

LlamaIndex owns chunking, embedding, and vector writing. It does not create a
second independent corpus or duplicate embeddings. SQLite stores canonical
passages and metadata. Chroma and BM25 share chunk IDs, paper IDs, display titles,
filenames, and one-based PDF page positions. Metadata is excluded from the text
sent to MiniLM. The default 220-token chunks have 40-token overlap and are checked
against the 256-token embedding limit, including special tokens. Vectors have
384 dimensions, are normalized, and use cosine distance.

The exact model revision is
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. A configuration fingerprint prevents
mixing vectors with a different model or chunking scheme in an existing library.
Use the original configuration or a new empty data folder; there is no automatic
reindexing or silent model substitution.

A file lock serializes document lifecycle operations. Processing/deleting states
hide incomplete papers. Failed ingestion removes partial records/vectors; startup
retries cleanup of interrupted operations. BM25 snapshots are saved atomically
and restored on restart; missing, corrupt, or stale snapshots are rebuilt from
SQLite without re-embedding. Only load snapshots created by this application;
Joblib is not a safe format for importing untrusted files.

The existing LangChain/Codex gateway remains intact. Phase 3 will read these
canonical chunks into LangChain retrieval chains, filter selected papers, fuse
rankings with RRF, and validate citations. No question-answering or comparison
logic has been implemented ahead of that phase.

## Important files

| File | Purpose |
| --- | --- |
| `app.py`, `.streamlit/config.toml` | Local Streamlit entry point, upload cap, telemetry preference |
| `src/ui/documents.py` | Batch uploads, saved papers, selection, page preview, confirmed deletion |
| `src/config.py` | Separate local-ingestion settings and unchanged fixed-model Codex settings |
| `src/schemas.py` | Canonical paper, page, chunk, and error contracts |
| `src/ingestion/pdf.py`, `cleaning.py` | Page-aware PyMuPDF reader, layout warnings, conservative cleanup |
| `src/ingestion/chunking.py` | Token-aware LlamaIndex chunks and stable IDs |
| `src/embeddings.py` | Lazy CPU MiniLM via LlamaIndex's Sentence Transformers integration |
| `src/ingestion/indexing.py` | The single LlamaIndex-to-Chroma writer |
| `src/ingestion/pipeline.py` | Document lifecycle, duplicate detection, locking, and cleanup |
| `src/persistence.py` | SQLite catalog, pages, chunks, and configuration checks |
| `src/retrieval/bm25.py` | Technical-token BM25 construction and local snapshot persistence |
| `src/generation/llm.py`, `src/verification.py` | Unchanged Phase 1 official Codex gateway and verifier |
| `tests/` | Phase 1 regression, ingestion/index persistence, Streamlit, real-model opt-in checks |

Local runtime layout (all ignored):

```text
data/
  catalog.sqlite3
  library.lock
  papers/<sha256>.pdf
  chroma/
  bm25.joblib
  models/
```

## Tests and verification

```bash
.venv/bin/python -m pytest -q --junitxml=reports/phase2-tests.xml
HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest tests/test_embedding_integration.py --run-embedding-integration -q
.venv/bin/python -m pip check
```

The standard suite uses synthetic PDFs and deterministic test embeddings while
exercising real PyMuPDF, LlamaIndex, Chroma, BM25, SQLite, and Streamlit. It does
not make LLM calls. The explicit integration test downloads/uses actual MiniLM
weights on CPU and checks dimensions, normalization, token limits, shared source
metadata, restart, duplicate handling, and deletion. Test results and remaining
limits are recorded in the [Phase 2 report](reports/PHASE2_REPORT.md).

Phase 1's verifier still works:

```bash
.venv/bin/python -m src.verification
# Optional synthetic inference; consumes Codex usage:
.venv/bin/python -m src.verification --live --report reports/phase1-verification.json
```

The default verifier checks account/model metadata without generation. The exact
model is required: no fallback or API-key authentication. Phase 1 previously
verified a live structured LangChain response through the official SDK and
existing ChatGPT-managed Codex sign-in. Those results are historical; no new
Codex inference is needed for Phase 2.

## Limits and costs

- Text extraction uses line geometry to improve two-column reading order, but it
  is a heuristic. Check the preview. PDF page positions can differ from printed
  page labels. Scans need OCR and are rejected when there is no usable text;
  sparse/blank pages remain visible with warnings. Figures, equations, complex
  tables, and layout-dependent meaning are not reliably interpreted.
- Source metadata is preserved, but citation validation and hallucination or
  retrieval-quality measurement belong to later phases. No accuracy improvement
  is claimed from these ingestion tests.
- This is a single-user local app. Document status recovery handles basic partial
  operations; comprehensive corruption/recovery and UI refinement remain Phase 5.
  Deletion removes application data logically, not forensic traces or backups.
- No hosted model fee is incurred by Phase 2. Local tools/model downloads use
  disk, CPU, and internet bandwidth. PyMuPDF's existing AGPL/commercial licensing
  decision remains relevant before distribution; no license choice is changed.
- Before real excerpts enter Codex in Phase 3, review inherited MCP/skill/hook
  configuration and finish the evidence-isolation gate. Read-only execution alone
  is insufficient. SDK runtime startup can need OS execution permission in the
  desktop sandbox. Account entitlement and quotas can change.

## Git workflow and stop point

Phase 1 has been published to
[sumanyuu10/domain-specific-rag-chatbot](https://github.com/sumanyuu10/domain-specific-rag-chatbot).
Phase 2 is complete, tested, reviewed, and approved for publication. Git history
records the phase commits. Phase 3 implementation requires separate approval.
Phase 2 commit message:

```text
feat: add phase 2 PDF ingestion and persistent indexes
```

`.gitignore` excludes `.env` variants, credentials, PDFs/private documents, local
databases/vectors/models, caches, environments, build output, and raw reports.
Only `.env.example`, source, tests, and curated documentation are publishable.
Publication follows the [Git workflow](docs/GIT_WORKFLOW.md); future phase commits
and pushes require their own approval.
**Stop after Phase 2; Phase 3 requires explicit approval.**

## Implementation references

- [LlamaIndex ingestion pipeline](https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/)
- [LlamaIndex Chroma integration](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/vector_stores/llama-index-vector-stores-chroma/llama_index/vector_stores/chroma/base.py)
- [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [PyMuPDF extraction](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)
- [Streamlit upload widget](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)
