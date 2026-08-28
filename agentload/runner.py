from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import gevent
from locust import HttpUser, between, task
from locust.env import Environment

from .analyze import build_report, write_report
from .config import Assertions, Scenario
from .trace import FailureCategory, Trace, safe_message, write_traces


def assess(status: int | None, payload: dict[str, Any], assertions: Assertions, latency_ms: float) -> tuple[bool, str | None]:
    if status is None:
        return False, "timeout"
    if status >= 400:
        return False, "rate_limited" if status == 429 else "http_error"
    if payload.get(assertions.success_field) != assertions.required_value:
        return False, "assertion_failed"
    if assertions.max_cost_usd is not None and float(payload.get("estimated_cost_usd", 0)) > assertions.max_cost_usd:
        return False, "cost_exceeded"
    if assertions.max_loop_depth is not None and int(payload.get("loop_depth", 0)) > assertions.max_loop_depth:
        return False, "loop_depth_exceeded"
    if assertions.expected_tool_call and assertions.expected_tool_call not in payload.get("tool_calls", []):
        return False, "missing_tool_call"
    if assertions.max_latency_ms is not None and latency_ms > assertions.max_latency_ms:
        return False, "latency_exceeded"
    return True, None


def _trace(concurrency: int, response: Any, payload: dict[str, Any], latency_ms: float, scenario: Scenario) -> Trace:
    status = response.status_code if response is not None else None
    success, reason = assess(status, payload, scenario.assertions, latency_ms)
    categories = {"rate_limited": FailureCategory.HTTP_429, "http_error": FailureCategory.HTTP_5XX if status and status >= 500 else FailureCategory.HTTP_4XX,
                  "assertion_failed": FailureCategory.SUCCESS_ASSERTION_FAILED, "cost_exceeded": FailureCategory.COST_LIMIT_EXCEEDED,
                  "loop_depth_exceeded": FailureCategory.LOOP_LIMIT_EXCEEDED, "latency_exceeded": FailureCategory.LATENCY_LIMIT_EXCEEDED,
                  "timeout": FailureCategory.TIMEOUT}
    return Trace(concurrency=concurrency, latency_ms=latency_ms, http_status=status, task_success=success,
                 input_tokens=int(payload.get("input_tokens", 0)), output_tokens=int(payload.get("output_tokens", 0)),
                 estimated_cost_usd=float(payload.get("estimated_cost_usd", 0)), tool_call_count=len(payload.get("tool_calls", [])),
                 loop_depth=int(payload.get("loop_depth", 0)), failure_category=FailureCategory.SUCCESS if success else categories.get(reason, FailureCategory.UNKNOWN_ERROR), error_message=safe_message(reason))


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
                with self.client.post(scenario.endpoint, json={"prompt": prompt}, catch_response=True, context=context) as response:
                    try:
                        payload = response.json()
                    except ValueError:
                        payload = {}
                    response.request_meta["context"]["payload"] = payload
                    success, reason = assess(response.status_code, payload, scenario.assertions, response.elapsed.total_seconds() * 1000)
                    response.request_meta["context"]["semantic_reason"] = reason
                    if not success:
                        response.failure(reason or "semantic failure")

        environment = Environment(user_classes=[ScenarioUser])
        def capture(request_type: str, name: str, response_time: float, response_length: int, response: Any, context: dict[str, Any], exception: Exception | None, **_: Any) -> None:
            payload = (context or {}).get("payload", {})
            trace = _trace(users, response, payload, response_time, scenario)
            if exception and trace.failure_category is None:
                trace.failure_category = "transport_error"
                trace.task_success = False
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
