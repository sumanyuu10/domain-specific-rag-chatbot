# Git workflow

The repository root is `domain_specific_rag`, not the surrounding chat output
directory. The local `main` branch is connected to `origin` at
`https://github.com/sumanyuu10/domain-specific-rag-chatbot.git`.
The user approved the initial Phase 1 commit and push. Do not publish the
surrounding `work/` directory or the entire chat's `outputs/` directory.

## First Phase 1 commit

These are the review and commit commands for the completed phase. The user has
authorized the initial publication; later phase commits still require approval.

```bash
cd /Users/sumanyu/Documents/Codex/2026-11-02/i-have-an-idea-for-a/outputs/domain_specific_rag
.venv/bin/python -m pytest -q
.venv/bin/python -m pip check
git status --short
git add .gitignore .env.example pyproject.toml requirements-phase1.lock README.md PROJECT_PROGRESS.md src tests docs reports/PHASE1_REPORT.md
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "feat: complete phase 1 environment and Codex verification"
```

Review the staged diff before executing the commit command. Configure your Git
author name/email if Git requests them; no global Git identity has been changed.

## Verify GitHub and push

The `origin` remote is already configured; do not add a duplicate remote. Check
the target before an approved push:

```bash
git remote -v
git push -u origin main
```

These initial-push commands assume an empty remote. If it already has commits,
inspect its history and reconcile it before pushing. Do not force-push to bypass
that check. If `origin` already exists, inspect it instead of adding another one.

Only the public repository URL is documented in project files; credentials must
never be stored here. GitHub authentication uses your normal Git tooling;
Codex sign-in is not Git authentication.

## Every later phase

1. Obtain approval to begin that phase.
2. Implement and test only its approved scope.
3. Update `PROJECT_PROGRESS.md`, README, and the curated phase report.
4. Check `git status`, exclusions, and the proposed diff for secrets/private data.
5. Present the results and suggest a phase-specific commit message.
6. Commit and push only after approval; get approval before starting the next phase.

## Phase 2 review and publication

Phase 2 is implemented, tested, and approved by the user for commit and push.
These commands document its publication workflow. Phase 3 and publication of
future phases each need their own explicit approval.

```bash
cd /Users/sumanyu/Documents/Codex/2026-11-02/i-have-an-idea-for-a/outputs/domain_specific_rag
git status --short
git diff --check
git diff
# Phase 2 publication was explicitly approved:
git add .env.example .streamlit/config.toml app.py pyproject.toml requirements-phase2.lock README.md PROJECT_PROGRESS.md src tests docs/GIT_WORKFLOW.md reports/PHASE2_REPORT.md
git diff --cached --check
git diff --cached --stat
git diff --cached
git commit -m "feat: add phase 2 PDF ingestion and persistent indexes"
git remote -v
git push origin main
```

Keep all PDFs, model weights, databases and raw test reports excluded. Do not use
`git add -f`. The unchanged `requirements-phase1.lock` is retained as history;
the current full dependency snapshot is `requirements-phase2.lock`. If Git needs
an author identity, configure an appropriate repository-local or command-scoped
identity; do not change global settings automatically.

## Phase 3 review boundary

Phase 3 implementation is complete and the user approved its commit and push on
November 6, 2026. Inspect the exact staged source/test/doc diff, exclusions and
current remote history before publication. That approval applies only to Phase 3;
Phase 4 publication and implementation of future phases need their own approval.

The full check includes both actual embedding tests:

```bash
HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q
.venv/bin/python -m pip check
git status --short
git diff --check
```

Approved Phase 3 commit message:
`feat: add phase 3 hybrid retrieval and cited research chat`.
See `reports/PHASE3_REPORT.md` for the file inventory, live synthetic verification
and limitations. Phase 4 publication requires separate explicit approval.

## Phase 4 review boundary

Phase 4 is implemented, tested and reviewed. The user approved commit and push on
November 6, 2026. Recheck tests, `reports/PHASE4_REPORT.md`, the exact source/test/doc
diff, exclusions and fetched remote history before staging only Phase 4 files.
Use a normal push; stop on failures, conflicts or unexpected remote changes.
Phase 5 implementation and publication were subsequently approved separately.

```bash
HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q
.venv/bin/python -m pip check
git status --short
git diff --check
```

Approved Phase 4 commit message:
`feat: add phase 4 cited research paper comparisons`.
Validated card caches reside inside the ignored SQLite catalog; raw Phase 4
verification reports remain ignored. Never stage those generated/private files.

## Phase 5 review boundary

Phase 5 is implemented, tested and reviewed. The user approved commit/push on
November 7, 2026. Recheck the source/test/doc diff, exclusions, full suite, live
synthetic RAG and fetched remote before staging only the relevant Phase 5 files.
Use a normal push and stop on test failures, authentication issues, conflicts or
unexpected remote changes. Phase 6 implementation and publication were subsequently approved separately.

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q
.venv/bin/python -m pip check
git status --short
git diff --check
```

Approved Phase 5 commit message:
`feat: add phase 5 library recovery and resilient source workflows`.
Local recovery modifies only the ignored library; never stage its PDFs, databases,
card caches, vector records or raw verification reports.

## Phase 6 review boundary

The user retained the original evaluation scope; no backend API was authorized.
Phase 6 implementation and automated testing are completed. The user reviewed
and approved commit/push on November 7, 2026. Draft relevance labels and unreviewed
generated claims remain pending human validation; publication approval is not
scientific acceptance. Review `reports/PHASE6_REPORT.md`, `eval/README.md`, the exact
staged diff/exclusions and fetched remote history before publishing only Phase 6
files. Use a normal push; stop on failures, authentication issues, conflicts or
unexpected remote changes.

```bash
HF_HUB_OFFLINE=1 HF_XET_CACHE="$PWD/data/models/xet" .venv/bin/python -m pytest --run-embedding-integration -q
.venv/bin/python -m pip check
git status --short
git diff --check
```

Approved Phase 6 commit message:
`feat: add phase 6 reproducible RAG evaluation and review workflow`.
Review public definitions/aggregates before staging. Keep PDFs, canonical labels,
model weights, review sheets, caches and raw evaluation artifacts excluded.
No later phase is automatically authorized.

## What stays local

`.gitignore` excludes environment variants, credentials, uploaded/private
documents, PDFs/Word files, databases and sidecars, vector/model files, caches,
build output, raw test/inference reports, and evaluation results. The empty
`.env.example`, source, tests, curated Markdown report, and approved architecture
remain publishable. Hygiene tests exercise those rules without creating private
files.

Git ignore rules do not detect secrets embedded in otherwise publishable files,
and do not remove anything already tracked. Never stage real tokens or account
credentials; always inspect the staged diff. Keep future synthetic fixtures
separate from private papers and review any needed ignore-rule exception explicitly.
