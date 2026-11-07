"""Preserve structured failures from the pinned SDK's public turn stream.

SDK 0.163.0's run() flattens failed turns to RuntimeError(message), losing error
codes. This adapter consumes public notifications without logging their content.
"""
from dataclasses import dataclass

from openai_codex.errors import JsonRpcError, ServerBusyError, TransportClosedError


MESSAGES = {
    "authentication_required": "Codex sign-in is missing or expired. Run codex login, then retry. Local retrieval remains available.",
    "quota_exceeded": "Codex usage allowance is exhausted. Check your account limits and wait for reset before retrying. No credits were purchased.",
    "rate_limited": "Codex is rate limited. Wait before retrying; local evidence and completed cards remain available.",
    "context_limit": "Codex rejected the context size or session budget. Select fewer papers/categories or shorten the question and collect again.",
    "request_rejected": "Codex rejected this request. Check the supported runtime and account permissions; no model or authentication was substituted.",
    "network_error": "Codex could not reach or finish with the service. Check your connection and retry; local evidence remains available.",
}


def classify_info(info):
    if hasattr(info, "model_dump"):
        info = info.model_dump(mode="json", by_alias=True)
    info = getattr(info, "value", info)
    mapping = {
        "unauthorized": "authentication_required", "usageLimitExceeded": "quota_exceeded",
        "rateLimitExceeded": "rate_limited", "contextWindowExceeded": "context_limit",
        "sessionBudgetExceeded": "context_limit", "badRequest": "request_rejected",
        "sandboxError": "request_rejected", "serverOverloaded": "network_error",
        "internalServerError": "network_error",
    }
    if isinstance(info, str):
        return mapping.get(info)
    if isinstance(info, dict):
        for name in ("httpConnectionFailed", "responseStreamConnectionFailed", "responseStreamDisconnected", "responseTooManyFailedAttempts"):
            if name in info:
                status = (info[name] or {}).get("httpStatusCode") if isinstance(info[name], dict) else None
                return {401: "authentication_required", 403: "request_rejected", 429: "rate_limited"}.get(status, "network_error")
    return None


def classify_exception(error):
    if isinstance(error, (ServerBusyError, TransportClosedError, ConnectionError)):
        return "network_error"
    if isinstance(error, JsonRpcError) and isinstance(error.data, dict):
        for name in ("codexErrorInfo", "codex_error_info", "errorInfo"):
            code = classify_info(error.data.get(name))
            if code:
                return code
    return None


@dataclass
class CollectedTurn:
    status: str
    final_response: str | None
    items: list
    duration_ms: int | None
    error_info: object = None


async def collect_turn(handle):
    # Small test/injected clients may expose only run(). Official pinned handles
    # expose stream(); real notifications retain typed error codes before run()
    # would flatten them. No SDK version or authentication change is required.
    if not hasattr(handle, "stream"):
        return await handle.run()
    items, completed = [], None
    stream = handle.stream()
    try:
        async for event in stream:
            payload = event.payload
            if event.method == "item/completed" and payload.turn_id == handle.id:
                items.append(payload.item)
            elif event.method == "turn/completed" and payload.turn.id == handle.id:
                completed = payload.turn
    finally:
        await stream.aclose()
    if completed is None:
        raise RuntimeError("Missing turn completion")
    final, fallback = None, None
    for item in items:
        value = getattr(item, "root", item)
        if getattr(value, "type", None) == "agentMessage":
            phase = getattr(getattr(value, "phase", None), "value", getattr(value, "phase", None))
            if phase == "final_answer":
                final = value.text
            elif phase is None:
                fallback = value.text
    error = getattr(completed, "error", None)
    return CollectedTurn(
        status=getattr(completed.status, "value", completed.status),
        final_response=final if final is not None else fallback, items=items,
        duration_ms=completed.duration_ms, error_info=getattr(error, "codex_error_info", None),
    )
