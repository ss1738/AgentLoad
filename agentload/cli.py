from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyze import AnalysisError, build_report, build_report_from_stages, markdown_report, write_report
from .config import load_scenario
from .trace import read_traces

EXIT_OK = 0
EXIT_INVALID_CONFIG = 2
EXIT_EXECUTION_FAILED = 3
EXIT_THRESHOLD = 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="agentload", description="Measure HTTP agent reliability under load.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="run a YAML scenario")
    run.add_argument("scenario")
    run.add_argument("--host", required=True)
    run.add_argument("--output", default="agentload-results")
    run.add_argument("--fail-under-threshold", "--fail-on-threshold", action="store_true", dest="fail_under_threshold", help="exit 4 after writing reports when a stage fails")
    analyze = commands.add_parser("analyze", help="analyze JSONL traces or a stage-output directory")
    analyze.add_argument("traces")
    analyze.add_argument("--threshold", type=float, required=True)
    analyze.add_argument("--output")
    analyze.add_argument("--fail-under-threshold", action="store_true", help="exit 4 when a breaking point is found")
    args = parser.parse_args(argv)
    try:
        if args.command == "run":
            scenario = load_scenario(args.scenario)
            from .runner import run_scenario

            report = run_scenario(scenario, args.host, args.output)
            print(markdown_report(report))
            return EXIT_THRESHOLD if args.fail_under_threshold and report["breaking_point"] is not None else EXIT_OK
        if not 0 <= args.threshold <= 1:
            raise ValueError("threshold must be between 0 and 1")
        source = Path(args.traces)
        report = build_report_from_stages(source, args.threshold) if source.is_dir() else build_report(read_traces(source), args.threshold)
        if args.output:
            write_report(args.output, report)
        print(markdown_report(report))
        return EXIT_THRESHOLD if args.fail_under_threshold and report["breaking_point"] is not None else EXIT_OK
    except (OSError, AnalysisError) as exc:
        print(f"agentload: execution failed: {exc}", file=sys.stderr)
        return EXIT_EXECUTION_FAILED
    except ValueError as exc:
        print(f"agentload: {exc}", file=sys.stderr)
        return EXIT_INVALID_CONFIG
    except Exception as exc:
        print(f"agentload: execution failed: {exc}", file=sys.stderr)
        return EXIT_EXECUTION_FAILED


if __name__ == "__main__":
    sys.exit(main())
