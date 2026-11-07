# Project progress

Last updated: November 7, 2026.

## Current phase

**Phase 5 — recovery, service failures and source/UI refinement.**
Implementation and validation are complete. The user reviewed Phase 5 and approved
its commit and push on November 7, 2026. This publication follows the checks in the
Phase 5 report. Phase 6 requires separate explicit approval and has not started.

## Completed phases

### Phase 1 — published

Official Codex Python SDK with ChatGPT-managed sign-in and exact `gpt-6.1-sol`,
LangChain gateway, structured output, account/model checks, timeout/cancellation,
temporary runtime cleanup and safe errors. Original gateway/hygiene tests remain.
Commit `063b8b6`; see [the Phase 1 report](reports/PHASE1_REPORT.md).

### Phase 2 — published

Local Streamlit PDF library, PyMuPDF page metadata, LlamaIndex chunks, actual local
MiniLM embeddings, persistent Chroma/BM25 and canonical SQLite records. Includes
limits, deduplication, restart reuse, deletion, fingerprint validation and basic
lifecycle cleanup. Commit `cffa5e6`; see [the Phase 2 report](reports/PHASE2_REPORT.md).

### Phase 3 — published

Selected-paper sparse/dense retrieval, RRF, LangChain question answering, canonical
citations, missing-evidence acknowledgment, bounded repair and consent-based chat.
The isolated evidence worker audits effective configuration/thread permissions,
restricts file/network/tool capabilities and disables inherited tracing. All 181
tests passed at publication, along with live synthetic isolation/RAG checks.
Commit `0416d77`; see [the Phase 3 report](reports/PHASE3_REPORT.md).

### Phase 4 — published

Commit `3a3e9f5`; published before Phase 5 implementation was approved.

- Compare 2–12 selected papers across methodology, datasets, results, conclusions
  and limitations, with an optional focus/category subset.
- Retrieve each paper/category independently: eight BM25 and eight dense
  candidates, existing RRF, up to two retained passages per category and a 16,000
  character per-paper passage budget. A dominant paper cannot consume others' budgets.
- Preview passages locally before explicit comparison-sharing consent.
- Generate one structured evidence card per uncached paper using the existing
  isolated signed-in Codex gateway and real LangChain prompt/runnable composition.
- Validate card identities, versions, exact category coverage and category-specific
  canonical source IDs. Missing categories explicitly describe gaps in retrieved
  passages; failed requests are not mislabeled as missing paper content.
- Extract reported experimental task/dataset/split/metric/value/settings where
  supported. Unknown fields stay unknown; no automatic protocol equivalence assumed.
- A second LangChain chain selects validated entries for every paper/category table
  cell and generates cited agreements/disagreements or comparison limits. Table
  facts are rendered from validated card entries; citations resolve to original PDFs.
- A relationship needs category evidence from each named paper. Result agreements/
  disagreements require complete matching reported task, dataset, split, metric
  and settings. The UI exposes matching/not-directly-comparable assessments.
- Persist validated cards in an additive SQLite table. Keys include paper version,
  focus/categories, model, card-prompt version, settings and source IDs. Cache reads
  revalidate against current evidence; invalid entries regenerate. Retention is
  bounded to 16 cards per paper. Paper deletion cascades to its cards.
- Card/synthesis requests have at most two attempts total (initial plus one retry
  or repair). Authentication/model/isolation failures stop further generation.
  Successful cards remain cached, so manual retries avoid regenerating them.
- Failed card coverage withholds synthesis. A malformed/unsupported synthesis is
  withheld while validated cards remain inspectable. Source changes during an
  active request invalidate the preview/result.
- Comparison focus/category/selection/corpus changes clear session comparison data
  and reset consent. Final comparisons remain session-only.
- Added an explicit synthetic comparison/cache verification CLI. No new dependency
  versions, model, authentication method, vector store or infrastructure were added.

**Final results: 234 tests passed, no failures/errors/skips, in 19.79 seconds at the publication recheck.**
This includes all 181 existing Phase 1/2/3 tests and 53 new Phase 4 cases. All three
actual MiniLM tests ran from cached public weights with HF Hub networking disabled.
The live comparison check passed using signed-in `gpt-6.1-sol`: two generated papers,
five categories, ten table cells, original citations, an agreement, a disagreement,
a missing limitation and reuse of both validated cards. Four generation requests
were made. Dependency consistency, package/CLI checks and local HTTP smoke passed.
See [the Phase 4 report](reports/PHASE4_REPORT.md).

## Pending phases

| Phase | Approved roadmap scope | Status |
| --- | --- | --- |
| 6 | Labeled dataset, three-mode retrieval evaluation, claim faithfulness/hallucination review, optional Ragas and final demo/guide | Pending |

The approved [architecture reference](docs/ARCHITECTURE.md) and diagram remain
unchanged. Phase 5 extends existing lifecycle behavior; quality evaluation remains Phase 6.

## Important components

| Files | Responsibility |
| --- | --- |
| `src/ingestion/`, `src/embeddings.py` | Original parsing/chunking/embedding baseline; Phase 5 extends lifecycle/index recovery |
| `src/retrieval/comparison.py` | Separate paper/category budgets and immutable evidence snapshot containers |
| `src/generation/comparison.py` | Card generation, validated-cache reuse, bounded retries and synthesis |
| `src/generation/comparison_validation.py` | Canonical card/table/relationship provenance and condition matching |
| `src/generation/prompts.py` | New versioned card/synthesis prompts; existing answer prompt preserved |
| `src/persistence.py` | Existing catalog plus paper version and foreign-key-linked bounded card cache |
| `src/config.py`, `src/schemas.py` | Comparison limits, cards, cells, relationships and result contracts |
| `src/ui/comparison.py`, `src/ui/documents.py`, `src/ui/chat.py` | Comparison preview/consent/table/source flow integrated with existing library/chat |
| `src/phase4_verification.py` | Explicit synthetic isolation/comparison/cache check and installed CLI |
| `tests/`, `reports/PHASE4_REPORT.md` | Regressions, new coverage, actual MiniLM and live verification evidence |

## Technical decisions and dependencies

- Preserve Python, Streamlit, LangChain, LlamaIndex, ChromaDB, Sentence Transformers,
  BM25 and RRF. LlamaIndex still owns ingestion/indexing; LangChain composes
  retrieval/generation. There is one canonical corpus and one vector store.
- Reuse existing MiniLM revision, ingestion fingerprint, SDK `0.163.0` and
  `gpt-6.1-sol` authentication/isolation boundary. SDK code and its restrictions
  were not changed for Phase 4. No fallback provider or API key is used.
- Reuse the dependency set in `requirements-phase2.lock`. Only the local package
  was refreshed for the new `rag-verify-comparison` entry point.
- Canonical chunk IDs are also card source IDs, so cache entries remain independent
  of paper display ordering. Human-friendly C1/C2 labels are created in the UI only.
- Table synthesis selects validated card entry indices. Every factual displayed
  entry retains links to original passages; cards are not treated as original sources.
- The additive `comparison_cards` table preserves existing catalogs/indexes. Only
  card summaries/metadata/IDs are cached; canonical passages remain in the catalog.
- Each comparison preserves every selected paper/category or withholds synthesis
  after a failure. Context is bounded; oversized requests ask for a narrower scope
  instead of silently dropping a paper or truncating evidence.
- Keep each phase separate; publication and the next phase require explicit approval.

## Known issues and limitations

- Five upstream PyMuPDF/SWIG deprecation warnings remain; no tests are failing.
- PDF extraction remains heuristic; OCR/scans, figure interpretation, equations
  and complex tables remain unsupported. No new parsing service was introduced.
- Citation validation establishes traceability, not semantic support for every
  generated claim. Faithfulness/hallucination and retrieval metrics remain Phase 6.
- Condition matching is deliberately conservative and uses normalized strings;
  synonymous protocols may be labeled not directly comparable. Matching labels
  do not prove scientific equivalence or a fair performance comparison.
- The synthesis input has a 180,000-character cap. Very large comparisons may need
  fewer categories/papers. Model usage grows with uncached papers and retries;
  cached cards still need a new synthesis request.
- Comparison/chat results are session-only. Card caching persists. Phase 5 repairs
  derived indexes, but cannot reconstruct lost canonical data or reliably detect
  arbitrary semantically wrong vectors that still have valid shape and norm.
  Joblib snapshots remain trusted local data and must never be imported from others.
- Live tests used generated evidence only. Broad real-paper/adversarial benchmarks
  and full manual browser upload transport were not tested. AppTest covered the
  actual library/chat/comparison flows and the HTTP server was checked separately.
- SDK runtime and HTTP checks need OS execution permission in the desktop sandbox.
  The explicit canary verifier uses `/bin/cat`; macOS was tested, other OSes were not.
  Account entitlement and quotas can change; failed isolation disables generation.
- `.gitignore` excludes private documents, credentials, runtime/index/model data and
  raw reports; it cannot identify arbitrary secrets pasted into source.

## Phase 5 — completed, reviewed and approved for publication

- Startup and an explicit sidebar recovery action audit SQLite integrity and foreign
  keys, safe paper IDs/states, canonical page/chunk metadata and identities, PDF
  existence/hash, Chroma documents/metadata/vector shape/norm and BM25 statistics.
- Interrupted processing/deletion finishes idempotently. Derived orphan vectors and
  abandoned application-owned hash-named PDFs are removed. Unmanaged filenames stay
  untouched. A failed operation blocks search/generation until recovery succeeds.
- Missing/changed PDFs or inconsistent canonical rows mark only the affected paper
  unavailable. Saved records remain local and excluded from retrieval; the UI gives
  restore/delete guidance. Exact restored sources can become ready again. Explicit
  deletion works even when the paper's metadata JSON cannot parse. Unavailable papers
  count toward the twelve-paper cap; their identical PDF can replace its own record.
- Repair only missing/damaged vectors with existing LlamaIndex and local MiniLM.
  Healthy startup never parses/rechunks/re-embeds; valid cards for unaffected sources
  survive. Rebuilt BM25 uses canonical text, verifies stored statistics and never
  loads an untrusted external snapshot. Old BM25 signatures rebuild once locally.
- Add a `paper_issues` table and opaque recovery revision in existing SQLite metadata.
  Revision changes invalidate stale previews even when paper/chunk IDs remain stable.
  No ingestion fingerprint, embedding space or additional vector store is introduced.
- Preserve structured error codes through the official SDK's public turn stream.
  The pinned SDK's `run()` otherwise flattens failed turns to raw RuntimeError text.
  Map verified error shapes to safe sign-in/quota/rate/context/network guidance;
  unknown errors retain generic safe messages. Account/request limits halt comparison
  calls without an immediate retry; transient comparison retries remain bounded.
- Keep exact model/authentication/isolation/timeout/cancellation and tracing controls.
  Logs contain fixed event/error codes and recovery counts, never filenames, paths,
  document passages, questions, tokens, raw SDK exceptions or notification payloads.
- Shared source buttons navigate chat/comparison citations to the correct saved PDF
  page's original/cleaned text. Recovery, deletion and stale-evidence failures clear
  chat/comparison state and reset consent before widgets render on the next run.
  Explicit recovery failures also remove previously visible source panels.

**Validation: 298 tests passed, no failures/errors/skips, in 21.52 seconds at the November 7 publication recheck.**
All 234 original Phase 1–4 tests passed unchanged, plus 64 new Phase 5 tests.
All four actual MiniLM integrations ran with cached public weights and HF Hub
networking disabled. New integration coverage includes abrupt subprocess exit
mid-deletion, repeated restarts and actual MiniLM vector repair/hybrid search.
Dependency/package/CLI and HTTP checks passed. See [the Phase 5 report](reports/PHASE5_REPORT.md)
for the separate live access/generation evidence and complete limitations.

| Files | Phase 5 responsibility |
| --- | --- |
| `src/ingestion/recovery.py` | New canonical audit, unavailable states and idempotent consistency repair |
| `src/ingestion/pipeline.py`, `indexing.py` | Availability gate, safe lifecycle cleanup and targeted LlamaIndex vector repair |
| `src/persistence.py`, `src/retrieval/bm25.py` | Issue metadata/recovery revision and stronger snapshot validation |
| `src/retrieval/hybrid.py`, generation validators | Prevent retrieval/generation while recovery is incomplete |
| `src/generation/runtime.py`, `llm.py`, `comparison.py` | Public SDK stream adapter, sanitized errors and bounded request policy |
| `src/ui/maintenance.py`, `sources.py` | New recovery controls, unavailable-paper guidance, navigation and invalidation |
| Existing document/chat/comparison UI | Integrate recovery and source inspection with the existing user flow |
| Four new recovery/runtime test modules | Fault injection, durability, MiniLM, safe failures and Streamlit tests |

## Phase 5 decisions and limits

No third-party dependencies, model/provider/authentication, SDK versions, pipeline
fingerprints or architecture components changed. Only the local package was refreshed.
The verified route remains `gpt-6.1-sol`, official `openai-codex==0.163.0` and this
account's ChatGPT-managed Codex sign-in. This is measured runtime support, not an
assumption that a subscription supplies OpenAI API credits. Local repair has CPU/disk
costs; hosted inference consumes Codex allowance, with no automatic credit purchase.

Physical SQLite/Chroma corruption can require a backup. Canonical records are never
silently invented or a whole database reset. The audit is a consistency check, not
proof of source truth or semantic vector correctness. Recovery checks read local PDFs
and vector batches, so startup has extra disk I/O. Storage changes made outside the
application after startup require explicit recovery or restart. The app remains local
and single-user. Managed sign-in/quotas can change; unsupported access fails closed.

## Phase 6 preparation — not implemented

The approved final phase covers the labeled dataset, fair BM25/vector/hybrid
retrieval evaluation, claim-level faithfulness/hallucination review, optional Ragas
and the final setup/demo guide. It preserves the existing local architecture.
No Phase 6 modules, datasets, endpoints, dependencies or evaluation runs have
been created by this publication update.

1. Freeze a six-paper corpus and source-preserving chunk configuration. Manually
   label 30 questions: 12 single-paper, eight comparisons, five unanswerable and
   five misleading/conflict cases; reserve ten for development and twenty held out.
   Store selected paper IDs, expected points, answerability, PDF pages/passages,
   relevant canonical chunk IDs and label rationale. Human review is required;
   model-generated labels are not automatically ground truth. Detect deleted or
   re-chunked sources and refuse stale labels. Report recall against labeled evidence
   when the relevant set is incomplete.
2. Implement `src/evaluation/dataset.py`, `retrieval_metrics.py` and `runner.py` to
   reuse the canonical catalog and existing retrievers with `bm25`, `vector` and
   `hybrid` modes. Reconstruct complete ranked IDs for K=5/10 from sparse/dense/RRF
   outputs, and assess the bounded context actually sent to the LLM separately.
   Keep paper selection, candidates, context budgets, prompts/model and corpus
   fixed across modes. Extend the existing comparison retriever's mode parameter
   only as needed for the same paper/category balancing; retain hybrid defaults.
3. Add `src/evaluation/faithfulness.py` for human claim/support review, structural
   citation validity versus actual passage support, hallucination rate, answer
   relevance and correct/false abstention. Include paper coverage, retrieval and
   generation/end-to-end latency. Empty factual output is not automatically perfect
   faithfulness. Cache valid generated artifacts with corpus/model/prompt identities
   and report failures, retries, regressions and denominator exclusions explicitly.
4. Prepare the public-safe dataset description/template in `eval/README.md` and
   reviewed public labels in `eval/questions.jsonl`; private labels/passages belong
   under ignored `data/evaluation/`. Keep raw artifacts in ignored `eval/results/`.
   Publish only reviewed summaries and public/licensed examples. Add a final demo
   and reproducible setup/run guide; never invent an improvement percentage.
5. Optionally add `src/evaluation/ragas_runner.py` after checking a pinned Ragas
   version and an explicit compatible Codex judge adapter. Do not assume that the
   current LangChain runnable is automatically accepted by Ragas. Use local embeddings
   where supported; remain with custom metrics/human review if compatibility fails.
   No alternate provider, API key or paid judge is authorized. Model judging is
   opt-in, usage-budgeted, cached and compared with human review.
6. Add deterministic metric/schema/stale-label/aggregation tests, three-mode real
   index integration tests and existing regression checks. Automated generation
   tests use mocks; clearly separate any permissioned live evaluation subset and
   record its request usage. Use synthetic fixtures for CI and include all actual
   MiniLM tests plus HTTP/UI checks when UI behavior changes.

### Integration, endpoints and security

Proposed evaluation modules call `HybridRetriever.retrieve`, `ResearchAssistant.search`
and `ResearchAssistant.answer`, plus the balanced comparison service and canonical
citation validators. LlamaIndex/PyMuPDF ingestion and Chroma/BM25 indexes are reused;
there is no duplicate corpus, new vector store, FastAPI service or React frontend.
No new REST endpoints are needed. A local runner/CLI calls Python services and the
existing official Codex SDK gateway. The local Streamlit interface remains unchanged
unless a small evaluation display is approved within this scope.

Core evaluation can use existing pinned Python libraries, custom calculations and
standard-library serialization/timing. Ragas is an optional dependency only after
compatibility/cost checks. Existing exact `gpt-6.1-sol`, `openai-codex==0.163.0` and
ChatGPT-managed sign-in are retained; November 7 live RAG/injection/citation and
insufficient-evidence checks passed. Future inference depends on this account's
allowance and must be checked before a larger run. Subscription access is not
assumed to supply direct OpenAI API credits, and nothing is purchased automatically.

Keep upload extension/content checks, size/page/capacity limits, hash-based filenames,
source selection/consent, isolated generation and disabled tracing. Treat PDF and
label text as untrusted data. Do not import external Joblib snapshots, log questions/
passages or publish raw results containing private evidence. Recheck exports and
Git exclusions before publication. Current uploads remain local; public hosting,
authentication systems, OCR and infrastructure changes remain outside this phase.

## Next steps and stop point

1. Publish only the reviewed Phase 5 changes after the final checks pass.
2. Obtain explicit approval before beginning Phase 6.

Approved Phase 5 commit message:
`feat: add phase 5 library recovery and resilient source workflows`

**Stop after the authorized Phase 5 publication; do not implement Phase 6 without approval.**
