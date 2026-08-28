from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from .trace import Trace


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    values = sorted(values)
    index = (len(values) - 1) * p
    lower, upper = int(index), min(int(index) + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (index - lower)


def build_report(traces: list[Trace], threshold: float, duration_seconds: float | None = None) -> dict[str, Any]:
    groups: dict[int, list[Trace]] = defaultdict(list)
    for trace in traces:
        groups[trace.concurrency].append(trace)
    levels = []
    for users, rows in sorted(groups.items()):
        successes = [row for row in rows if row.task_success]
        attempted = len(rows)
        total_cost = sum(row.estimated_cost_usd for row in rows)
        elapsed = duration_seconds or max(sum(row.latency_ms for row in rows) / 1000, 1)
        levels.append({
            "concurrency": users, "attempted_tasks": attempted,
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
        })
    breaking = next((row["concurrency"] for row in levels if row["task_success_rate"] < threshold), None)
    return {"success_threshold": threshold, "breaking_point": breaking, "levels": levels}


def markdown_report(report: dict[str, Any]) -> str:
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
