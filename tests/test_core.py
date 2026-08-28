import json

import pytest

from agentload.analyze import build_report, markdown_report, percentile
from agentload.config import load_scenario
from agentload.runner import assess
from agentload.trace import Trace, read_traces, write_traces


def test_config_valid_and_invalid(tmp_path):
    valid = tmp_path / "a.yml"
    valid.write_text('name: x\nendpoint: /agent\nconcurrency: [1]\nduration_seconds: 1\nspawn_rate: 1\nsuccess_threshold: 0.9\ntasks: [{prompt: hi}]\nassertions: {success_field: success, required_value: true}\n')
    assert load_scenario(valid).name == "x"
    valid.write_text("name: x\n")
    with pytest.raises(ValueError, match="missing"):
        load_scenario(valid)


def test_assertions_and_metrics():
    scenario = type("S", (), {"success_field": "success", "required_value": True, "max_cost_usd": .01, "max_loop_depth": 3, "expected_tool_call": None, "max_latency_ms": None})()
    assert assess(200, {"success": True, "estimated_cost_usd": .001, "loop_depth": 1}, scenario, 2) == (True, None)
    assert assess(429, {}, scenario, 2)[1] == "HTTP 429"
    assert percentile([1, 3, 5], .95) == pytest.approx(4.8)
    report = build_report([Trace(1, 10, 200, True, estimated_cost_usd=.01), Trace(1, 20, 429, False, failure_category="rate_limited", estimated_cost_usd=.01), Trace(10, 30, 200, False)], .5, 10)
    assert report["breaking_point"] == 10
    assert report["levels"][0]["cost_per_successful_task_usd"] == .02
    assert report["levels"][1]["cost_per_successful_task_usd"] is None
    assert "Breaking point: 10" in markdown_report(report)


def test_trace_roundtrip_and_no_breaking(tmp_path):
    path = tmp_path / "traces.jsonl"
    write_traces(path, [Trace(1, 2, 200, True)])
    assert read_traces(path)[0].task_success
    assert build_report(read_traces(path), .9)["breaking_point"] is None
    path.write_text("not json\n")
    with pytest.raises(ValueError, match="Malformed"):
        read_traces(path)
