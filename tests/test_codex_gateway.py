"""Offline contract/failure tests. These never start Codex or consume quota."""
import asyncio
import json
from pathlib import Path
import re
import subprocess
import sys
from types import SimpleNamespace as NS

from openai_codex import ApprovalMode, Sandbox
import pytest

from src.config import MODEL, Settings
from src.generation.llm import CodexGateway, CodexIntegrationError, runtime_config
from src.verification import verify


class FakeTurn:
    def __init__(self, owner, prompt):
        self.owner = owner
        self.prompt = prompt
        self.interrupted = False

    async def run(self):
        await asyncio.sleep(self.owner.delay)
        text = self.owner.answer
        if callable(text):
            text = text(self.prompt)
        return NS(
            status=self.owner.status, final_response=text,
            items=[NS(root=NS(type=kind)) for kind in self.owner.item_types],
            duration_ms=10,
        )

    async def interrupt(self):
        self.interrupted = True


class FakeThread:
    def __init__(self, owner):
        self.owner = owner

    async def read(self):
        return NS(thread=NS(model=self.owner.effective_model, model_provider="openai"))

    async def turn(self, prompt, **kwargs):
        self.owner.turn_options = kwargs
        self.owner.turn = FakeTurn(self.owner, prompt)
        return self.owner.turn


class FakeClient:
    def __init__(self, config, **options):
        self.config = config
        self.account_type = options.get("account_type", "chatgpt")
        self.catalog_model = options.get("catalog_model", MODEL)
        self.effective_model = options.get("effective_model", MODEL)
        self.answer = options.get("answer", "hello")
        self.status = options.get("status", "completed")
        self.item_types = options.get("item_types", ["userMessage", "agentMessage"])
        self.delay = options.get("delay", 0)
        self.start_error = options.get("start_error")
        self.closed = False
        self.thread_options = None
        self.turn = None
        self.metadata = NS(userAgent="Codex test runtime")

    async def __aenter__(self):
        if self.start_error:
            raise self.start_error
        return self

    async def close(self):
        self.closed = True

    async def account(self, **kwargs):
        return NS(account=None if self.account_type is None else NS(type=self.account_type))

    async def models(self, **kwargs):
        return NS(data=[NS(model=self.catalog_model)])

    async def thread_start(self, **kwargs):
        self.thread_options = kwargs
        return FakeThread(self)


def make_gateway(tmp_path, *, timeout=1, **options):
    clients = []

    def factory(config):
        client = FakeClient(config, **options)
        clients.append(client)
        return client

    return CodexGateway(Settings(runtime_dir=tmp_path, timeout_seconds=timeout), client_factory=factory), clients


def test_only_authorized_model_is_accepted():
    with pytest.raises(ValueError, match="fallback"):
        Settings(model="another-model")


@pytest.mark.parametrize("timeout", [0, -1, float("inf"), float("nan")])
def test_invalid_timeout_is_rejected(timeout):
    with pytest.raises(ValueError, match="positive"):
        Settings(timeout_seconds=timeout)


def test_environment_timeout(monkeypatch):
    monkeypatch.setenv("RAG_CODEX_TIMEOUT_SECONDS", "15")
    assert Settings.from_environment().timeout_seconds == 15


def test_runtime_configuration_shadows_keys_without_changing_parent(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "fake-parent-key")
    config = runtime_config(Settings(), tmp_path)
    assert config.env["OPENAI_API_KEY"] == ""
    assert config.env["CODEX_API_KEY"] == ""
    assert config.env["LANGSMITH_TRACING"] == "false"
    assert 'forced_login_method="chatgpt"' in config.config_overrides
    assert 'web_search="disabled"' in config.config_overrides
    assert 'features.shell_tool=false' in config.config_overrides
    assert config.codex_bin is None  # Official SDK's pinned runtime, not a substituted CLI.
    import os
    assert os.environ["OPENAI_API_KEY"] == "fake-parent-key"


def test_preflight_makes_no_generation_request_and_cleans_up(tmp_path):
    gateway, clients = make_gateway(tmp_path)
    access = asyncio.run(gateway.preflight())
    assert access.authentication == "chatgpt"
    assert access.model == MODEL
    assert clients[0].thread_options is None
    assert clients[0].closed
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("mode", [None, "apiKey", "chatgptAuthTokens", "amazonBedrock"])
def test_wrong_or_missing_auth_fails_before_generation(tmp_path, mode):
    gateway, clients = make_gateway(tmp_path, account_type=mode)
    with pytest.raises(CodexIntegrationError) as captured:
        asyncio.run(gateway.generate("hello"))
    assert captured.value.code == "authentication_required"
    assert clients[0].thread_options is None
    assert clients[0].closed


def test_missing_model_never_uses_default(tmp_path):
    gateway, clients = make_gateway(tmp_path, catalog_model="another-model")
    with pytest.raises(CodexIntegrationError) as captured:
        asyncio.run(gateway.generate("hello"))
    assert captured.value.code == "model_not_listed"
    assert clients[0].thread_options is None


def test_runtime_model_mismatch_blocks_turn(tmp_path):
    gateway, clients = make_gateway(tmp_path, effective_model="another-model")
    with pytest.raises(CodexIntegrationError) as captured:
        asyncio.run(gateway.generate("hello"))
    assert captured.value.code == "model_mismatch"
    assert clients[0].turn is None


def test_success_uses_explicit_model_ephemeral_read_only_thread(tmp_path):
    gateway, clients = make_gateway(tmp_path)
    result = asyncio.run(gateway.generate("hello", output_schema={"type": "object"}))
    client = clients[0]
    assert result.text == "hello"
    assert result.model == MODEL
    assert client.thread_options["ephemeral"] is True
    assert client.thread_options["sandbox"] == Sandbox.read_only
    assert client.thread_options["approval_mode"] == ApprovalMode.deny_all
    assert client.thread_options["model"] == MODEL
    assert client.turn_options["model"] == MODEL
    assert client.turn_options["output_schema"] == {"type": "object"}
    assert client.closed


@pytest.mark.parametrize("kind", ["commandExecution", "webSearch", "mcpToolCall", "unknown"])
def test_unexpected_activity_discards_answer(tmp_path, kind):
    gateway, _ = make_gateway(tmp_path, item_types=["agentMessage", kind])
    with pytest.raises(CodexIntegrationError) as captured:
        asyncio.run(gateway.generate("hello"))
    assert captured.value.code == "unexpected_activity"


@pytest.mark.parametrize("answer", [None, "", "   "])
def test_empty_answer_is_not_success(tmp_path, answer):
    gateway, _ = make_gateway(tmp_path, answer=answer)
    with pytest.raises(CodexIntegrationError) as captured:
        asyncio.run(gateway.generate("hello"))
    assert captured.value.code == "empty_answer"


def test_incomplete_turn_is_not_success(tmp_path):
    gateway, _ = make_gateway(tmp_path, status="interrupted")
    with pytest.raises(CodexIntegrationError) as captured:
        asyncio.run(gateway.generate("hello"))
    assert captured.value.code == "incomplete_turn"


def test_timeout_interrupts_turn_and_closes_runtime(tmp_path):
    gateway, clients = make_gateway(tmp_path, timeout=0.03, delay=1)
    with pytest.raises(CodexIntegrationError) as captured:
        asyncio.run(gateway.generate("hello"))
    assert captured.value.code == "timeout"
    assert clients[0].turn.interrupted
    assert clients[0].closed


def test_explicit_cancellation_interrupts_and_closes(tmp_path):
    gateway, clients = make_gateway(tmp_path, delay=1)

    async def cancel():
        task = asyncio.create_task(gateway.generate("hello"))
        while not clients or clients[0].turn is None:
            await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    assert clients[0].turn.interrupted
    assert clients[0].closed


def test_sdk_startup_error_is_safe_and_closes_client(tmp_path):
    gateway, clients = make_gateway(tmp_path, start_error=RuntimeError("fake-secret-detail"))
    with pytest.raises(CodexIntegrationError) as captured:
        asyncio.run(gateway.preflight())
    assert captured.value.code == "sdk_failure"
    assert "fake-secret-detail" not in str(captured.value)
    assert clients[0].closed


def test_langchain_sync_adapter(tmp_path):
    gateway, clients = make_gateway(tmp_path)
    result = gateway.as_runnable().invoke("hello")
    assert result.model == MODEL
    assert clients[0].turn.prompt == "hello"


def test_invalid_prompt_never_starts_sdk(tmp_path):
    gateway, clients = make_gateway(tmp_path)
    with pytest.raises(ValueError):
        asyncio.run(gateway.generate(" "))
    assert clients == []


def test_live_verifier_checks_dynamic_nonce_and_structured_output(tmp_path):
    def response(prompt):
        nonce = re.search(r"Nonce: ([0-9a-f]+)", prompt).group(1)
        return json.dumps({"answer": "Cobalt", "source_ids": ["S1"], "nonce": nonce})

    gateway, clients = make_gateway(tmp_path, answer=response)
    report = asyncio.run(verify(gateway, live=True))
    assert report["status"] == "passed"
    assert report["checks"]["langchain_round_trip"]
    assert len(clients) == 2


def test_verifier_does_not_accept_wrong_evidence(tmp_path):
    gateway, _ = make_gateway(tmp_path, answer='{"answer":"wrong","source_ids":["S9"],"nonce":"wrong"}')
    report = asyncio.run(verify(gateway, live=True))
    assert report["status"] == "failed"
    assert report["error"]["code"] == "verification_mismatch"


def test_verifier_does_not_accept_malformed_json(tmp_path):
    gateway, _ = make_gateway(tmp_path, answer="not JSON")
    report = asyncio.run(verify(gateway, live=True))
    assert report["status"] == "failed"
    assert report["error"]["code"] == "invalid_output"


def test_installed_cli_imports_outside_project_directory(tmp_path):
    command = Path(sys.executable).parent / "rag-verify-codex"
    result = subprocess.run([str(command), "--help"], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert "--live" in result.stdout
