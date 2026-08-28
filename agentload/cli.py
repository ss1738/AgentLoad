from __future__ import annotations

import argparse
import sys

from .analyze import build_report, markdown_report, write_report
from .config import load_scenario
from .runner import run_scenario
from .trace import read_traces

EXIT_OK = 0
EXIT_THRESHOLD = 2
EXIT_INVALID_CONFIG = 3
EXIT_EXECUTION_FAILED = 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentload", description="Measure HTTP agent reliability under load.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a YAML scenario")
    run.add_argument("scenario")
    run.add_argument("--host", required=True)
    run.add_argument("--output", default="agentload-results")
    run.add_argument("--fail-under-threshold", "--fail-on-threshold", action="store_true", dest="fail_under_threshold", help="exit 2 after writing reports when a stage fails")
    analyze = commands.add_parser("analyze", help="analyze auditable JSONL traces")
    analyze.add_argument("traces")
    analyze.add_argument("--threshold", type=float, required=True)
    analyze.add_argument("--output")
    analyze.add_argument("--fail-under-threshold", action="store_true", help="exit 2 when a breaking point is found")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            report = run_scenario(load_scenario(args.scenario), args.host, args.output)
            print(markdown_report(report))
            return EXIT_THRESHOLD if args.fail_under_threshold and report["breaking_point"] is not None else EXIT_OK
        if not 0 <= args.threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        report = build_report(read_traces(args.traces), args.threshold)
        if args.output:
            write_report(args.output, report)
        print(markdown_report(report))
        return EXIT_THRESHOLD if args.fail_under_threshold and report["breaking_point"] is not None else EXIT_OK
    except (ValueError, OSError) as exc:
        print(f"agentload: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    except Exception as exc:
        print(f"agentload: execution failed: {exc}", file=sys.stderr)
        return EXIT_EXECUTION_FAILED


if __name__ == "__main__":
    sys.exit(main())
