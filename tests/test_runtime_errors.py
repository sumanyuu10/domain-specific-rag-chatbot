"""Pinned SDK error shapes, public streaming and safe messages; no live calls."""
import asyncio
from types import SimpleNamespace as NS

import pytest
from openai_codex.errors import JsonRpcError, TransportClosedError
from openai_codex.generated.v2_all import CodexErrorInfo

from src.generation.llm import CodexIntegrationError
from src.generation.runtime import classify_info, collect_turn
from test_codex_gateway import make_gateway
from src.generation.comparison import ComparisonService
from comparison_helpers import FakeComparisonGateway


@pytest.mark.parametrize("info,code", [
    ("unauthorized", "authentication_required"), ("usageLimitExceeded", "quota_exceeded"),
    ("rateLimitExceeded", "rate_limited"), ("contextWindowExceeded", "context_limit"),
    ("sessionBudgetExceeded", "context_limit"), ("badRequest", "request_rejected"),
    ({"httpConnectionFailed": {"httpStatusCode": 401}}, "authentication_required"),
    ({"httpConnectionFailed": {"httpStatusCode": 429}}, "rate_limited"),
    ({"httpConnectionFailed": {"httpStatusCode": 503}}, "network_error"),
    ({"responseStreamDisconnected": {"httpStatusCode": None}}, "network_error"),
])
def test_official_pinned_error_info_maps_without_message_guessing(info, code):
    assert classify_info(CodexErrorInfo.model_validate(info)) == code


@pytest.mark.parametrize("info,code", [("unauthorized", "authentication_required"), ("usageLimitExceeded", "quota_exceeded"), ("rateLimitExceeded", "rate_limited")])
def test_structured_rpc_error_is_safe_and_closes_sdk(tmp_path, caplog, info, code):
    gateway, clients = make_gateway(tmp_path, start_error=JsonRpcError(-32000, "PRIVATE-token-passage", {"codexErrorInfo": info}))
    with pytest.raises(CodexIntegrationError) as caught:
        asyncio.run(gateway.generate("PRIVATE question"))
    assert caught.value.code == code
    assert "PRIVATE" not in str(caught.value) + caplog.text
    assert clients[0].closed
    assert not list(tmp_path.iterdir())


def test_transport_failure_has_network_guidance(tmp_path):
    gateway, _ = make_gateway(tmp_path, start_error=TransportClosedError("private runtime stderr"))
    with pytest.raises(CodexIntegrationError) as caught:
        asyncio.run(gateway.preflight())
    assert caught.value.code == "network_error" and "private" not in str(caught.value)


class StreamHandle:
    id = "synthetic-turn"
    def __init__(self, info=None):
        self.info, self.closed = info, False
    async def stream(self):
        try:
            yield NS(method="item/completed", payload=NS(turn_id=self.id, item=NS(type="agentMessage", text="analysis-summary", phase="commentary")))
            yield NS(method="item/completed", payload=NS(turn_id=self.id, item=NS(type="agentMessage", text="verified answer", phase="final_answer")))
            error = NS(codex_error_info=CodexErrorInfo.model_validate(self.info), message="PRIVATE error") if self.info else None
            yield NS(method="turn/completed", payload=NS(turn=NS(id=self.id, status="failed" if self.info else "completed", error=error, duration_ms=10)))
        finally:
            self.closed = True


def test_public_turn_stream_preserves_typed_failure_and_closes():
    handle = StreamHandle("usageLimitExceeded")
    result = asyncio.run(collect_turn(handle))
    assert result.status == "failed" and classify_info(result.error_info) == "quota_exceeded"
    assert handle.closed


def test_public_turn_stream_uses_final_phase():
    handle = StreamHandle()
    result = asyncio.run(collect_turn(handle))
    assert result.final_response == "verified answer" and handle.closed


def test_gateway_maps_failed_stream_before_flattening_to_generic_error(tmp_path):
    from test_codex_gateway import FakeClient, FakeThread
    handle = StreamHandle("unauthorized")
    class Thread(FakeThread):
        async def turn(self, *_args, **_kwargs): return handle
    class Client(FakeClient):
        async def thread_start(self, **kwargs): return Thread(self)
    from src.generation.llm import CodexGateway
    from src.config import Settings
    gateway = CodexGateway(Settings(runtime_dir=tmp_path), client_factory=Client)
    with pytest.raises(CodexIntegrationError) as caught:
        asyncio.run(gateway.generate("synthetic"))
    assert caught.value.code == "authentication_required" and handle.closed


@pytest.mark.parametrize("code", ["quota_exceeded", "rate_limited", "context_limit", "request_rejected"])
def test_account_or_request_limit_stops_comparison_without_retry(library, make_pdf, code):
    ids = [library.ingest(make_pdf(title=str(i)), f"{i}.pdf").paper.paper_id for i in range(2)]
    def fail(*args): raise CodexIntegrationError(code, "Synthetic limit; retry later.")
    gateway = FakeComparisonGateway(fail)
    service = ComparisonService(library, gateway=gateway)
    result = service.compare(service.collect("", ids), allow_remote=True)
    assert result.status == "incomplete" and len(gateway.calls) == 1
    assert result.failures[1].code == "not_attempted"
    assert library.papers() and library.sparse.search("accuracy", library.catalog.chunks(), set(ids), 5)


def test_runtime_storage_failure_never_exposes_paths(tmp_path, caplog):
    path = tmp_path / 'file-not-directory'
    path.write_text('fixture')
    gateway, _ = make_gateway(path)
    with pytest.raises(CodexIntegrationError) as caught:
        asyncio.run(gateway.preflight())
    assert str(path) not in str(caught.value) + caplog.text
