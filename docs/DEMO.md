# Local setup and demonstration

## Environment

Use the tested Python 3.12 environment or create Python 3.11+ with the existing
`requirements-phase2.lock`. No evaluation dependency or provider change is needed.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-phase2.lock
.venv/bin/python -m pip install --no-deps .
.venv/bin/python -m pip check
```

For the existing environment, only refresh the local package after source edits.
Use a normal install; editable installation has a known macOS path issue in this
environment. The verification/evaluation CLI entry points then match the source.
Do not commit environment files, caches, PDFs, indexes or credentials.

## Demonstrate the assistant

```bash
.venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

1. Upload two or more selectable-text research PDFs. Inspect extraction warnings
   and original/cleaned text. The first local MiniLM download needs internet; later
   healthy restarts reuse saved vectors without loading the embedding model.
2. Select papers, ask a concrete dataset/method question and inspect local retrieved
   passages before sharing anything. No Codex account is needed for local search.
3. For generation, sign in using `codex login`; verify with
   `.venv/bin/python -m src.verification`. Enable the explicit sharing checkbox and
   generate a cited answer through `gpt-6.1-sol`. Inspect source filename/page/passage.
4. Ask about an unreported measurement. Show an insufficient-evidence response;
   do not assert general hallucination elimination from that example.
5. Compare selected papers across desired categories. Preview per-paper evidence,
   permit excerpts, then inspect table entries, missing categories, agreements,
   experimental comparability and original citation pages. Repeat to show card reuse.
6. Restart to show persistent sources/indexes. Use sidebar recovery after a local
   storage problem; unavailable sources are preserved with explicit restore/delete
   guidance. Confirm deletion and show removal from active search/comparison.

Only permitted excerpts go to Codex. Subscription/account allowance is not direct
OpenAI API credit. Missing access or failed isolation stops generation, preserving
local retrieval; no fallback provider or model is selected.

## Demonstrate evaluation

Follow [the evaluation guide](../eval/README.md) to download the six versioned public
papers, bind the 30 draft definitions into a dedicated library and run all three
retrieval methods. The default evaluation is local and makes no LLM request.

Show separate raw ranking metrics at K=5/10 and retained-context/paper coverage,
plus dev/heldout/task strata and timings. Identify the labels as draft until a
person completes the relevance review. Show the actual comparison even when
hybrid loses to a baseline; do not tune or invent a favorable percentage.

Generation evaluation is optional, explicit and capped. A pending human review
sheet demonstrates how atomic claim support, citation support and answer relevance
will be assessed. Without completed human review, semantic scores remain null.

For a live plumbing check using generated fixtures only:

```bash
HF_HUB_OFFLINE=1 .venv/bin/python -m src.phase6_verification --live --report reports/phase6-demo-live.json
```

This can consume up to six application model calls, including repairs, and checks
all three modes, source citations, missing evidence and zero-call answer-cache reuse.
Do not run it merely to show local retrieval or when allowance is unavailable.

## Verification and stop boundary

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q
.venv/bin/python -m pip check
git status --short
```

All actual MiniLM tests need cached public weights or first-download internet.
Pytest generation uses mocks. Keep model-usage tests visibly separate from the
scientific benchmark and from deterministic unit tests. Review the phase report,
private/generated exclusions and exact diff before any approved publication.
The user approved publication of Phase 6 tooling separately. Human benchmark
validation remains pending; publishing the tooling does not certify its draft labels
or generated claims. The roadmap defines no automatic later phase.
