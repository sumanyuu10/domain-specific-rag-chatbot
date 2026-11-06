# Phase 4 implementation report

Date: November 6, 2026. Scope: approved paper-balanced evidence retrieval, validated
cards, comparison synthesis/tables and card caching. Phase 3 remains published at
`0416d77`. The user reviewed Phase 4 and approved commit/push on November 6, 2026.
This report accompanies that publication; Phase 5 has not started.

## Delivered behavior and component boundaries

Users select 2–12 saved research papers, an optional focus and categories. Local
retrieval runs independently for each paper/category, using eight sparse and eight
dense candidates, existing RRF and up to two passages per category. Per-paper
passage characters are bounded to 16,000. No paper can consume another's budget.
The existing PyMuPDF/LlamaIndex/MiniLM ingestion and stored vectors are reused.

`src/retrieval/comparison.py` carries canonical evidence snapshots and actual
LangChain Documents for each paper/category. `src/generation/comparison.py` uses
LangChain prompts/runnables and the existing EvidenceGateway. Model/authentication,
SDK isolation, timeout/cancellation and tracing controls remain the approved route.
Generation requires comparison-specific consent after a local preview.

One structured card request per uncached paper extracts supported entries and gaps.
Every requested category must occur once, and entries must cite chunks actually
retrieved for that paper/category. Identity/version/content checks reuse canonical
records. Missing categories refer to retrieved evidence, not claims about the
whole paper; failed requests are separately reported.

A second chain selects validated card entries for every table cell and produces
cited relationships. The application materializes cell facts from those entries,
so synthesis cannot invent independent table values or omit selected papers.
Agreement/disagreement relationships need category citations from each named paper.
Result relationships require matching complete reported task/dataset/split/metric/
settings. Pairwise assessments explicitly flag absent/mismatching conditions.
All source panels resolve to original PDF names, positions and passages.

Validated cards persist in the existing SQLite catalog via an additive table.
Keys include paper version, focus/categories, model, card-prompt version, settings
and retrieved source IDs. Reads are revalidated; invalid cached cards regenerate.
Deletion cascades by foreign key, unaffected cards survive, and retention is capped
at 16 cards per paper. Final comparisons are not persisted. Focus/category/selection/
corpus changes reset the UI comparison and consent; source changes during generation
withhold the result immediately.

Every card/synthesis request has at most two attempts total: first request and one
transient retry or validation repair. Auth/model/isolation failures halt remaining
requests. Failed cards withhold synthesis; successful cards are reused by Retry
failed comparison requests. Invalid synthesis is withheld while valid cards and
sources remain inspectable. No provider substitution or unbounded retry is used.

## Files created or modified

| Files | Purpose/change |
| --- | --- |
| `src/retrieval/comparison.py` | New per-paper/category retrieval and evidence snapshots |
| `src/generation/comparison.py` | New card/cache/synthesis service and bounded request handling |
| `src/generation/comparison_validation.py` | New provenance, grid coverage and experimental-condition validation |
| `src/ui/comparison.py` | New local preview, consent, table, relationship, comparability and source panels |
| `src/phase4_verification.py` | New explicit synthetic comparison/cache verification CLI |
| `src/config.py`, `src/schemas.py` | Add comparison settings and typed contracts; earlier settings preserved |
| `src/persistence.py` | Add paper versions, bounded validated-card storage and FK deletion |
| `src/generation/prompts.py` | Add versioned card/synthesis prompts; existing answer prompt unchanged |
| `src/ui/documents.py`, `src/ui/chat.py` | Connect comparison panel and update selection/help text |
| `pyproject.toml` | Add `rag-verify-comparison`; no dependency version changes |
| `tests/comparison_helpers.py` | Synthetic deterministic model-response helpers |
| `tests/test_balanced_retrieval.py`, `test_comparison.py` | Budgets, coverage, consent, retries, failures and canonical sources |
| `tests/test_comparison_cache.py`, `test_comparison_validation.py` | Persistence, invalidation, protocols and source constraints |
| `tests/test_comparison_ui.py`, `test_comparison_integration.py` | UI actions/invalidation and real MiniLM pipeline |
| `tests/test_phase4_verification.py` | CLI packaging and isolation-failure stop behavior |
| `README.md`, `PROJECT_PROGRESS.md`, `docs/GIT_WORKFLOW.md`, this report | Usage, current status, decisions, tests and approval boundary |

The SDK gateway/isolation implementation, ingestion modules, embedding implementation,
existing test files, historical dependency locks, approved architecture reference and
diagram are unchanged. Existing PDFs/vectors do not need rebuilding. Refresh the
local package normally for the added CLI and restart the application after updating.

## Test evidence

Final full-suite command:

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q --tb=short --junitxml=reports/phase4-all-tests.xml
```

**234 passed; 0 failed, 0 errors, 0 skipped; 19.79 seconds at the publication recheck.**

| Group | Passed |
| --- | ---: |
| All original Phase 1/2/3 tests | 181 |
| Balanced retrieval and 12-paper coverage | 12 |
| Comparison service/repair/failure handling | 12 |
| Card persistence/cache/invalidation | 6 |
| Synthesis/citation/protocol validation | 15 |
| Comparison Streamlit AppTest | 5 |
| Actual MiniLM comparison integration | 1 |
| Comparison verifier/CLI | 2 |
| **Total** | **234** |

The 12-paper test completed a 60-cell comparison through real local indexes with
13 deterministic model-response calls. That is functional coverage, not a hosted
performance benchmark. The three actual MiniLM tests used cached public weights
with HF Hub networking disabled. Pytest never invokes an LLM; the default command
skips those three embedding tests unless explicitly opted in.

Live check:

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m src.phase4_verification --live --report reports/phase4-live.json
```

**Passed** with `gpt-6.1-sol`, ChatGPT-managed Codex sign-in and official SDK/runtime
`0.163.0`. The existing isolation/file-canary check passed before comparison.
Two generated papers produced five categories, ten cells, two original-page
citations, a supported agreement and disagreement, a missing limitation and reuse
of both cached cards on the second comparison. Exactly four generation requests
were observed: two card calls and two synthesis calls. No private paper was submitted.
This checks the crafted synthetic cases, not general scientific correctness.

Normal local wheel build/install and installed CLI help passed. `pip check` found
no broken requirements. The actual local Streamlit server's health and HTML routes
returned HTTP 200. Source syntax, dependency pins, local doc links, private/generated
ignore rules and unchanged Git history/index are checked before handoff. Raw JSON/XML
reports stay local and ignored; this curated Markdown report is publishable.

## Issues found and corrected

- After a failed generation, the retry button initially retained its old label
  until another UI interaction. A controlled rerun now immediately reflects the
  failure/retry state; AppTest covers the complete retry and cache reuse action.
- A previous comparison could remain in session display if a source changed during
  a new request. Retrieval-error handling now clears the comparison preview/result;
  the regression test confirms the stale result is withheld.
- Card source IDs use canonical chunk IDs, preserving identity across paper ordering
  and cache reuse. Table source labels are created by the UI, never trusted from models.
- Five upstream PyMuPDF/SWIG deprecation warnings remain. No test failure is unresolved.

## Decisions, costs and limits

No new third-party package/model/provider was installed. The dependency set remains
`requirements-phase2.lock`; the local package adds a CLI entry point. LlamaIndex
continues ingestion/indexing; LangChain composes generation/retrieval; Chroma/BM25
share the existing corpus. SQLite stores the validated cache with no cloud service.

Ordinary uncached generation normally costs one request per paper plus one synthesis;
failed requests can each use one extra retry/repair. Cached cards avoid their calls,
but synthesis runs again. Very large comparison inputs can exceed the configured
180,000-character synthesis cap and ask for a narrower scope rather than dropping
papers or silently truncating evidence. Existing account entitlement/quotas apply.

Condition matching is conservative normalized-string matching, without automatic
unit conversion or semantic protocol equivalence. Matching reported labels is not
proof of a fair experiment. Structural citations are not a faithfulness score.
Phase 6 will evaluate retrieval/claim quality; no improvement or hallucination-free
claim is invented here. OCR, figures, complex tables and mathematical interpretation
retain their existing limits. Broad real-paper/adversarial benchmarks and manual
browser file-upload transport were not executed. AppTest/HTTP checks are separate.

Comparison results remain session-only; comprehensive corruption/recovery is Phase 5.
The desktop sandbox requires OS execution permission for the SDK/HTTP smoke test.
macOS was tested; other operating systems were not. No SDK/auth/user config was
changed, and no Phase 5 or evaluation feature was implemented.

Approved commit message:
`feat: add phase 4 cited research paper comparisons`

**Stop after the authorized Phase 4 publication. Phase 5 still requires explicit approval.**

## Publication recheck

All 234 tests passed again with all three real MiniLM integrations enabled and no
skips. The original 181 Phase 1/2/3 tests remain unchanged. Dependency consistency,
source syntax, dependency pins, local documentation links, secret-pattern/trackable
file scan, ignore exclusions and preserved earlier core components passed.
The fetched `origin/main` matched local Phase 3 HEAD before publication.

The first HTTP harness attempt resolved the virtual-environment interpreter symlink
to the system interpreter and exited before Streamlit started. Correcting the harness
to use `.venv/bin/python` directly passed both health and HTML HTTP 200. This required
no application change. No unresolved test failure remains. Five upstream SWIG
warnings remain. Broad real-paper evaluation/manual browser uploads remain unexecuted.

The live publication check passed again at `2026-11-06T14:25:06Z`: exact
`gpt-6.1-sol`, authentication `chatgpt`, official SDK/runtime `0.163.0`, all six
verification gates, ten cells, two canonical citations and both cached cards reused.
Four generation requests were observed. No private paper was submitted and no
SDK, model, account credentials or user configuration was changed.

Current [official Python SDK documentation](https://learn.chatgpt.com/docs/codex-sdk)
shows programmatic `gpt-6.1-sol` turns through the local app-server, subject to
signed-in account availability. The [authentication documentation](https://learn.chatgpt.com/docs/auth)
distinguishes subscription sign-in from API-key billing. Documentation and this
actual pinned-runtime check support reusing the existing gateway for Phase 5 error
handling; they do not guarantee future entitlement or quotas. The private low-level
SDK bridge used for isolation remains version-pinned and fails closed. Phase 5
preparation is recorded in `PROJECT_PROGRESS.md`; no Phase 5 implementation was added.
