"""Pure, ordered classification for an HTTP agent attempt."""
from __future__ import annotations
from .config import Assertions
from .trace import FailureCategory, safe_message

def classify(status: int | None, payload: dict | None, assertions: Assertions, latency_ms: float, error: BaseException | None = None) -> tuple[FailureCategory, str | None]:
    """HTTP and transport failures take precedence over semantic assertions."""
    if error is not None:
        name = type(error).__name__.lower()
        return (FailureCategory.TIMEOUT if "timeout" in name else FailureCategory.CONNECTION_ERROR if "connection" in name else FailureCategory.UNKNOWN_ERROR, safe_message(error))
    if status is None: return FailureCategory.TIMEOUT, "no HTTP response"
    if status == 429: return FailureCategory.HTTP_429, "HTTP 429"
    if 400 <= status < 500: return FailureCategory.HTTP_4XX, f"HTTP {status}"
    if status >= 500: return FailureCategory.HTTP_5XX, f"HTTP {status}"
    if payload is None: return FailureCategory.INVALID_JSON, "invalid JSON response"
    if payload.get(assertions.success_field) != assertions.required_value: return FailureCategory.SUCCESS_ASSERTION_FAILED, "required value did not match"
    if assertions.max_cost_usd is not None and float(payload.get("estimated_cost_usd", 0)) > assertions.max_cost_usd: return FailureCategory.COST_LIMIT_EXCEEDED, "cost limit exceeded"
    if assertions.max_loop_depth is not None and int(payload.get("loop_depth", 0)) > assertions.max_loop_depth: return FailureCategory.LOOP_LIMIT_EXCEEDED, "loop limit exceeded"
    if assertions.max_latency_ms is not None and latency_ms > assertions.max_latency_ms: return FailureCategory.LATENCY_LIMIT_EXCEEDED, "latency limit exceeded"
    return FailureCategory.SUCCESS, None
