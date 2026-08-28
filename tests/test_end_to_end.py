import errno
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import urlopen
import pytest

ROOT = Path(__file__).parents[1]
REQUIRE_E2E = "AGENTLOAD_REQUIRE_E2E"


def _listener_denial_is_skippable(error: PermissionError) -> bool:
    """Only the managed sandbox's explicit listener denial is skippable."""
    return error.errno in {errno.EPERM, errno.EACCES}


def _skip_or_fail_listener_denial(error: PermissionError) -> None:
    detail = f"loopback listener denied: {error!r}"
    if os.environ.get(REQUIRE_E2E) == "1":
        pytest.fail(f"{detail}; {REQUIRE_E2E}=1 requires end-to-end execution")
    pytest.skip(detail)


@pytest.fixture
def simulator():
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", 0))
        except PermissionError as error:
            if _listener_denial_is_skippable(error):
                _skip_or_fail_listener_denial(error)
            raise
        port = sock.getsockname()[1]
    env = os.environ | {
        "AGENTLOAD_SIMULATOR_MODE": "concurrency_degradation",
        "AGENTLOAD_SIMULATOR_FAIL_AT": "4",
        "AGENTLOAD_SIMULATOR_DELAY_SECONDS": ".04",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "examples.mock_agent:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                with urlopen(f"http://127.0.0.1:{port}/health", timeout=.2) as response:
                    if json.load(response)["status"] == "ok":
                        break
            except OSError:
                time.sleep(.03)
        else:
            pytest.fail("server readiness timeout")
        yield f'http://127.0.0.1:{port}', process
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        assert process.poll() is not None


def test_listener_denial_skip_decision():
    assert _listener_denial_is_skippable(PermissionError(errno.EPERM, "denied"))
    assert _listener_denial_is_skippable(PermissionError(errno.EACCES, "denied"))
    assert not _listener_denial_is_skippable(PermissionError(errno.EADDRINUSE, "in use"))


def test_real_cli_reports_and_cleans_up(simulator, tmp_path):
    host, process = simulator
    scenario = tmp_path / "scenario.yml"
    sentinel = "AGENTLOAD_TEST_SECRET_SENTINEL"
    scenario.write_text(f'''name: deterministic-e2e
endpoint: /agent
concurrency: [1, 4]
duration_seconds: 0.2
spawn_rate: 100
success_threshold: 0.90
tasks: [{{prompt: {sentinel}}}]
assertions: {{success_field: success, required_value: true, max_loop_depth: 5, max_cost_usd: 0.05}}
''')
    normal_output = tmp_path / "normal-result"
    normal = subprocess.run(
        [sys.executable, "-m", "agentload.cli", "run", str(scenario), "--host", host, "--output", str(normal_output)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert normal.returncode == 0, normal.stderr
    output = tmp_path / "threshold-result"
    threshold = subprocess.run(
        [sys.executable, "-m", "agentload.cli", "run", str(scenario), "--host", host, "--output", str(output), "--fail-under-threshold"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert threshold.returncode == 4, threshold.stderr
    expected = ("traces.jsonl", "report.json", "report.md", "stages/concurrency-1.jsonl", "stages/concurrency-1.meta.json", "stages/concurrency-4.jsonl", "stages/concurrency-4.meta.json")
    assert all((output / name).exists() for name in expected)
    report = json.loads((output / "report.json").read_text())
    assert report["breaking_point"] == 4
    assert report["highest_passing_concurrency"] == 1
    assert "Breaking point: 4" in (output / "report.md").read_text()
    stage_rows = [(output / "stages" / f"concurrency-{users}.jsonl").read_text().splitlines() for users in (1, 4)]
    combined_rows = (output / "traces.jsonl").read_text().splitlines()
    assert len(combined_rows) == sum(len(rows) for rows in stage_rows)
    trace_failures = sum(not json.loads(row)["task_success"] for row in combined_rows)
    assert trace_failures == sum(level["failed_tasks"] for level in report["levels"])
    text = "".join(path.read_text() for path in output.rglob("*") if path.is_file()) + threshold.stdout + threshold.stderr
    assert sentinel not in text
    assert process.poll() is None
    shutil.rmtree(output)
    assert not output.exists()
    print(
        "E2E summary: breaking_point=4 highest_passing=1 "
        f"normal_exit={normal.returncode} threshold_exit={threshold.returncode} "
        f"traces={len(combined_rows)} failures={trace_failures} "
        "privacy_sentinel_absent=true cleanup=passed"
    )
