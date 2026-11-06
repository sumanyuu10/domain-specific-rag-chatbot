"""Safe verifier failures and the installed comparison CLI, without model use."""
from pathlib import Path
import subprocess
import sys

from src import phase4_verification


def test_failed_isolation_never_starts_a_comparison(monkeypatch):
    monkeypatch.setattr(phase4_verification, "verify_isolation", lambda **kwargs: {
        "status": "failed", "error": {"code": "isolation_unverified", "message": "Blocked"},
    })
    def forbidden(*args): raise AssertionError("No comparison may start after isolation fails")
    monkeypatch.setattr(phase4_verification, "verify_comparison", forbidden)
    result = phase4_verification.verify(live=True)
    assert result["status"] == "failed" and result["error"]["code"] == "isolation_unverified"


def test_installed_comparison_cli_help_outside_repository(tmp_path):
    cli = Path(sys.executable).parent / "rag-verify-comparison"
    result = subprocess.run([str(cli), "--help"], cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "--live" in result.stdout and "--report" in result.stdout
