# Domain-Specific RAG Chatbot Using Large Language Models

A local research assistant for AI and Computer Science papers. **Phase 6 adds
reproducible three-mode retrieval evaluation and human claim-review workflows** to
the existing PDF library, hybrid retrieval, cited chat, paper-balanced comparisons
and recovery. Public benchmark labels remain draft until human review.

The approved architecture is unchanged. Generation remains **GPT-6.1 Sol
(`gpt-6.1-sol`) through signed-in Codex and the official Python SDK**. Uploading,
indexing and retrieval stay local. Generation sends the question and bounded
retrieved excerpts only when you permit it. There is no provider or API-key fallback.

- [Project progress and approval gates](PROJECT_PROGRESS.md)
- [Approved architecture reference](docs/ARCHITECTURE.md)
- [Phase 1 verification evidence](reports/PHASE1_REPORT.md)
- [Phase 2 implementation and validation](reports/PHASE2_REPORT.md)
- [Phase 3 implementation and validation](reports/PHASE3_REPORT.md)
- [Phase 4 implementation and validation](reports/PHASE4_REPORT.md)
- [Phase 5 implementation and validation](reports/PHASE5_REPORT.md)
- [Phase 6 implementation and measured evidence](reports/PHASE6_REPORT.md)
- [Evaluation and human-review guide](eval/README.md)
- [Setup and demonstration](docs/DEMO.md)
- [Git workflow](docs/GIT_WORKFLOW.md)

## Run the application

From this repository directory, using its existing environment:

```bash
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

Open the local URL shown in the terminal. Upload selectable-text English research
PDFs, click **Index uploaded papers**, and inspect the extracted and cleaned page
text. Select the papers you want to question. Confirm deletion to
remove a paper's PDF, catalog pages/chunks, Chroma vectors, and BM25 entries.
Close the app and restart with the same data folder to reopen the library.

To ask a question:

1. Select one or more indexed papers.
2. Enter a question in the chat box. Hybrid search runs locally and shows the
   retrieved passages; no Codex account is needed for this step.
3. To generate an answer, enable the excerpt-sharing checkbox and click
   **Generate cited answer**. The app uses only the approved signed-in Codex route.
4. Inspect each claim's source IDs and the **Validated citations** panel for the
   paper name, PDF page and canonical supporting passage.

Paper selection or corpus changes clear in-memory chat/evidence and reset consent.
The last six question contexts are kept in the current Streamlit session; answers
are not stored in SQLite. Ambiguous follow-ups need a named paper/method or a recent
user question. Earlier assistant answers are never used as documentary evidence.

To compare papers:

1. Select **2–12 indexed papers** and scroll to **Compare selected papers**.
2. Optionally enter a comparison focus and select categories: methodology,
   datasets, results, conclusions and limitations.
3. Click **Collect comparison evidence**. This searches each paper/category
   independently and previews the passages locally; it makes no model request.
4. Enable the comparison excerpt-sharing checkbox, then **Generate comparison**.
   The app validates one evidence card per uncached paper before synthesis.
5. Inspect the table, supported agreements/disagreements, reported experimental
   conditions, and original **Comparison source passages**.

Missing categories are labeled as gaps in the retrieved passages. Failed model
requests are shown as failures, not missing paper content. **Retry failed comparison
requests** reuses valid cached cards. Changing the focus, categories, selection
or corpus clears the preview/result and resets comparison consent. Restart the
app after updating so additive SQLite cache/issue tables are created and local
consistency checks run. Valid PDFs and vector entries are reused.

A library accepts **1–12 papers**, at most **25 MB and 200 pages per PDF**. Six to
twelve is the intended research workload; a single paper is enough to start.
Identical PDF bytes are detected even if the filename changes, without parsing
or embedding again. Different byte versions are treated as separate papers.

The first indexing operation downloads the pinned public
`sentence-transformers/all-MiniLM-L6-v2` model, approximately 90 MB of weights.
No Hugging Face API key is required for this public model. Embeddings run on the
local CPU; model assets are cached in `data/models`. Downloads need internet and
may encounter public-host rate limits. After caching, local indexing can run
offline. Healthy reopening and deletion never load the embedding model. Repairing
missing or damaged vectors loads the same local model and embeds only those chunks. The dependency environment itself is substantially larger than
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
historical Phase 1 snapshot. Phases 3–6 use the same installed dependency versions;
the existing LangSmith dependency is now explicitly pinned for disabling tracing.
No new third-party package or model was installed for Phases 3–6. Other platforms may require compatible wheels.
The environment and public model cache are not committed. After source edits,
repeat `pip install --no-deps .` with the environment's Python to refresh the
installed verification CLI. Running from the checkout uses its current source.

## LLM configuration and access

The application uses official `openai-codex==0.163.0` and its pinned app-server
runtime with exact `gpt-6.1-sol`. Sign in through Codex; do not put credentials in
this repository:

```bash
codex login
# Optional shell configuration; .env is not automatically loaded:
export RAG_CODEX_TIMEOUT_SECONDS=60
.venv/bin/python -m src.verification
```

The last command checks this account's authentication/model access without model
generation. The signed-in account must actually expose the selected model; there
is no default-model/API-key fallback. Live `--live` checks below consume Codex
allowance. A ChatGPT subscription is not treated as direct OpenAI API credits.
Do not add `OPENAI_API_KEY`, copy an auth cache, or purchase credits automatically.

Retrieved canonical LangChain Documents become bounded prompt passages with source
IDs, filenames and PDF page numbers before the existing gateway is invoked. The
LLM is given the question and these excerpts; it does not open the uploaded PDF.
Source validation resolves output IDs to stored passages. Review passages for
semantic support: structural citation validation alone does not establish truth.

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

## How Phase 3 works

```text
Question + selected active papers
  → bounded question processing (recent user question for simple follow-ups)
  → selected-paper BM25 + local MiniLM query embedding / Chroma search
  → equal-weight RRF, deduplication and bounded context
  → canonical chunks as LangChain Documents
  → local passage preview
  → explicit excerpt-sharing consent
  → LangChain prompt → isolated Codex gateway → structured claims/source IDs
  → schema + canonical citation checks → answer/source display
```

Both retrieval methods filter before top-K ranking. Defaults are 20 candidates
per method, rank constant 60, and at most eight context chunks/16,000 passage
characters. Ranks start at one; a missing candidate contributes zero. RRF scores
are ranking signals, never answer-confidence percentages. Same-page exact or
subsumed passages are removed conservatively; similar passages with different
experimental numbers are retained. Overlong dense questions are rejected before
MiniLM can silently truncate them. BM25-only and vector-only modes are available
programmatically for later evaluation; the chat uses hybrid search.

LangChain runnable composition connects retrieval, prompt construction, the
existing Codex generation boundary and source validation. LlamaIndex still owns
ingestion/indexing; querying does not rebuild the corpus or create another store.
BM25 refreshes its loaded snapshot after corpus changes. Citation validation uses
only retrieved, selected, still-active canonical chunks. Model-written filenames,
pages or quotations are never trusted. One schema/source-ID repair is permitted;
an unresolved answer is withheld. SDK failures are not automatically retried with
another model. Missing passages/evidence produce an explicit acknowledgment.

The stricter `EvidenceGateway` reuses Phase 1 authentication, exact-model checks,
turn handling and timeout/cancellation. Each request discovers configuration with
no model turn, disables inherited MCP servers/plugins/skills, and then audits the
effective configuration. The answer thread uses a restricted read-only profile
limited to its temporary directory and platform defaults, with tool network access
disabled. Hooks, notifications, web/shell/image tools, memory, subagents and
telemetry export are disabled for that worker. Inherited instruction files are
rejected. Service endpoint checks accept only the official OpenAI/ChatGPT hosts.
User configuration and authentication are not edited or copied.

LangChain tracing is also disabled in the application process around retrieval
and generation, so inherited tracing settings cannot export questions/passages.
The pinned SDK lacks high-level helpers for the needed inspection RPCs; a small
adapter accesses its low-level official SDK client and checks the raw thread
permission response. Incompatible/unverifiable settings disable generation while
retaining local retrieval. Revalidate this boundary before changing SDK versions.

## How Phase 4 works

```mermaid
flowchart TD
    A[Selected papers and comparison categories] --> B[Separate BM25 and vector retrieval for each paper/category]
    B --> C[Local passage preview and sharing consent]
    C --> D[Validated cached card or isolated Codex card request]
    D --> E[Validate category coverage and original source IDs]
    E --> F[LangChain comparison synthesis]
    F --> G[Validate table coverage, citations and reported experimental conditions]
    G --> H[Comparison table, relationships and original PDF passages]
```

Each paper/category receives eight sparse and eight dense candidates. The existing
RRF implementation keeps up to two passages per category, with a total per-paper
passage budget of 16,000 characters. One paper cannot consume another's budget.
Source IDs are canonical chunk IDs, stable across paper ordering and cached cards.

One structured card request per paper extracts cited findings. Results can include
reported task, dataset, split, metric, value and settings; absent fields remain
unknown. A second chain selects validated card entries for every table cell and
generates cited relationships. The app renders the selected entry text rather
than accepting independently invented table facts. Every relationship must cite
category evidence from each named paper. All source panels resolve to the original
canonical passages, not an intermediate card.

Result agreements/disagreements require complete matching reported task, dataset,
split, metric and settings. Missing or mismatching fields produce **not directly
comparable** assessments. Matching uses conservative case/whitespace normalization,
not semantic equivalence or unit conversion; matching labels do not establish a
fair scientific experiment. Different numbers or methods are not automatically
contradictions. Source support still requires human/evaluation review.

Validated cards are cached in the existing local SQLite catalog using paper version,
focus, categories, model, card-prompt version, retrieval settings and retrieved
source IDs. Cache reads are revalidated against current canonical records. Invalid
card JSON is regenerated; deleting a paper cascades to its cards. Retention is
bounded to 16 cards per paper. Comparison results remain session-only, and synthesis
runs again even when all cards are cached.

Each card/synthesis request has at most two attempts total: an initial request and
one transient retry or schema/citation repair. Authentication, model or isolation
failures, exhausted allowance, rate limits and rejected requests stop further generation. A failed card withholds synthesis until all
selected papers have validated cards; successful cards remain cached for retry.
No new SDK worker, provider, embedding model or vector store is introduced.

## Recovery and source inspection

Use **Check and recover local library** in the sidebar after a failed storage
operation or an external local-file change. Startup runs the same checks under
one library lock. Recovery never sends documents to an LLM.

- Interrupted upload/deletion cleanup is repeatable. Healthy saved sources remain
  available after recovery; incomplete operations cannot feed generation.
- Missing, changed or inconsistent source papers appear as **unavailable**, with
  restore/delete guidance. Their canonical records are preserved. Restore the
  exact PDF/backup and run recovery, or explicitly delete and upload again.
  Unavailable papers count toward the twelve-paper limit.
- Missing/damaged derived vector entries are recreated through LlamaIndex/MiniLM.
  BM25 is rebuilt from canonical text when missing, stale or inconsistent. The
  stronger Phase 5 snapshot signature causes a one-time local BM25 rebuild;
  it does not reparse PDFs, rechunk or re-embed healthy papers.
- Orphan vector entries and abandoned hash-named PDFs in the app's paper folder
  are cleaned; unmanaged filenames are preserved. Corrupt SQLite/Chroma storage
  receives a safe diagnostic and can require a backup; the database is not reset.
- Recovery/deletion invalidates old answers, comparisons, previews and consent.
  Valid evidence cards survive derived-index repair and are revalidated on reuse.
- In retrieved passages and citation panels, **Inspect this PDF page in the paper
  library** opens the matching saved paper/page's original and cleaned extracted
  text. It preserves the selected research scope; it is not a PDF image renderer.

Generation errors distinguish missing/expired sign-in, exhausted Codex allowance,
rate limits, context limits and network failures when the SDK provides a recognized
structured code. Unknown errors stay generic. For sign-in, run `codex login`; for
usage limits, wait/check account allowance. Local search remains available. No model,
authentication, credit purchase or paid API fallback occurs. The pinned official
SDK's public turn stream preserves these codes; its convenience `run()` flattens
failed turns. Existing isolation and timeout/cancellation checks still apply.
Application logs use fixed error/event codes and counts without private content.

## Phase 6 evaluation

The Streamlit architecture and model/authentication remain unchanged. Evaluation
uses local Python services/CLI, with no new REST endpoints or third-party package.

After preparing the versioned public PDFs and frozen draft dataset as described in
[the evaluation guide](eval/README.md), run the complete local retrieval comparison:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.evaluation.cli --data-dir data/evaluation/public-six/library run --dataset data/evaluation/public-six/dataset.json --allow-draft --output eval/results/public-six-run.json
```

This makes **zero LLM requests** and preserves BM25/vector/hybrid budgets and
paper/category balancing. It reports raw Precision/Recall/MRR at K=5/10 separately
from retained-context quality, required-paper coverage, timing and split/task strata.
The output is explicitly exploratory while labels are draft. In the measured run,
hybrid did not outperform BM25 under the draft labels; no improvement is invented.

Generation evaluation requires `--generate --allow-remote --max-model-requests N`.
The default request budget is zero. Existing Codex allowance applies; no API credits
or paid judge are assumed. Valid answers/cards are cached and revalidated against
canonical source records, and label-review changes alone do not force regeneration.
Cache timing is kept separate from fresh-model timing. Budget exclusions and failures
are not counted as good abstentions.

Use `review-template` to produce pending human atomic-claim/citation judgments and
`review-score` after a person completes them. Unsupported/pending/uncertain claims
and review coverage remain explicit; empty answers never receive automatic perfect
faithfulness. Structural citation validity is separate from semantic passage support.
Ragas remains optional and disabled because the existing Codex runnable's judge
compatibility is unverified; no provider/authentication fallback is added.

The six public PDFs/indexes, frozen canonical labels, answer caches, review sheets
and raw runs remain under ignored `data/` or `eval/results/`. Only public-safe paper
references, draft definitions and curated aggregate reports are publishable. Source
inspection can explicitly print passages locally; do not publish private output.
See [the demo guide](docs/DEMO.md) for setup and an end-to-end walkthrough.

Explicit synthetic live evaluation verification (up to six application model calls):

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.phase6_verification --live --report reports/phase6-check.json
```

`rag-evaluate` and `rag-verify-evaluation` are installed equivalents after refreshing
the local package. Use new output filenames; existing datasets/reports are preserved.

## Important files

| File | Purpose |
| --- | --- |
| `app.py`, `.streamlit/config.toml` | Local Streamlit entry point, upload cap, telemetry preference |
| `src/ui/documents.py` | Batch uploads, saved papers, selection, page preview, confirmed deletion |
| `src/config.py` | Separate ingestion, retrieval and fixed-model Codex settings |
| `src/schemas.py` | Canonical source records, structured claims, citations and answer results |
| `src/ingestion/pdf.py`, `cleaning.py` | Page-aware PyMuPDF reader, layout warnings, conservative cleanup |
| `src/ingestion/chunking.py` | Token-aware LlamaIndex chunks and stable IDs |
| `src/embeddings.py` | Lazy CPU MiniLM via LlamaIndex's Sentence Transformers integration |
| `src/ingestion/indexing.py` | The single LlamaIndex-to-Chroma writer |
| `src/ingestion/pipeline.py` | Document lifecycle, duplicate detection, locking, and cleanup |
| `src/persistence.py` | SQLite catalog, canonical chunk lookup and active-corpus version |
| `src/retrieval/bm25.py`, `vector.py`, `hybrid.py` | Sparse/dense filtering, RRF and context selection |
| `src/retrieval/adapters.py` | Actual LangChain Documents and retrieval runnable |
| `src/generation/llm.py`, `runtime.py`, `src/verification.py` | Fixed-model gateway, public SDK streaming, safe structured errors and verifier |
| `src/generation/isolation.py` | Mandatory worker configuration and thread-permission checks |
| `src/generation/prompts.py`, `chains.py`, `citations.py` | Versioned prompts, orchestration, one repair and canonical citations |
| `src/ui/chat.py` | Local question search, consent, answers and source panels |
| `src/retrieval/comparison.py` | Per-paper/category budgets and comparison evidence snapshots |
| `src/generation/comparison.py` | Card generation/cache reuse, bounded retries and synthesis |
| `src/generation/comparison_validation.py` | Card/table/relationship provenance and experimental-context checks |
| `src/ui/comparison.py` | Local preview, consent, comparison tables, failures and original sources |
| `src/phase3_verification.py` | Explicit isolation/canary and optional live synthetic RAG verifier |
| `src/phase4_verification.py` | Explicit synthetic multi-paper comparison and card-cache verifier |
| `src/ingestion/recovery.py` | Canonical consistency, unavailable sources, idempotent derived-index repair |
| `src/ui/maintenance.py`, `sources.py` | Recovery controls, unavailable-paper guidance, navigation and state invalidation |
| `src/evaluation/` | Frozen labels, custom metrics, three-mode runner, budget/cache and human review |
| `src/phase6_verification.py` | Explicit isolated synthetic evaluation and answer-cache check |
| `eval/`, `docs/DEMO.md` | Public draft definitions and reproducible evaluation/demo instructions |
| `tests/` | Existing regressions plus recovery and evaluation contracts/integration tests |

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
.venv/bin/python -m pytest -q
# Include all five real MiniLM integration tests (first use may download public weights):
HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q --junitxml=reports/phase6-all-tests.xml
.venv/bin/python -m pip check
```

The standard suite uses synthetic PDFs and deterministic test embeddings while
exercising real PyMuPDF, LlamaIndex, Chroma, BM25, SQLite, Streamlit and LangChain.
No pytest test makes an LLM request. The five real embedding tests are skipped
unless opted in. After public model caching, the full suite can run with
`HF_HUB_OFFLINE=1`. Results and limits are in the [Phase 6 report](reports/PHASE6_REPORT.md).

Latest Phase 6 validation (November 7, 2026): **350 tests passed, none skipped**,
including all 298 existing Phase 1–5 tests and five real MiniLM integrations. The
separate synthetic live evaluation check passed through signed-in `gpt-6.1-sol`
with six model requests; repeating the six cases used zero requests through cache.
No real benchmark paper was sent to a hosted model. The 90-case public retrieval
run used zero LLM calls. Scientific label/claim review remains pending.

Explicit worker verification (requires signed-in Codex and OS execution permission):

```bash
# Effective settings, temporary thread and synthetic filesystem checks; no model inference:
.venv/bin/python -m src.phase3_verification --report reports/phase3-isolation.json
# Optional synthetic injection, cited RAG answer and missing-evidence checks:
HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m src.phase3_verification --live --report reports/phase3-live.json
```

`rag-verify-rag` is the installed equivalent. `--live` consumes Codex allowance:
normally three turns, up to five if either RAG response requires its one repair.
The filesystem verifier uses `/bin/cat` and has been tested on macOS, not Windows.
It reads only generated control/canary files. JSON/XML reports remain local and ignored.

Explicit Phase 4 verification:

```bash
# Existing isolation checks only; no model inference:
.venv/bin/python -m src.phase4_verification --report reports/phase4-isolation.json
# Generated two-paper comparison, agreements/disagreements, gaps and cached-card reuse:
HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m src.phase4_verification --live --report reports/phase4-live.json
```

`rag-verify-comparison` is the installed equivalent. Its live check normally uses
four model requests, up to eight with bounded retries/repairs. The recorded live
run used four. It submits generated synthetic passages only.

Phase 1's verifier still works:

```bash
.venv/bin/python -m src.verification
# Optional synthetic inference; consumes Codex usage:
.venv/bin/python -m src.verification --live --report reports/phase1-verification.json
```

The default verifier checks account/model metadata without generation. The exact
model is required: no fallback or API-key authentication. Phase 1 previously
verified a live structured LangChain response through the official SDK and
existing ChatGPT-managed Codex sign-in. Phase 3 separately verifies the stricter
evidence worker and synthetic RAG workflow.

## Limits and costs

- Text extraction uses line geometry to improve two-column reading order, but it
  is a heuristic. Check the preview. PDF page positions can differ from printed
  page labels. Scans need OCR and are rejected when there is no usable text;
  sparse/blank pages remain visible with warnings. Figures, equations, complex
  tables, and layout-dependent meaning are not reliably interpreted.
- Source IDs, selected papers, canonical passages and PDF pages are validated.
  This establishes traceability, not semantic support for every claim. Retrieval
  quality metrics now have local evaluation tools. Final relevance labels and
  semantic faithfulness/hallucination scores still require human review; no accuracy
  improvement or general injection immunity is claimed from synthetic checks.
- This is a single-user local app. Recovery checks run on startup or explicit
  request and add local disk I/O; external changes after startup require another
  check/restart. A structurally valid but semantically wrong vector cannot always
  be detected without re-embedding. Missing canonical data/physical database
  corruption may require backups. Joblib snapshots must be trusted app-local files.
  Deletion removes application data logically, not forensic traces or backups.
- No hosted model fee is incurred by Phase 2. Local tools/model downloads use
  disk, CPU, and internet bandwidth. PyMuPDF's existing AGPL/commercial licensing
  decision remains relevant before distribution; no license choice is changed.
- Phase 3 answer generation uses the account's Codex allowance, including any
  explicit repair. No API credits are assumed or purchased. SDK runtime startup
  can need OS execution permission in the desktop sandbox. Account entitlement,
  quotas and managed restrictions can change; failed isolation checks disable
  generation. The live tests used generated evidence only, not private papers.
- Phase 4 normally uses one card request per uncached paper plus one synthesis
  request. Cached cards save their generation calls; final synthesis still uses
  allowance. Larger comparisons can take longer. Reported-condition matching and
  structural source validation do not replace scientific or faithfulness review.
- Chat history is session-only and cleared when source scope changes. Ambiguous
  follow-ups use a simple bounded rule. Broad PDF quality, adversarial coverage,
  manual browser file-upload transport and other operating systems remain untested.

## Git workflow and stop point

Phases 1–5 have been published to
[sumanyuu10/domain-specific-rag-chatbot](https://github.com/sumanyuu10/domain-specific-rag-chatbot).
Phase 6 implementation and automated testing are completed. The user reviewed
and approved publication of the tooling on November 7, 2026. Public benchmark
labels and generated claims still await human review; scientific validation is
not completed. Approved Phase 6 commit message:

```text
feat: add phase 6 reproducible RAG evaluation and review workflow
```

`.gitignore` excludes `.env` variants, credentials, PDFs/private documents, local
databases/vectors/models, caches, environments, build output, and raw reports.
Only `.env.example`, source, tests, and curated documentation are publishable.
Publication follows the [Git workflow](docs/GIT_WORKFLOW.md); future phase commits
and pushes require their own approval.
**Stop after the authorized Phase 6 publication. Human benchmark review remains
open. The approved roadmap defines no later phase; further work needs explicit
scope approval.** See [the remaining acceptance tasks](PROJECT_PROGRESS.md#next-phase-in-the-approved-roadmap).

## Implementation references

- [LlamaIndex ingestion pipeline](https://developers.llamaindex.ai/python/framework/module_guides/loading/ingestion_pipeline/)
- [LlamaIndex Chroma integration](https://github.com/run-llama/llama_index/blob/main/llama-index-integrations/vector_stores/llama-index-vector-stores-chroma/llama_index/vector_stores/chroma/base.py)
- [MiniLM model card](https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2)
- [PyMuPDF extraction](https://pymupdf.readthedocs.io/en/latest/recipes-text.html)
- [Streamlit upload widget](https://docs.streamlit.io/develop/api-reference/widgets/st.file_uploader)
- [Codex SDK](https://learn.chatgpt.com/docs/codex-sdk)
- [Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference)
- [App-server configuration and thread interfaces](https://learn.chatgpt.com/docs/app-server)
