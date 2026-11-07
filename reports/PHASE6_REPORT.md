# Phase 6 implementation and evaluation report

Date: November 7, 2026. Approved scope: the recorded evaluation phase, retained
explicitly by the user after the backend/API scope mismatch was identified.
The user selected six public AI/CS papers. Phase 5 is published at `d253da8`.

**Evaluation tooling and automated testing are completed; scientific benchmark
acceptance remains open pending human relevance/claim review.** The user reviewed
and approved commit/push on November 7, 2026. This report accompanies publication
of the tools, not validation of the scientific benchmark. No later phase was implemented.

## Delivered components and integration

The existing Python/Streamlit application, LlamaIndex ingestion, PyMuPDF extraction,
local MiniLM embeddings, persistent Chroma/BM25 indexes, RRF and LangChain generation
remain intact. No third-party package/model/provider/authentication change was made.
The local package adds `rag-evaluate` and `rag-verify-evaluation` entry points.

- `dataset.py`: strict draft/reviewed/synthetic contracts, exact corpus/pipeline/
  paper versions, selected-paper/category labels and canonical page/content hashes.
  Stale/deleted/re-chunked sources are rejected rather than scored against old labels.
- `retrieval_metrics.py`: deterministic Precision/Recall/MRR at K=5/10, retained
  context quality, relevant-paper coverage and count/mean/median/range summaries.
- `runner.py`: identical settings across BM25/vector/hybrid, ordinary questions and
  balanced comparisons, raw rankings versus actual selected context, per-question
  aggregation plus split/kind/task strata, warm-up and per-stage timing.
- `artifacts.py`: exclusive local writes, accidental-edit digests, cached output
  revalidation against original chunks, card/table/relationship/citation contracts.
  Keys cover corpus, prompt inputs/content/version, model, SDK, output schemas,
  mode and budgets. Human label/review edits alone do not regenerate unchanged
  prompts. Cache timing is separated from fresh inference timing.
- `faithfulness.py`: pending human atomic-claim/citation review tied to an exact
  run, support/hallucination ratios, relevance judgments, review coverage, structural
  citations and operationally separate abstention checks. No automatic semantic
  score is fabricated from citation validity, empty answers or lexical similarity.
- `benchmark.py`/`cli.py`: checked versioned public PDFs, draft page-anchor binding,
  local preparation/freezing/inspection, three-mode runs and human review commands.
  Default evaluation makes no LLM request; output/report paths are never overwritten.
- Existing comparison retrieval/service/validator: explicit optional mode selection
  preserves paper/category budgets. Hybrid defaults and Phase 4/5 card-cache keys
  are preserved; sparse/vector card entries are separately identified.
- `phase6_verification.py`: explicit isolated generated-fixture live test across
  three modes, canonical citations, insufficient evidence and zero-call cache reuse.

Inference requires `--generate --allow-remote` and an explicit request cap (default
zero). The meter includes application retries/repair and records budget exclusions.
It does not measure token cost or runtime/provider internal retry usage. Access/
quota/model/isolation failures halt further uncached generation; local retrieval
metrics remain available. Existing exact `gpt-6.1-sol`, SDK/runtime `0.163.0`,
ChatGPT-managed Codex sign-in, restrictions and disabled tracing are unchanged.
Subscription allowance is not treated as direct API credits; nothing is purchased.

## Public corpus and draft labels

The six PDFs were downloaded from versioned primary sources into ignored local
storage. Their hashes/URLs are in `eval/papers.json`; PDFs are not redistributed.

| Paper | Versioned source |
| --- | --- |
| Attention Is All You Need | [1706.03762v7](https://arxiv.org/abs/1706.03762v7) |
| BERT | [1810.04805v2](https://arxiv.org/abs/1810.04805v2) |
| RoBERTa | [1907.11692v1](https://arxiv.org/abs/1907.11692v1) |
| Dense Passage Retrieval | [2004.04906v3](https://arxiv.org/abs/2004.04906v3) |
| Retrieval-Augmented Generation | [2005.11401v4](https://arxiv.org/abs/2005.11401v4) |
| LoRA | [2106.09685v2](https://arxiv.org/abs/2106.09685v2) |

The dedicated library contains **6 PDFs, 102 pages and 559 canonical chunks**.
`eval/questions.jsonl` supplies 30 source-level draft definitions: 12 single-paper,
eight comparison, five unanswerable and five misleading cases; ten development
and twenty held-out. Preparation proposes chunk labels using known PDF pages and
lexical terms. A person must inspect pooled passages from all three methods, add
missed relevant evidence, correct false matches and verify absence claims. Proposed
labels and expected points are not human ground truth. No reviewer identity or
review timestamp was invented.

The frozen dataset is local/ignored; changing review metadata alone does not
invalidate a still-valid model response cache. A changed corpus or chunk identity
does require explicit label revalidation/rebinding. The split is retained in all
reports, but draft exploratory inspection is not a blinded scientific benchmark.

## Measured exploratory retrieval run

The following commands ran successfully using cached public MiniLM weights and no
hosted inference:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.evaluation.cli --data-dir data/evaluation/public-six/library prepare-public --pdf-dir data/evaluation/public-six/pdfs --output data/evaluation/public-six/dataset.json
HF_HUB_OFFLINE=1 .venv/bin/python -m src.evaluation.cli --data-dir data/evaluation/public-six/library run --dataset data/evaluation/public-six/dataset.json --allow-draft --output eval/results/public-six-retrieval-v2.json
```

**90 cases completed, zero failures, zero LLM calls.** The raw report is ignored.
Run ID: `cc18e9df59fd4832954bd3788aa2b2c6`. All rows are labeled **draft**.

| Method | Labeled P@10 | Labeled R@10 | MRR@10 | Retained-context recall | Relevant-paper coverage | Mean retrieval ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| bm25 | 0.0600 | 0.6000 | 0.2437 | 0.4400 | 0.4400 | 4.67 |
| vector | 0.0220 | 0.2200 | 0.0439 | 0.1600 | 0.1600 | 10.47 |
| hybrid | 0.0480 | 0.4800 | 0.1436 | 0.2000 | 0.2000 | 10.40 |

These are actual exploratory measurements, not validated scientific accuracy.
Twenty-five answerable questions contribute rank metrics; five empty-gold
unanswerable questions are excluded with null values. Comparison paper/category
units are averaged within each question before the question macro average. Precision
uses K even if fewer results exist. Recall refers only to the pooled labeled set;
unlabeled relevant passages can also depress measured precision. Draft lexical
anchors can favor BM25 and do not exhaust all relevant evidence. Scores at K=5,
retained-context precision, per-question outcomes, strata, exclusions, median/range
and warm-up cost remain in the private raw artifact.

**Hybrid did not exceed BM25 in these aggregate draft-label results.** No improvement
percentage, statistical significance, semantic faithfulness or hallucination-free
claim is made. The public papers were not sent for answer generation in this run.

## Tests and live verification

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q --tb=short --junitxml=reports/phase6-all-tests.xml
```

**350 passed, 0 failed, 0 errors, 0 skipped; 23.66 seconds at the publication recheck.** All 298 original
Phase 1–5 tests passed unchanged, plus 52 Phase 6 tests. All five actual MiniLM
integrations ran offline from cached public weights. No pytest test invokes an LLM.

| Test group | Passed |
| --- | ---: |
| Existing Phase 1–5 regressions | 298 |
| `test_evaluation_cli` | 5 |
| `test_evaluation_dataset` | 12 |
| `test_evaluation_integration` | 3 |
| `test_evaluation_metrics` | 11 |
| `test_evaluation_review` | 8 |
| `test_evaluation_runner` | 10 |
| `test_phase6_verification` | 3 |
| **Total** | **350** |

Coverage includes metric edge cases/denominators, invalid/stale labels, canonical
cache reuse/corruption, mode budgets and comparison coverage, opt-in generation,
retry accounting, access failure stops, corpus changes mid-generation, pending/
partial human review, foreign/missing/duplicate judgments, safe CLI output and
interruption, existing-report preservation and actual MiniLM three-mode retrieval.

Separate explicit live command:

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m src.phase6_verification --live --report reports/phase6-live.json
```

**Passed**, timestamp `2026-11-07T12:05:26Z`: account authentication `chatgpt`, exact
`gpt-6.1-sol`, official Python SDK/runtime `0.163.0`, existing configuration and
filesystem isolation gate. Two generated questions × three modes produced six
cases with six application model calls: supported answers with original citations
and correct insufficient-evidence statuses. Repeating all six cases reused
validated answers with **zero additional calls**. No public benchmark PDF or
private document was sent. Semantic scores remain unclaimed without human review.
Later changes only refined cache identities/report-path protection and were covered
by regression tests; live access was not repeatedly consumed for documentation edits.

Normal local wheel/package refresh and dependency consistency passed. The actual
Streamlit health/HTML routes returned HTTP 200 with a temporary empty library;
AppTest regression coverage remained. All installed CLI help commands are checked
outside the checkout. Source syntax, dependency pins, links, whitespace, private/
generated exclusions, secret-pattern scan and unchanged Git staging/HEAD are checked
before handoff. Five upstream PyMuPDF/SWIG warnings remain; no failing test is unresolved.

## Ragas, privacy and limitations

Ragas is optional and remains disabled/not installed. Current
[LLM factory documentation](https://docs.ragas.io/en/latest/references/llms/) describes
a compatible structured client/adapter boundary. It does not establish compatibility
with this signed-in Codex runnable. The [metrics documentation](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/)
describes judge-based faithfulness/relevance alongside other metrics. Adding a judge
would require a verified pinned adapter and usage/privacy checks; no default paid
API or model/authentication substitute is introduced. The implemented baseline is
custom deterministic metrics plus explicit human review.

Human review templates begin pending. Reviewers split parent text into atomic facts,
confirm decomposition coverage and assess each citation. Faithfulness and unsupported
claim rate use supported+unsupported assessed facts as denominator; uncertain/pending
and incomplete parent coverage are visible. No factual claims yields null scores.
Human answer relevance is a custom 1/0.5/0 rating, not a Ragas metric. Operational
failures/budget exclusions are not counted as abstentions. Structural citation
validity applies to accepted outputs only; invalid-output counts remain separate.

Private datasets, original PDFs, generated answers/citations, caches, human sheets
and raw runs stay in ignored data/results. Public definitions contain bibliographic
metadata, proposed questions and paraphrased expected points, not copied PDFs.
Inspection prints passage text only with explicit `--show-passages`. Application
logs/normal CLI output contain counts, aggregates and fixed codes, not questions,
credentials, raw SDK details or stack traces. Existing upload/isolation/consent and
trusted-local Joblib boundaries remain; no new network endpoint is introduced.
Local artifact hashes detect accidental edits, not malicious local tampering.

Remaining acceptance work: human relevance/absence review, reviewed frozen labels,
optional capped real-answer evaluation and actual human claim/citation judgments.
No final scientific quality score is claimed before that work. OCR/figures/complex
tables, protocol semantic equivalence, broader adversarial benchmarking, manual
browser upload transport and other OSes retain their existing limits.

## Issues found and corrected

- Dedicated benchmark preparation initially looked for weights in its empty local
  model cache and retried blocked network requests. It was interrupted, then the
  CLI reused the existing configured cache and prepared all papers offline. Existing
  recovery handled the interrupted import. No model/provider was changed.
- An oversized synthetic single-page PDF fixture overflowed its text box, producing
  empty extraction. The fixture now uses multiple fitting pages; no parser workaround
  or extraction behavior change was made.
- Hybrid card-cache keys retain their Phase 4/5 identity. Other retrieval modes are
  separated, and label-review-only changes do not force model regeneration.
- Verification/report writes now reject existing paths before runtime work; CLI
  interruption/cleanup errors are sanitized. This prevents overwrites or raw tracebacks.

## File inventory and stop point

Modified: `pyproject.toml`, `src/retrieval/comparison.py`,
`src/generation/comparison.py`, `src/generation/comparison_validation.py`,
`README.md`, `PROJECT_PROGRESS.md`, `docs/GIT_WORKFLOW.md`.

Created: `src/evaluation/__init__.py`, `dataset.py`, `retrieval_metrics.py`,
`runner.py`, `artifacts.py`, `faithfulness.py`, `benchmark.py`, `cli.py`;
`src/phase6_verification.py`; `eval/papers.json`, `eval/questions.jsonl`,
`eval/README.md`; `docs/DEMO.md`; `reports/PHASE6_REPORT.md`;
`tests/evaluation_helpers.py`, `test_evaluation_metrics.py`,
`test_evaluation_dataset.py`, `test_evaluation_runner.py`, `test_evaluation_review.py`,
`test_evaluation_cli.py`, `test_evaluation_integration.py`, `test_phase6_verification.py`.

There are **22 new and 7 modified files**. Baseline ingestion/chunking/embeddings,
UI, generation gateway/isolation/prompts, dependency locks and approved architecture/
diagram remain unchanged. No phase after the recorded Phase 6 was implemented.

Approved Phase 6 commit message:
`feat: add phase 6 reproducible RAG evaluation and review workflow`

**Stop after the authorized publication. Scientific human validation remains
pending, and no later phase may begin without explicit scope approval.**

## Final publication verification

The user approved commit/push of the completed evaluation tools, using the exact
message above. Publication recheck: **350 tests passed, no failures/errors/skips,
23.66 seconds**, including all 298 original regressions and five real MiniLM tests.
No pytest test used a live model. Source/dependency/CLI and secret-pattern/ignore
checks passed; all five installed CLI entrypoints worked outside the checkout.

The 90-case local retrieval evaluation was rerun to ignored
`eval/results/phase6-publication-retrieval.json`: no failures and zero model calls.
Its draft-label Precision/Recall/MRR@10 values match the historical run in the table
exactly. Hybrid still did not outperform BM25 under these draft labels. Labels were
not promoted to reviewed, no reviewer/time was invented, and semantic scores remain
unset. The prior six-call synthetic live check remains explicitly historical; it
was not rerun for this documentation-only publication review.

The fetched `origin/main` matched the Phase 5 baseline before publication. Only the
29 Phase 6 source/test/public-definition/documentation files are included. Local
PDFs, canonical frozen labels, vector stores, caches, generated claims/review sheets
and raw JSON/XML remain ignored. The approved Streamlit architecture and diagram,
model, authentication, dependency versions and prior test files are unchanged.

The actual roadmap ends at Phase 6; no Phase 7 is defined. Human relevance-label,
absence, claim/citation-support and answer-relevance validation are outstanding
Phase 6 acceptance tasks. The objectives, existing modules, prerequisites,
deliverables and regression strategy are recorded in `PROJECT_PROGRESS.md`.
No acceptance review or later implementation was performed by this publication.
