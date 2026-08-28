from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass
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
    failure_category: str | None = None
    semantic_reason: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_traces(path: str | Path, traces: list[Trace]) -> None:
    Path(path).write_text("".join(json.dumps(trace.as_dict(), sort_keys=True) + "\n" for trace in traces))


def read_traces(path: str | Path) -> list[Trace]:
    traces = []
    for line_no, line in enumerate(Path(path).read_text().splitlines(), 1):
        try:
            traces.append(Trace(**json.loads(line)))
        except (json.JSONDecodeError, TypeError) as exc:
            raise ValueError(f"Malformed trace at line {line_no}: {exc}") from exc
    return traces
