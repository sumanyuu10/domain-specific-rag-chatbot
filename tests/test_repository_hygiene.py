"""Exercise publish/ignore boundaries without creating private documents."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def ignore_repo(tmp_path_factory):
    directory = tmp_path_factory.mktemp("git-hygiene")
    git = shutil.which("git")
    if not git:
        pytest.fail("Git is required to validate the repository's ignore rules.")
    subprocess.run([git, "init", "-q", str(directory)], check=True, capture_output=True)
    shutil.copyfile(ROOT / ".gitignore", directory / ".gitignore")
    return git, directory


def is_ignored(repository, path):
    git, directory = repository
    result = subprocess.run(
        [git, "-c", "core.excludesFile=/dev/null", "-C", str(directory),
         "check-ignore", "--no-index", "--stdin"],
        input=path + "\n", text=True, capture_output=True,
    )
    assert result.returncode in (0, 1), result.stderr
    return result.returncode == 0


@pytest.mark.parametrize("path", [
    ".env", ".env.local", ".env.production", ".env.test",
    ".streamlit/secrets.toml", "config/secrets.toml", "auth.json",
    "credentials.json", ".codex/auth.json", "service-account-dev.json",
    "keys/client.key", "keys/client.pem", ".venv/bin/python",
    "__pycache__/config.pyc", ".pytest_cache/v/cache/nodeids",
    ".runtime/request/logs/runtime.log", "build/lib/src/config.py",
    "dist/project.whl", "data/papers/paper.pdf", "uploads/paper.pdf",
    "documents/private.txt", "papers/research.PDF", "private/notes.txt",
    "models/model.onnx", "chroma_db/index.bin", "vector_store/part.bin",
    "cache/chunks.joblib", "local/catalog.sqlite3", "local/catalog.sqlite3-wal",
    "reports/phase1-verification.json", "reports/phase1-tests.xml",
    "eval/results/results.csv", "backup.zip",
])
def test_private_and_generated_paths_are_ignored(ignore_repo, path):
    assert is_ignored(ignore_repo, path), f"Private/generated path would be publishable: {path}"


@pytest.mark.parametrize("path", [
    ".env.example", "src/config.py", "src/generation/llm.py", "src/verification.py",
    "tests/test_repository_hygiene.py", "pyproject.toml", "requirements-phase1.lock",
    "README.md", "PROJECT_PROGRESS.md", "docs/ARCHITECTURE.md",
    "docs/assets/architecture.png", "reports/PHASE1_REPORT.md", "eval/questions.jsonl",
])
def test_intended_source_and_documentation_remain_publishable(ignore_repo, path):
    assert not is_ignored(ignore_repo, path), f"Intended project file would be hidden: {path}"
