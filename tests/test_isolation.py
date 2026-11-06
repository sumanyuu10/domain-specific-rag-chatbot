"""Fail-closed configuration/thread checks; no SDK process or model calls."""
import asyncio
from types import SimpleNamespace as NS
import tomllib

import pytest

from src.config import MODEL, Settings
from src.generation.isolation import (
    DISABLED_FEATURES, EvidenceGateway, RPCPayload, discovery_overrides,
    hardening_overrides, inspect, official_endpoint, validate_config,
)
from src.generation.llm import CodexIntegrationError, runtime_config


def secure_values(directory):
    return {
        "web_search": "disabled", "features": {name: False for name in DISABLED_FEATURES},
        "notify": [], "mcp_servers": {"test.server": {"enabled": False}},
        "skills": {"include_instructions": False}, "project_doc_max_bytes": 0,
        "developer_instructions": "", "model_instructions_file": str(directory / "answer-instructions.txt"),
        "default_permissions": "rag_answer", "permissions": {"rag_answer": {
            "filesystem": {":minimal": "read", str(directory): "read", "glob_scan_max_depth": None},
            "network": {"enabled": False},
        }}, "analytics": {"enabled": False},
        "otel": {"exporter": "none", "trace_exporter": "none", "metrics_exporter": "none"},
    }


def test_secure_effective_config_passes(tmp_path):
    validate_config(secure_values(tmp_path), [{"enabled": False}], tmp_path)


@pytest.mark.parametrize("endpoint,allowed", [
    (None, True), ("https://chatgpt.com/", True), ("https://chatgpt.com/backend-api/codex", True),
    ("https://chatgpt.com.evil.example", False), ("http://chatgpt.com", False),
    ("https://user:secret@chatgpt.com", False), ("https://chatgpt.com:8080", False),
])
def test_only_official_tls_service_endpoints_are_accepted(endpoint, allowed):
    assert official_endpoint(endpoint, "chatgpt.com") is allowed


@pytest.mark.parametrize("hazard", ["mcp", "skill", "hooks", "shell", "network", "extra_root", "profile", "instructions", "telemetry", "notify", "endpoint", "unknown_config"])
def test_unsafe_or_unverifiable_effective_config_blocks_generation(tmp_path, hazard):
    values, skills = secure_values(tmp_path), []
    if hazard == "mcp": values["mcp_servers"]["test.server"]["enabled"] = True
    if hazard == "skill": skills = [{"enabled": True}]
    if hazard == "hooks": values["features"]["hooks"] = True
    if hazard == "shell": values["features"]["shell_tool"] = True
    if hazard == "network": values["permissions"]["rag_answer"]["network"]["enabled"] = True
    if hazard == "extra_root": values["permissions"]["rag_answer"]["filesystem"]["/private-papers"] = "read"
    if hazard == "profile": values["default_permissions"] = ":read-only"
    if hazard == "instructions": values["developer_instructions"] = "inherited instruction"
    if hazard == "telemetry": values["otel"]["exporter"] = "otlp-http"
    if hazard == "notify": values["notify"] = ["some-command"]
    if hazard == "endpoint": values["openai_base_url"] = "https://unapproved.example"
    if hazard == "unknown_config": values = {}
    with pytest.raises(CodexIntegrationError) as captured:
        validate_config(values, skills, tmp_path)
    assert captured.value.code == "isolation_unverified"


def test_discovery_disables_literal_server_and_skill_names_without_replacing_auth():
    values = {"mcp_servers": {"test.server": {}, 'name"quote': {}}, "plugins": {"plugin@market": {}}}
    skills = [{"path": '/private/skills/with"quote/SKILL.md'}]
    overrides = discovery_overrides(values, skills)
    parsed = [tomllib.loads(value) for value in overrides]
    assert parsed[0]["mcp_servers"]["test.server"] == {"enabled": False, "required": False}
    assert parsed[0]["mcp_servers"]['name"quote']["enabled"] is False
    assert parsed[1]["plugins"]["plugin@market"]["enabled"] is False
    assert parsed[2]["skills"]["config"][0]["path"] == skills[0]["path"]
    assert not any("auth" in value or "token" in value for value in overrides)


def test_hardening_only_writes_own_instructions_in_temporary_directory(tmp_path):
    before = runtime_config(Settings(), tmp_path)
    overrides = hardening_overrides(tmp_path)
    assert list(tmp_path.iterdir()) == [tmp_path / "answer-instructions.txt"]
    assert 'features.hooks=false' in overrides and 'notify=[]' in overrides
    assert 'forced_login_method="chatgpt"' in before.config_overrides
    assert before.env["OPENAI_API_KEY"] == ""


class FakeRPC:
    def __init__(self, payload): self.payload = payload
    async def request(self, method, params, *, response_model):
        if method == "mcpServerStatus/list": return RPCPayload({"data": [], "nextCursor": None})
        return RPCPayload(self.payload)


def test_thread_permission_profile_and_instruction_sources_are_checked(tmp_path):
    payload = {
        "thread": {"id": "test"}, "model": MODEL, "modelProvider": "openai",
        "instructionSources": [], "approvalPolicy": "never",
        "sandbox": {"type": "readOnly", "networkAccess": False},
        "activePermissionProfile": {"id": "rag_answer"},
    }
    gateway = EvidenceGateway(Settings(runtime_dir=tmp_path))
    thread = asyncio.run(gateway._start_thread(NS(_client=FakeRPC(payload)), str(tmp_path)))
    assert thread.id == "test"
    for key, value in [("instructionSources", ["unrelated.md"]), ("activePermissionProfile", {}),
                       ("approvalPolicy", "on-request"), ("sandbox", {"type": "dangerFullAccess"}),
                       ("model", "another-model")]:
        altered = {**payload, key: value}
        with pytest.raises(CodexIntegrationError):
            asyncio.run(gateway._start_thread(NS(_client=FakeRPC(altered)), str(tmp_path)))


@pytest.mark.parametrize("status,tools,allowed", [
    ("disabled", {}, True), ("connected", {"read": {}}, False),
    ("starting", {}, False), (None, {}, False), ("disabled", {"read": {}}, False),
])
def test_mcp_inventory_accepts_only_disabled_empty_entries(tmp_path, status, tools, allowed):
    class Inventory(FakeRPC):
        async def request(self, method, params, *, response_model):
            if method == "mcpServerStatus/list":
                return RPCPayload({"data": [{"runtimeStatus": status, "tools": tools, "resources": [], "resourceTemplates": []}]})
            return await super().request(method, params, response_model=response_model)
    payload = {
        "thread": {"id": "test"}, "model": MODEL, "modelProvider": "openai",
        "instructionSources": [], "approvalPolicy": "never",
        "sandbox": {"type": "readOnly", "networkAccess": False}, "activePermissionProfile": {"id": "rag_answer"},
    }
    call = lambda: asyncio.run(EvidenceGateway()._start_thread(NS(_client=Inventory(payload)), str(tmp_path)))
    if allowed: assert call().id == "test"
    else:
        with pytest.raises(CodexIntegrationError): call()


def test_skill_discovery_errors_fail_closed(tmp_path):
    class BrokenSkills:
        async def request(self, method, params, *, response_model):
            return RPCPayload({"config": {}} if method == "config/read" else {"data": [{"errors": ["unreadable"], "skills": []}]})
    with pytest.raises(CodexIntegrationError, match="discovery failed"):
        asyncio.run(inspect(BrokenSkills(), tmp_path))


def test_isolation_failure_prevents_any_thread_or_turn(tmp_path):
    from test_codex_gateway import FakeClient
    clients = []
    class Guarded(EvidenceGateway):
        async def _prepare_config(self, config, directory): return config
        async def _validate_session(self, client, directory):
            raise CodexIntegrationError("isolation_unverified", "Blocked by isolation check")
    def factory(config):
        client = FakeClient(config)
        clients.append(client)
        return client
    gateway = Guarded(Settings(runtime_dir=tmp_path), client_factory=factory)
    with pytest.raises(CodexIntegrationError): asyncio.run(gateway.generate("synthetic evidence"))
    assert clients[0].thread_options is None and clients[0].closed
    assert not list(tmp_path.iterdir())
