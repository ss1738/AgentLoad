from __future__ import annotations

import argparse
import sys

from .analyze import build_report, markdown_report, write_report
from .config import load_scenario
from .runner import run_scenario
from .trace import read_traces


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentload", description="Measure HTTP agent reliability under load.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a YAML scenario")
    run.add_argument("scenario")
    run.add_argument("--host", required=True)
    run.add_argument("--output", default="agentload-results")
    run.add_argument("--fail-on-threshold", action="store_true")
    analyze = commands.add_parser("analyze", help="analyze auditable JSONL traces")
    analyze.add_argument("traces")
    analyze.add_argument("--threshold", type=float, required=True)
    analyze.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            report = run_scenario(load_scenario(args.scenario), args.host, args.output)
            print(markdown_report(report))
            return 2 if args.fail_on_threshold and report["breaking_point"] is not None else 0
        if not 0 <= args.threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        report = build_report(read_traces(args.traces), args.threshold)
        if args.output:
            write_report(args.output, report)
        print(markdown_report(report))
        return 0
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    return 1


if __name__ == "__main__":
    sys.exit(main())
