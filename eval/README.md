# Phase 6 evaluation

Run the module commands below from the repository root. Installed entrypoints
use installed-package defaults; export `RAG_DATA_DIR="$PWD/data"` to reuse the
checkout cache when using `rag-evaluate`, and select the corpus with `--data-dir`. Evaluation reuses the existing Python
services and local indexes; Streamlit remains the application interface. No REST
service, new provider or automatic judging service is introduced.

## Dataset and review status

`papers.json` identifies six versioned public arXiv papers and their downloaded
PDF SHA-256 values. PDFs remain under ignored local data; they are not redistributed
in this repository. Follow each source's license/terms before redistributing it.

`questions.jsonl` contains **draft source-level definitions**, not an executable
frozen dataset and not human ground truth. The mix is 12 single-paper questions,
eight comparisons, five unanswerable and five misleading cases; ten development
and twenty held-out. Proposed page/lexical anchors bind to canonical chunk IDs.
They can miss relevant passages and favor lexical matching. Do not report these
labels as reviewed accuracy or proof that a retrieval method is better.

Download the versioned URLs in `papers.json` into:

```text
data/evaluation/public-six/pdfs/
  transformer.pdf
  bert.pdf
  roberta.pdf
  dpr.pdf
  rag.pdf
  lora.pdf
```

Then prepare a separate six-paper library and frozen **draft** dataset:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.evaluation.cli --data-dir data/evaluation/public-six/library prepare-public --pdf-dir data/evaluation/public-six/pdfs --output data/evaluation/public-six/dataset.json
```

The PDFs and cached public MiniLM weights must already be present for offline use.
Without offline mode, first model use may download public weights. The CLI reuses
the normal configured model cache (`data/models` by default) even when `--data-dir`
selects a dedicated benchmark corpus. Existing paper bytes/hash/version are checked
before import; a library with other papers is rejected. Existing output files are
never overwritten. Choose a new output path for a new dataset/report.

## Retrieval-only evaluation

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.evaluation.cli --data-dir data/evaluation/public-six/library run --dataset data/evaluation/public-six/dataset.json --allow-draft --output eval/results/public-six-run.json
```

This executes 90 cases (30 questions × three modes) with **zero model requests**.
`--allow-draft` explicitly marks the result exploratory. Once labels have actually
been reviewed, omit that flag. `--split dev` or `--split heldout` evaluates a subset;
reports always retain split/kind/task strata. Do not tune on held-out results.

Each mode uses the same corpus, selected papers, budgets and prompts. QA defaults
to 20 candidates/method and eight context chunks; comparisons use eight candidates/
method and two retained passages per paper/category. Mode is the changed variable.
Raw rankings at K=5/10 are evaluated separately from the smaller context sent to
generation. Comparison scores first average eligible paper/category units per
question, then average questions so a many-category case does not dominate.

- Precision@K divides labeled hits by K, including missing positions as misses.
- Recall@K divides hits by the labeled relevant set. This is pooled-label recall,
  not exhaustive corpus recall. Unlabeled relevant passages may also depress
  measured precision. Duplicate result IDs earn no extra credit.
- Mean reciprocal rank is reported at K=5 and K=10, not as unbounded MRR.
- Questions/units with no relevant labels have null rank metrics and explicit
  denominators; unanswerable cases are evaluated by abstention when generated.
- Context precision/recall and required-paper coverage use only eligible labeled
  hits; merely retrieving some text from a paper does not earn evidence coverage.
- Local warm-up is recorded separately. Retrieval, fresh generation, cache reuse
  and total-case timings are distinguished; small samples do not justify strong
  tail-latency or significance claims.

The run artifact includes identities for dataset, corpus, model, SDK, prompt
contents/versions, schemas and retrieval settings; ranked/context IDs, failures,
request counts, aggregate and stratified scores. Its digest detects accidental
edits, not malicious local rewriting. Raw artifacts are private and ignored.

## Human relevance labeling

1. Inspect the selected PDF pages and the candidates pooled from all three modes.
   Add missed relevant chunks and remove false matches in the local frozen dataset.
   Review the whole selected paper before confirming an unanswerable label.
2. Obtain canonical IDs/hashes with:

```bash
.venv/bin/python -m src.evaluation.cli --data-dir data/evaluation/public-six/library inspect --paper PAPER_SHA256 --page 1
```

Add `--show-passages` only to explicitly print original passages locally. Do not
publish that terminal output for private documents. The Streamlit page inspector
can also inspect the same library using `RAG_DATA_DIR` pointing to it.

3. Review expected points, categories, required papers, the 10/20 split and label
   rationale. Record an actual reviewer and ISO review timestamp, and only then
   change the local dataset's `review_status` from `draft` to `reviewed`. No command
   automatically claims a person reviewed generated labels. Changes in source
   bytes/chunks/corpus are rejected until labels are revalidated and rebound.
4. For a custom corpus, author canonical `Question` records in local JSONL and use
   `freeze --questions ... --name ... --output ...`. This creates a draft, never
   automatically reviewed labels. Private definitions belong in ignored data.

## Optional answer generation

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.evaluation.cli --data-dir data/evaluation/public-six/library run --dataset data/evaluation/public-six/dataset.json --allow-draft --split dev --generate --allow-remote --max-model-requests 6 --output eval/results/generated-dev.json
```

This deliberately permits questions and retrieved excerpts to the existing
signed-in `gpt-6.1-sol` Codex gateway. Without `--generate`, no inference occurs;
without `--allow-remote`, generation is refused. Default request budget is zero.
The cap counts application calls including repair/retry; it is not a token budget
and cannot count provider/runtime internal retry usage. Comparisons can need one
request per uncached paper plus synthesis. Exhausted budget is recorded separately
from failed requests; retrieval scoring continues. Authentication/model/isolation/
quota failures halt further uncached generation. No paid credit purchase or provider
fallback occurs. Recheck account allowance before a larger run.

The existing card cache and an ignored evaluation-answer cache reuse valid results.
Keys include prompt inputs, model/SDK/schema identities, mode, corpus and selected
context. Reusing an answer revalidates canonical sources. Human annotation changes
alone do not spend model allowance to regenerate the same prompt. Failed outputs
are not cached as successful answers; cached latency is not fresh-model latency.

## Human claim-level review

```bash
.venv/bin/python -m src.evaluation.cli review-template --run eval/results/generated-dev.json --output eval/results/review-pending.json
# A person reviews and edits the sheet, then:
.venv/bin/python -m src.evaluation.cli review-score --run eval/results/generated-dev.json --review eval/results/review-completed.json --output eval/results/review-metrics.json
```

Templates begin pending, with no human reviewer. For every generated parent entry,
split multi-fact text into atomic claims, confirm complete coverage, and mark each
supported/unsupported/uncertain. Assess each original citation's passage support.
Use the local run's canonical citation passages and the frozen expected points.
Record an actual reviewer/date and a relevance judgment for every answer. Claims
and sources are linked to the exact hashed run; foreign/duplicate/missing entries
are rejected. A genuine reviewer must verify that their atomic decomposition is
complete; schema checks alone cannot prove that attestation.

Faithfulness = supported / (supported + unsupported). Hallucination rate uses the
same assessed denominator with unsupported in the numerator. Pending/uncertain and
unconfirmed parent entries have explicit coverage/exclusion counts. No factual
claims means a null faithfulness score, never automatic perfection. Partial human
review yields partial metrics with explicit coverage; it does not close benchmark acceptance. Citation support
correctness uses assessed claim/citation pairs. Human answer relevance uses a
custom 1/0.5/0 scale for relevant/partial/irrelevant, with pending excluded; it is
not a Ragas score. Operational errors and budget exclusions are not counted as
correct abstentions. Structural citation validity is reported for accepted outputs
and is separate from semantic support and validation-failure counts.

## Ragas decision

Ragas remains optional and **disabled/not installed**. Its current
[LLM factory](https://docs.ragas.io/en/latest/references/llms/) requires a compatible
structured-generation client/adapter; the project's Codex runnable is not verified
against that interface. [Available metrics](https://docs.ragas.io/en/latest/concepts/metrics/available_metrics/)
include model-judged faithfulness/relevance, which add model behavior, usage and
potential bias. No alternate judge, API-key billing or subscription-to-API assumption
is introduced. Custom deterministic metrics and human review are the implemented
baseline; a pinned compatible Ragas judge can be evaluated separately if approved.

## Privacy and limitations

Keep PDFs, canonical datasets, answer caches, review sheets and raw outputs under
ignored `data/` or `eval/results/`. Public source-level definitions and curated
aggregate reports are reviewed separately before publication. Logs/stdout normally
contain counts, fixed error codes and aggregates, not questions, passages, account
credentials or stack traces. Existing upload limits, canonical filenames, selected
source consent, isolation, tracing restrictions and trusted-local Joblib boundary
remain unchanged. Do not import untrusted serialized snapshots.

The current public labels are draft. No final scientific benchmark, human claim
score, hallucination elimination or statistically significant improvement is claimed.
The small synthetic live verifier tests plumbing and abstention only. Public hosting,
OCR, a REST backend and additional phases are outside the approved scope.
