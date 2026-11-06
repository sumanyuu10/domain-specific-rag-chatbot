"""Verifier error handling and CLI packaging, without a live runtime."""
from types import SimpleNamespace as NS
import subprocess
import sys

from src.config import Settings
from src import phase3_verification


def test_verifier_never_leaks_raw_sdk_or_config_errors(tmp_path, monkeypatch):
    async def broken(*args):
        raise RuntimeError("private endpoint credential must not appear")
    monkeypatch.setattr(phase3_verification, "verify_worker", broken)
    result = phase3_verification.verify(gateway=NS(settings=Settings(runtime_dir=tmp_path)))
    assert result["status"] == "failed"
    assert "private endpoint" not in str(result)
    assert not list(tmp_path.iterdir())


def test_installed_phase3_cli_help_works_outside_repository(tmp_path):
    from pathlib import Path
    cli = Path(sys.executable).parent / "rag-verify-rag"
    result = subprocess.run([str(cli), "--help"], cwd=tmp_path, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "--live" in result.stdout and "--report" in result.stdout
