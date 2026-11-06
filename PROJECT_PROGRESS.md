# Project progress

Last updated: November 6, 2026.

## Current phase

**Phase 4 — paper-balanced evidence cards and cited research comparisons.**
Implementation and validation are complete. The user reviewed and approved Phase 4
for commit and push on November 6, 2026. Publication follows the checks documented
in the Phase 4 report. Phase 5 requires separate explicit approval and has not started.

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

### Phase 4 — completed, reviewed and approved for publication

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
| 5 | UI/source refinement, comprehensive corruption/recovery and failure handling | Awaiting explicit approval; not started |
| 6 | Labeled dataset, three-mode retrieval evaluation, claim faithfulness/hallucination review, optional Ragas and final demo/guide | Pending |

The approved [architecture reference](docs/ARCHITECTURE.md) and diagram remain
unchanged. Basic cache consistency belongs to Phase 4; comprehensive recovery and
quality evaluation were not implemented early.

## Important components

| Files | Responsibility |
| --- | --- |
| `src/ingestion/`, `src/embeddings.py` | Existing LlamaIndex/PyMuPDF/local embedding pipeline, unchanged |
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
- Comparison/chat results are session-only. Card caching persists; comprehensive
  corruption/recovery belongs to Phase 5. Joblib snapshots remain trusted local data.
- Live tests used generated evidence only. Broad real-paper/adversarial benchmarks
  and full manual browser upload transport were not tested. AppTest covered the
  actual library/chat/comparison flows and the HTTP server was checked separately.
- SDK runtime and HTTP checks need OS execution permission in the desktop sandbox.
  The explicit canary verifier uses `/bin/cat`; macOS was tested, other OSes were not.
  Account entitlement and quotas can change; failed isolation disables generation.
- `.gitignore` excludes private documents, credentials, runtime/index/model data and
  raw reports; it cannot identify arbitrary secrets pasted into source.

## Phase 5 preparation — not implemented

The approved roadmap assigns Phase 5 restart/deletion recovery, authentication and
quota errors, source inspection and UI refinement. It extends the existing local
application; retrieval evaluation, hallucination scoring and optional Ragas stay in
Phase 6. No new model, provider, embedding space or infrastructure is planned.

1. Audit cross-store failure points and define repeatable, idempotent recovery for
   interrupted ingestion/deletion. Extend `src/ingestion/pipeline.py`,
   `src/persistence.py`, `src/ingestion/indexing.py` and `src/retrieval/bm25.py`.
   Reuse canonical SQLite records to check Chroma/BM25 consistency. Preserve
   unaffected ready papers and validated cards. Corrupt canonical records or
   unavailable original PDFs need a safe diagnostic; do not silently delete the
   library, mix fingerprints or claim that lost data can always be restored.
2. Improve actionable missing/expired sign-in, quota, timeout, network, busy-library
   and disk/storage messages through `src/generation/llm.py`,
   `src/generation/isolation.py`, `src/generation/comparison.py` and UI boundaries,
   only where required. Keep isolation checks, bounded retries, successful card
   reuse and local retrieval available. Never substitute model/authentication or
   automatically purchase usage. SDK error classification must be verified against
   the pinned runtime before changing mappings.
3. Refine existing `src/ui/documents.py`, `src/ui/chat.py` and
   `src/ui/comparison.py`: clearer paper/page/passage inspection, processing/failure
   state and recovery guidance. Clear stale sources, answers, comparisons and
   consent after deletion/recovery. Keep one Streamlit app and existing services.
4. Extend existing lifecycle, gateway, isolation, chat, comparison and AppTest
   suites; add focused recovery integration tests. Inject failures around each
   cross-store step, restart repeatedly, verify complete deletion from PDFs,
   canonical rows, Chroma, BM25 and card caches, test stale/corrupt derived indexes,
   and check missing credentials/quota/timeouts without real account changes.
   Rerun the full regression suite, all actual MiniLM tests, local HTTP smoke and
   an explicitly authorized synthetic live check if the gateway changes.
5. Update README/progress and a Phase 5 report with recovery behavior, test evidence
   and remaining limitations; stop for review before commit/push.

Dependencies remain the existing pinned packages and local disk/CPU. Live tests
consume Codex allowance; deterministic failure tests do not. The Phase 4 publication
check re-verifies exact `gpt-6.1-sol`, ChatGPT-managed authentication, official Python
SDK/runtime `0.163.0`, programmatic structured inference and evidence isolation.
Support is account/runtime-specific and must be rechecked if access or versions change.

## Next steps and stop point

1. Publish only the reviewed Phase 4 changes after the final checks pass.
2. Obtain explicit approval before beginning Phase 5.

Approved Phase 4 commit message:
`feat: add phase 4 cited research paper comparisons`

**Stop after the authorized Phase 4 publication; do not implement Phase 5 without approval.**
