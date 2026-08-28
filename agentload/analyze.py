from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .trace import FailureCategory, Trace, read_traces

class AnalysisError(ValueError): pass

def build_report_from_stages(output: str | Path, threshold: float, scenario_name: str | None = None) -> dict[str, Any]:
    """Read only finalized stage pairs; incomplete stages remain visible."""
    directory = Path(output) / "stages"
    metas = {p.stem.removesuffix(".meta"): p for p in directory.glob("concurrency-*.meta.json")}
    traces = {p.stem: p for p in directory.glob("concurrency-*.jsonl")}
    if set(metas) != set(traces):
        raise AnalysisError("stage metadata and trace files must be paired")
    all_traces: list[Trace] = []; stage_data = []
    for key in sorted(metas, key=lambda value: int(value.rsplit("-", 1)[1])):
        try: meta = json.loads(metas[key].read_text())
        except json.JSONDecodeError as exc: raise AnalysisError(f"malformed metadata: {metas[key].name}") from exc
        rows = read_traces(traces[key])
        concurrency = int(key.rsplit("-", 1)[1])
        if meta.get("concurrency") != concurrency or any(row.concurrency != concurrency for row in rows): raise AnalysisError(f"concurrency mismatch: {key}")
        if meta.get("trace_count") != len(rows): raise AnalysisError(f"trace count mismatch: {key}")
        all_traces.extend(rows)
        stage = build_report(rows, threshold, scenario_name=scenario_name)["levels"]
        summary = stage[0] if stage else {"concurrency": concurrency, "attempted_tasks": 0, "successful_tasks": 0, "failed_tasks": 0}
        completed = meta.get("status") == "completed"; duration = meta.get("observed_duration_seconds")
        summary.update({"status": meta.get("status"), "configured_duration_seconds": meta.get("configured_duration_seconds"), "observed_duration_seconds": duration, "attempts": summary.pop("attempted_tasks"), "successes": summary.pop("successful_tasks"), "failures": summary.pop("failed_tasks")})
        summary["successful_tasks_per_minute"] = summary["successes"] * 60 / duration if completed and duration and duration > 0 else None
        stage_data.append(summary)
    completed = [s for s in stage_data if s["status"] == "completed"]
    breaking = next((s["concurrency"] for s in completed if s["task_success_rate"] < threshold), None)
    return {"report_version":"0.2", "scenario_name":scenario_name, "success_threshold":threshold, "aggregate_trace_count":len(all_traces), "highest_passing_concurrency":max((s["concurrency"] for s in completed if s["task_success_rate"] >= threshold), default=None), "breaking_point":breaking, "incomplete_stages":[s["concurrency"] for s in stage_data if s["status"] != "completed"], "stages":stage_data}


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = (len(values) - 1) * p
    lower, upper = int(index), min(int(index) + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def build_report(traces: list[Trace], threshold: float, duration_seconds: float | None = None, scenario_name: str | None = None) -> dict[str, Any]:
    groups: dict[int, list[Trace]] = defaultdict(list)
    for trace in traces:
        groups[trace.concurrency].append(trace)
    levels = []
    for users, rows in sorted(groups.items()):
        successes = [row for row in rows if row.task_success]
        attempted = len(rows)
        failure_counts = {category.value: sum(row.failure_category == category for row in rows) for category in FailureCategory if category is not FailureCategory.SUCCESS}
        total_cost = sum(row.estimated_cost_usd for row in rows)
        elapsed = duration_seconds or max(sum(row.latency_ms for row in rows) / 1000, 1)
        levels.append({
            "concurrency": users, "attempted_tasks": attempted,
            "successful_tasks": len(successes), "failed_tasks": attempted - len(successes), "completion_status": "completed",
            "task_success_rate": len(successes) / attempted if attempted else 0.0,
            "successful_tasks_per_minute": len(successes) * 60 / elapsed,
            "p50_latency_ms": percentile([r.latency_ms for r in rows], .5),
            "p95_latency_ms": percentile([r.latency_ms for r in rows], .95),
            "total_tokens": sum(r.input_tokens + r.output_tokens for r in rows),
            "total_cost_usd": total_cost,
            "cost_per_successful_task_usd": total_cost / len(successes) if successes else None,
            "http_429_rate": sum(r.http_status == 429 for r in rows) / attempted if attempted else 0.0,
            "timeout_rate": sum(r.failure_category == "timeout" for r in rows) / attempted if attempted else 0.0,
            "max_loop_depth": max((r.loop_depth for r in rows), default=0),
            "failure_counts": failure_counts,
            "failure_rates": {key: value / attempted if attempted else 0.0 for key, value in failure_counts.items()},
        })
    breaking = next((row["concurrency"] for row in levels if row["task_success_rate"] < threshold), None)
    return {"report_version": "0.2", "scenario_name": scenario_name, "success_threshold": threshold, "breaking_point": breaking,
            "highest_passing_concurrency": max((r["concurrency"] for r in levels if r["task_success_rate"] >= threshold), default=None),
            "aggregate_trace_count": len(traces), "incomplete_stage_warning": False, "levels": levels}


def markdown_report(report: dict[str, Any]) -> str:
    if "stages" in report:
        lines = ["# AgentLoad report", "", f"Scenario: {report.get('scenario_name') or 'n/a'}", f"Report version: {report['report_version']}", f"Required success threshold: {report['success_threshold']:.1%}", f"Aggregate retained traces: {report['aggregate_trace_count']}", f"Highest passing concurrency: {report['highest_passing_concurrency'] if report['highest_passing_concurrency'] is not None else 'n/a'}", f"Breaking point: {report['breaking_point'] if report['breaking_point'] is not None else 'n/a'}", "", "| Users | Status | Attempts | Success | Tasks/min | p95 | Cost/success | 429 | Timeout | Top failure |", "| ----: | ------ | -------: | ------: | --------: | --: | -----------: | --: | ------: | ----------- |"]
        for stage in report["stages"]:
            rate = stage.get("successful_tasks_per_minute"); cost = stage.get("cost_per_successful_task_usd")
            failures = [(key, value) for key, value in stage["failure_counts"].items() if value]
            top = max(failures, key=lambda item: (item[1], item[0]))[0] if failures else "n/a"
            lines.append(f"| {stage['concurrency']} | {stage['status']} | {stage['attempts']} | {stage['task_success_rate']:.1%} | {'n/a' if rate is None else f'{rate:.1f}'} | {stage['p95_latency_ms']:.1f} ms | {'n/a' if cost is None else f'${cost:.4f}'} | {stage['http_429_rate']:.1%} | {stage['timeout_rate']:.1%} | {top} |")
            if failures: lines.append(f"\nFailures at {stage['concurrency']}: " + ", ".join(f"{key}: {value}" for key, value in failures))
        if report["incomplete_stages"]: lines += ["", "**Incomplete stages retained:** " + ", ".join(map(str, report["incomplete_stages"]))]
        return "\n".join(lines) + "\n"
    lines = ["# AgentLoad report", "", "| Users | Tasks | Success | Tasks/min | p95 latency | Cost/success | 429 rate | Timeout rate | Max loop |", "| ----: | ----: | ------: | --------: | ----------: | -----------: | -------: | -----------: | -------: |"]
    for r in report["levels"]:
        cost = "n/a" if r["cost_per_successful_task_usd"] is None else f"${r['cost_per_successful_task_usd']:.4f}"
        lines.append(f"| {r['concurrency']} | {r['attempted_tasks']} | {r['task_success_rate']:.1%} | {r['successful_tasks_per_minute']:.1f} | {r['p95_latency_ms']:.1f} ms | {cost} | {r['http_429_rate']:.1%} | {r['timeout_rate']:.1%} | {r['max_loop_depth']} |")
    breaking = report["breaking_point"]
    lines += ["", f"**Breaking point: {breaking} concurrent users. Success fell below the required {report['success_threshold']:.0%} threshold.**" if breaking is not None else f"**No breaking point observed at the tested concurrency levels (required {report['success_threshold']:.0%}).**", ""]
    return "\n".join(lines)


def write_report(output: str | Path, report: dict[str, Any]) -> None:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    (output / "report.md").write_text(markdown_report(report))
