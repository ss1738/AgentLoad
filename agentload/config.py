from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class Assertions:
    success_field: str
    required_value: Any
    max_loop_depth: int | None = None
    max_cost_usd: float | None = None
    expected_tool_call: str | None = None
    max_latency_ms: float | None = None


@dataclass(frozen=True)
class Scenario:
    name: str
    endpoint: str
    concurrency: list[int]
    duration_seconds: float
    spawn_rate: float
    success_threshold: float
    tasks: list[dict[str, Any]]
    assertions: Assertions


def _fail(message: str) -> ValueError:
    return ValueError(f"Invalid scenario: {message}")


def load_scenario(path: str | Path) -> Scenario:
    try:
        data = yaml.safe_load(Path(path).read_text())
    except (OSError, yaml.YAMLError) as exc:
        raise _fail(str(exc)) from exc
    if not isinstance(data, dict):
        raise _fail("root must be a mapping")
    required = ("name", "endpoint", "concurrency", "duration_seconds", "spawn_rate", "success_threshold", "tasks", "assertions")
    missing = [key for key in required if key not in data]
    if missing:
        raise _fail("missing " + ", ".join(missing))
    levels = data["concurrency"]
    if not isinstance(levels, list) or not levels or any(not isinstance(x, int) or x < 1 for x in levels):
        raise _fail("concurrency must be a non-empty list of positive integers")
    if not isinstance(data["tasks"], list) or not data["tasks"] or any(not isinstance(x, dict) or not isinstance(x.get("prompt"), str) for x in data["tasks"]):
        raise _fail("tasks must be a non-empty list with prompt strings")
    if not isinstance(data["assertions"], dict) or "success_field" not in data["assertions"] or "required_value" not in data["assertions"]:
        raise _fail("assertions requires success_field and required_value")
    for key in ("duration_seconds", "spawn_rate"):
        if not isinstance(data[key], (int, float)) or data[key] <= 0:
            raise _fail(f"{key} must be positive")
    threshold = data["success_threshold"]
    if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
        raise _fail("success_threshold must be between 0 and 1")
    a = data["assertions"]
    return Scenario(str(data["name"]), str(data["endpoint"]), levels, float(data["duration_seconds"]), float(data["spawn_rate"]), float(threshold), data["tasks"], Assertions(**a))
