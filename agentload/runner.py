from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import gevent
from locust import HttpUser, between, task
from locust.env import Environment

from .analyze import build_report, write_report
from .classify import classify
from .config import Assertions, Scenario
from .trace import FailureCategory, Trace, write_traces


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
    traces: list[Trace] = []
    host_url = host
    for users in scenario.concurrency:
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
        runner.start(users, spawn_rate=scenario.spawn_rate)
        gevent.sleep(scenario.duration_seconds)
        runner.quit()
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_traces(output / "traces.jsonl", traces)
    report = build_report(traces, scenario.success_threshold, scenario.duration_seconds)
    write_report(output, report)
    return report
