from __future__ import annotations

import time
import json
from dataclasses import asdict, dataclass
from enum import Enum
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import gevent
from locust import HttpUser, between, task
from locust.env import Environment

from .analyze import build_report, write_report
from .classify import classify
from .config import Assertions, Scenario
from .trace import FailureCategory, Trace, write_traces

class StageStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"
    NOT_STARTED = "not_started"

@dataclass(frozen=True)
class StageMetadata:
    concurrency: int
    configured_duration_seconds: float
    observed_start_utc: str
    observed_end_utc: str | None
    observed_duration_seconds: float | None
    spawn_rate: float
    status: StageStatus
    exit_code: int | None
    trace_file: str
    trace_count: int
    failure_reason: str | None = None

def write_stage_metadata(path: Path, metadata: StageMetadata) -> None:
    data = asdict(metadata); data["status"] = metadata.status.value
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    temporary.replace(path)


def assess(status: int | None, payload: dict[str, Any], assertions: Assertions, latency_ms: float) -> tuple[bool, str | None]:
    category, message = classify(status, payload, assertions, latency_ms)
    return category is FailureCategory.SUCCESS, message


def _trace(concurrency: int, response: Any, payload: dict[str, Any] | None, latency_ms: float, scenario: Scenario, error: BaseException | None = None) -> Trace:
    status = response.status_code if response is not None else None
    category, message = classify(status, payload, scenario.assertions, latency_ms, error)
    payload = payload or {}
    return Trace(concurrency=concurrency, latency_ms=latency_ms, http_status=status, task_success=category is FailureCategory.SUCCESS,
                 input_tokens=int(payload.get("input_tokens", 0)), output_tokens=int(payload.get("output_tokens", 0)),
                 estimated_cost_usd=float(payload.get("estimated_cost_usd", 0)), tool_call_count=len(payload.get("tool_calls", [])),
                 loop_depth=int(payload.get("loop_depth", 0)), failure_category=category, error_message=message)


def run_scenario(scenario: Scenario, host: str, output: str | Path) -> dict[str, Any]:
    """Run each level using Locust's HTTP client semantics through its current API.

    Locust owns virtual-user concurrency, ramp-up, HTTP timing, and request events.
    Semantic failures are marked once with ``response.failure``; no deprecated event
    hooks are fired manually.
    """
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    for filename in ("traces.jsonl", "report.json", "report.md"):
        (output / filename).unlink(missing_ok=True)
    stages = output / "stages"
    if stages.exists():
        for path in stages.glob("concurrency-*.jsonl"): path.unlink()
        for path in stages.glob("concurrency-*.meta.json"): path.unlink()
    stages.mkdir(exist_ok=True)
    traces: list[Trace] = []
    host_url = host
    for users in scenario.concurrency:
        stage_start = len(traces)
        monotonic_start = time.monotonic()
        wall_start = datetime.now(timezone.utc).isoformat()
        trace_file = stages / f"concurrency-{users}.jsonl"
        meta_file = stages / f"concurrency-{users}.meta.json"
        counter = iter(range(10**9))

        class ScenarioUser(HttpUser):
            wait_time = between(0.001, 0.003)
            host = host_url

            @task
            def send_task(self):
                prompt = scenario.tasks[next(counter) % len(scenario.tasks)]["prompt"]
                context: dict[str, Any] = {"concurrency": users, "payload": {}}
                began = time.monotonic()
                with self.client.post(scenario.endpoint, json={"prompt": prompt}, catch_response=True, context=context) as response:
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = None
                    response.request_meta["context"]["payload"] = payload
                    category, message = classify(response.status_code, payload, scenario.assertions, (time.monotonic() - began) * 1000)
                    response.request_meta["context"]["semantic_reason"] = message
                    if category is not FailureCategory.SUCCESS:
                        response.failure(message or category.value)

        environment = Environment(user_classes=[ScenarioUser])
        def capture(request_type: str, name: str, response_time: float, response_length: int, response: Any, context: dict[str, Any], exception: Exception | None, **_: Any) -> None:
            payload = (context or {}).get("payload")
            trace = _trace(users, response, payload, response_time, scenario, exception)
            traces.append(trace)
        environment.events.request.add_listener(capture)
        runner = environment.create_local_runner()
        status = StageStatus.COMPLETED; reason = None
        try:
            runner.start(users, spawn_rate=scenario.spawn_rate)
            gevent.sleep(scenario.duration_seconds)
        except BaseException as exc:
            status = StageStatus.INTERRUPTED if isinstance(exc, KeyboardInterrupt) else StageStatus.FAILED
            reason = type(exc).__name__
        finally:
            runner.quit()
            stage_traces = traces[stage_start:]
            write_traces(trace_file, stage_traces)
            write_stage_metadata(meta_file, StageMetadata(users, scenario.duration_seconds, wall_start, datetime.now(timezone.utc).isoformat(), time.monotonic()-monotonic_start, scenario.spawn_rate, status, 0 if status is StageStatus.COMPLETED else 1, str(trace_file.relative_to(output)), len(stage_traces), reason))
        if status is not StageStatus.COMPLETED:
            break
    write_traces(output / "traces.jsonl", traces)
    report = build_report(traces, scenario.success_threshold, scenario.duration_seconds, scenario.name)
    write_report(output, report)
    return report
