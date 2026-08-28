"""Auditable, privacy-preserving records for one completed HTTP task."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any


class FailureCategory(StrEnum):
    SUCCESS = "success"
    HTTP_429 = "http_429"
    HTTP_4XX = "http_4xx"
    HTTP_5XX = "http_5xx"
    TIMEOUT = "timeout"
    CONNECTION_ERROR = "connection_error"
    INVALID_JSON = "invalid_json"
    SUCCESS_ASSERTION_FAILED = "success_assertion_failed"
    COST_LIMIT_EXCEEDED = "cost_limit_exceeded"
    LOOP_LIMIT_EXCEEDED = "loop_limit_exceeded"
    LATENCY_LIMIT_EXCEEDED = "latency_limit_exceeded"
    UNKNOWN_ERROR = "unknown_error"


def safe_message(error: object | None) -> str | None:
    """Keep an error useful without retaining responses, headers, or credentials."""
    if error is None:
        return None
    return str(error).replace("\n", " ")[:240]


@dataclass(frozen=True)
class Trace:
    concurrency: int
    latency_ms: float
    http_status: int | None
    task_success: bool
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost_usd: float = 0.0
    tool_call_count: int = 0
    loop_depth: int = 0
    failure_category: FailureCategory = FailureCategory.SUCCESS
    error_message: str | None = None
    stage_duration_seconds: float | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["failure_category"] = self.failure_category.value
        return data


def write_traces(path: str | Path, traces: list[Trace]) -> None:
    Path(path).write_text("".join(json.dumps(t.as_dict(), sort_keys=True) + "\n" for t in traces))


def read_traces(path: str | Path) -> list[Trace]:
    traces = []
    for line_no, line in enumerate(Path(path).read_text().splitlines(), 1):
        try:
            raw = json.loads(line)
            raw["failure_category"] = FailureCategory(raw.get("failure_category") or ("success" if raw.get("task_success") else "unknown_error"))
            raw.pop("semantic_reason", None)  # v0.1 compatibility
            traces.append(Trace(**raw))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise ValueError(f"Malformed trace at line {line_no}: {exc}") from exc
    return traces
