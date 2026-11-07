# Phase 5 implementation report

Implemented: November 6, 2026. Publication recheck: November 7, 2026. Scope: restart/deletion recovery, graceful service/storage
failures and source/UI refinement. Phase 4 is published at `3a3e9f5`. Phase 5 is
implemented, tested and reviewed. The user approved commit and push on November 7,
2026; this report accompanies that publication. Phase 6 has not started.

## Delivered behavior

The existing single-process local application remains Python/Streamlit, LlamaIndex
for ingestion/indexing, Sentence Transformers MiniLM, Chroma, BM25/RRF, SQLite and
LangChain orchestration. No dependency versions, fingerprints, embedding spaces,
providers, authentication settings or infrastructure changed.

`PaperLibrary.recover()` runs at startup and through an explicit sidebar control
under the same library lock as ingestion/deletion. It checks SQLite integrity and
foreign keys, safe identifiers/states, canonical page/chunk coverage/identity/text,
original PDF size/hash, active Chroma documents/metadata/vector shape/finiteness/norm
and BM25 snapshot contents/statistics. Healthy reopening never parses/rechunks or
embeds existing papers; the audit adds local disk I/O.

Interrupted processing/deletion finishes idempotently. Orphan vector records and
abandoned hash-named PDFs in the application-owned papers folder are removed;
unmanaged filenames remain untouched. Missing/damaged vectors are repaired using
canonical chunks through LlamaIndex and the original local model. Deletion uses canonical chunk IDs as well as paper metadata, so damaged vector
paper labels cannot leave target records behind. The pinned store
uses Chroma `add()`, so only affected entries are removed and recreated. If repair
is interrupted, canonical records remain and the next check can repeat it. BM25
rebuilds from canonical text. Stronger signatures cause a one-time BM25 rebuild
on upgrade, without re-embedding healthy papers.

Canonical inconsistencies or missing/changed PDFs mark the affected paper unavailable,
preserving its saved records and excluding it from active retrieval. The additive
`paper_issues` table stores a fixed reason code. Users can restore exact sources and
check again, or explicitly delete/re-upload. Deletion works even when metadata JSON
cannot parse. Unavailable papers count toward capacity; an identical original PDF
can replace its own unavailable record when its metadata is readable. Valid cards
for unaffected papers survive; cards for unavailable papers are invalidated.

An opaque recovery revision in existing SQLite metadata invalidates old evidence
snapshots even when canonical IDs stay unchanged. Failed mutation/recovery blocks
local retrieval and generation until recovery succeeds. No partial comparison is
silently generated. Existing canonical provenance checks and cached-card validation
continue to run.

## Generation and authentication verification

Generation remains exact `gpt-6.1-sol` through ChatGPT-managed Codex sign-in and
`openai-codex==0.163.0` with its pinned official runtime. The isolation adapter,
restricted permissions, endpoint checks, model checks, ephemeral requests, disabled
tracing, timeout/interrupt and cleanup are retained. No API key is introduced or
provider/model fallback enabled.

The SDK's public turn stream preserves typed errors that its `run()` convenience
collector otherwise flattens to raw `RuntimeError(message)`. The small runtime
adapter recognizes documented/generated error shapes for unauthorized access,
exhausted allowance, rate/context/session limits and connection failures. Unknown
errors remain generic. Quota/rate/request failures halt remaining comparison calls
without an immediate retry; transient comparison retries retain the two-attempt cap.
Application logging records fixed error/event codes and recovery counts, without
private paths, filenames, document content, questions, credentials, raw notifications
or exception text. No new log file or third-party telemetry service is added.

This was verified against installed SDK source/generated types and current official
[Python SDK documentation](https://learn.chatgpt.com/docs/codex-sdk),
[app-server errors](https://learn.chatgpt.com/docs/app-server) and
[authentication documentation](https://learn.chatgpt.com/docs/auth). Documentation
alone is not account entitlement. Two actual synthetic checks passed:

- Before the stream change: existing Phase 3 live verifier, report timestamp
  `2026-11-06T14:31:55Z`; signed-in model access, structured output, isolation,
  synthetic injection, canonical retrieval/citations and missing-evidence behavior.
- After the change: existing Phase 4 live verifier, report timestamp
  `2026-11-06T14:41:24Z`; exact model/authentication and SDK/runtime `0.163.0`, all six
  gates, two synthetic papers, five categories, ten cells, two canonical citations,
  agreement/disagreement, missing limitation and reuse of both cached cards.
  Four comparison generation calls were made.

The raw report `phase` fields identify the reused verifier (3 or 4), not a newly
implemented feature phase. Reports are stored as ignored `reports/phase5-*.json`.
Only generated synthetic passages were submitted. Credentials and user configuration
were not read/copied/changed by application code. Runtime access is account-specific
and can expire or change; it is not assumed from a subscription. Inference consumes
Codex allowance; no separate API credits, automatic purchases or guaranteed free
quota are assumed. Local recovery consumes disk/CPU and may need cached model weights.
The existing app-server route remains for this local project; commercial/hosted
access would require separate verification and approval.

## Source/UI refinements

Shared source-navigation buttons in chat previews, validated answer citations and
comparison citations select the correct paper and one-based PDF page in the library
inspector. The inspector shows original/cleaned extracted text, not rendered PDF
images. Navigation preserves the selected research scope and does not call a model.

The sidebar exposes recovery progress/results, unavailable-paper reasons and an
explicit confirmed deletion action. Startup failures offer a retry-opening action.
Recovery/deletion clear session answers, comparisons, previews and sharing consent.
Callbacks invalidate state before widgets render; stale-evidence errors trigger a
controlled rerun so previously rendered passages do not linger after failure.
SDK/account errors preserve local passages and cached cards for an explicit retry.

## Files created or modified

| File | Status | Responsibility |
| --- | --- | --- |
| `src/ingestion/recovery.py` | New | Canonical audit, source unavailability, idempotent cross-store repair |
| `src/ingestion/pipeline.py` | Modified | Startup/manual recovery, availability gate, safe lifecycle failure handling |
| `src/ingestion/indexing.py` | Modified | Batched vector audit and targeted LlamaIndex repair |
| `src/persistence.py` | Modified | Additive issue table, integrity checks, recovery revision and raw identity lookup |
| `src/retrieval/bm25.py` | Modified | Text-sensitive signatures and stored-statistics validation |
| `src/retrieval/hybrid.py` | Modified | Block retrieval until incomplete recovery is resolved |
| `src/generation/citations.py` | Modified | Block stale/incomplete-recovery evidence before generation |
| `src/generation/comparison_validation.py` | Modified | Apply recovery guard to all comparison evidence |
| `src/generation/runtime.py` | New | Public SDK stream collection and structured error classification |
| `src/generation/llm.py` | Modified | Safe runtime messages/logging using existing model/authentication route |
| `src/generation/comparison.py` | Modified | Stop on account/request limits; bounded network retry |
| `src/ui/sources.py` | New | Shared navigation, session invalidation and stale-source rerun |
| `src/ui/maintenance.py` | New | Explicit recovery and unavailable-paper actions |
| `src/ui/documents.py` | Modified | Integrate inspector navigation, recovery controls and safe state reset |
| `src/ui/chat.py` | Modified | Source navigation and immediate stale-evidence clearing |
| `src/ui/comparison.py` | Modified | Original-citation navigation and stale-evidence clearing |
| `tests/test_recovery.py` | New | Write/delete faults, corruption, repair, cache, capacity and generation guards |
| `tests/test_recovery_integration.py` | New | Subprocess interruption/restart and actual MiniLM repair |
| `tests/test_recovery_ui.py` | New | Recovery success/failure, source navigation and unavailable deletion |
| `tests/test_runtime_errors.py` | New | Pinned SDK error shapes, public stream, safe logging and account-limit behavior |
| `README.md` | Modified | Usage, recovery, tests, decisions, costs and limits |
| `PROJECT_PROGRESS.md` | Modified | Phase 5 completion and Phase 6 approval boundary |
| `docs/GIT_WORKFLOW.md` | Modified | Phase 5 review/publication gate |
| `reports/PHASE5_REPORT.md` | New | Curated implementation/test record |

Total: 9 new files and 15 modified files. Earlier tests, approved architecture/diagram,
PDF parsing/chunking/embedding baseline, isolation implementation, schemas/config,
prompt templates, dependency manifests/locks and `.gitignore` remain unchanged.
The local package was refreshed normally; no third-party packages were installed.

## Tests and validation

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q --tb=short --junitxml=reports/phase5-all-tests.xml
.venv/bin/python -m pip check
```

**298 passed, 0 failed, 0 errors, 0 skipped; 21.52 seconds at the November 7 publication recheck.**

| Group | Passed |
| --- | ---: |
| Unchanged Phase 1–4 tests | 234 |
| Recovery fault injection/consistency | 35 |
| Process durability and actual MiniLM recovery | 2 |
| Recovery/source Streamlit AppTest | 5 |
| Runtime stream/error/account-limit tests | 22 |
| **Total** | **298** |

All four actual MiniLM integrations used cached public weights with HF Hub networking
disabled. No pytest test calls an LLM; deterministic generation fixtures exercise
real local ingestion/indexing/retrieval and LangChain boundaries. The subprocess test
exits abruptly mid-deletion, then reopens twice without loading the embedding model.
Additional injection covers catalog/PDF/page/chunk/vector/ready/BM25 writes, deletion
steps, interrupted vector repair, corrupt derived statistics, missing/changed sources,
malformed metadata, invalid identifiers, orphan cleanup and card-cache preservation.

The local wheel build/install, `pip check` and all three installed CLI help commands
outside the checkout passed. The local Streamlit health and HTML endpoints returned
HTTP 200 using a temporary empty library; the server was stopped and temporary data
cleaned up. Source syntax, pins, doc links, whitespace, ignore rules, secret-pattern
scan and unstaged Git boundary are checked before handoff. Raw JSON/XML stay ignored.

## Issues found and fixed

- Chroma `add()` did not replace existing damaged vectors. Repair now removes only
  affected derived IDs before LlamaIndex recreates them, then rechecks consistency.
  The test's intentional document mutation also needed an explicit embedding because
  this collection deliberately has no default remote embedding function.
- Recovery actions rendered after chat could otherwise leave old source panels in
  the failed-action response. Pre-render invalidation callbacks and controlled stale
  source reruns now clear them; actual AppTest covers the failure path.
- Canonical chunk IDs are now used during deletion even if vector paper metadata
  is damaged; a dedicated regression verifies complete target removal.
- Catalog insertion and replacement cleanup now sit inside ingestion error handling;
  failed deletion/cleanup prevents the same cached library from serving stale state.
- SDK convenience collection discarded structured failure codes; public streaming
  preserves them without parsing raw messages or logging their content.

No test failure remains unresolved. Five existing PyMuPDF/SWIG deprecation warnings
remain. A pip cache-permission notice only disables pip's optional cache.

## Known limitations and stop point

Physical SQLite/Chroma corruption or lost canonical records may require a backup.
No automatic whole-database reset, invented source reconstruction or backup system
is introduced. A valid-shape/norm but semantically wrong embedding is not reliably
detectable by this audit. External changes after startup need explicit recovery or
restart. Joblib snapshots are trusted local serialization, never safe external input.

OCR/scans, complex tables/figures/equations, protocol semantic equivalence, broad
real-paper/adversarial benchmarks, manual browser upload transport and other OSes
retain their earlier limits. macOS was tested. Actual quota exhaustion/credential
revocation/disk filling were not triggered; safe deterministic failure injection was
used. Structural citation validity does not establish scientific faithfulness.
Retrieval-quality and hallucination evaluation remain Phase 6. Results remain
session-only; validated card caching remains local and durable.

Approved Phase 5 commit message:
`feat: add phase 5 library recovery and resilient source workflows`

**Stop after the authorized Phase 5 publication. Phase 6 still requires explicit approval.**

## November 7 publication verification

The full suite passed again: 298 tests, no failures/errors/skips, all 234 original
Phase 1–4 tests unchanged and all four real MiniLM integrations enabled with HF Hub
networking disabled. Pytest uses deterministic/mocked generation and makes no LLM
request. Source review confirms that canonical retrieved `Document.page_content`
and validated metadata are serialized into LangChain prompt passages before the
SDK gateway runs; citations resolve back to those same original chunks.

The separate live command was:

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m src.phase3_verification --live --report reports/phase5-publication-live.json
```

It passed with timestamp `2026-11-07T11:34:21Z`, authentication `chatgpt`, exact
`gpt-6.1-sol` and official SDK/runtime `0.163.0`. It verified effective configuration,
restricted permissions, allowed/denied synthetic filesystem canaries, ignored embedded
instructions, no tool activity, structured model response, real local retrieval and
one canonical PDF-page citation. The grounded answer included the retrieved study's
91.2-percent result. The question about unreported carbon emissions returned
`insufficient_evidence` with no factual claims. No private document or credentials
were supplied. This is a successful live inference test through Codex, distinct
from the mocked automated tests; it consumes account allowance.

Dependency consistency, three installed CLI entry points outside the checkout,
source syntax, pins, documentation links, whitespace, sensitive-pattern/trackable
file scan and private/generated ignore checks passed. The actual local Streamlit
health/HTML endpoints returned HTTP 200 with a temporary empty library. No critical
issue or failing test was found. Five upstream SWIG warnings remain; manual browser
upload transport and broad scientific evaluation remain unexecuted. Existing SDK,
model, provider and authentication were not changed for publication.

The fetched `origin/main` matched the local Phase 4 baseline before commit. Only the
24 Phase 5 source/test/doc files are included; raw JSON/XML, PDFs, credentials, local
catalog/vector stores and model weights remain excluded. The exact staged diff is
reviewed before committing. Phase 6 preparation is documentation only; no Phase 6
modules, datasets, dependencies, API endpoints or evaluation features were created.
