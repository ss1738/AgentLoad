# AgentLoad

AgentLoad answers: **at what concurrent-user level does an HTTP AI agent’s deterministic task-success rate fall below a required threshold?** It uses Locust for HTTP load generation and records auditable JSONL traces.

## Scope

Version 0.1 validates HTTP status, a required JSON field/value, cost, loop depth, expected tool call, and latency. It deliberately does not run an LLM judge during a load test; that would contaminate the measurement. Offline semantic evaluation can be added from the retained traces.

## Install and quick start

```bash
python3 -m pip install -e '.[demo]'
python3 -m uvicorn examples.mock_agent:app --port 8000
agentload run examples/scenario.yaml --host http://localhost:8000 --output agentload-results
```

`examples/mock_agent.py` is a labelled deterministic simulator, not a real AI agent. The command writes `traces.jsonl`, stable `report.json`, and a Markdown table in `report.md`. Add `--fail-on-threshold` for CI to exit 2 when a breaking point is measured.

## Scenario reference

`name`, `endpoint`, `concurrency` (positive integer list), `duration_seconds`, `spawn_rate`, `success_threshold` (0–1), task `prompt`s, and assertions are required. Assertions require `success_field` and `required_value`; optional keys are `max_cost_usd`, `max_loop_depth`, `expected_tool_call`, and `max_latency_ms`.

## Expected response

Your agent should return JSON such as:

```json
{"success": true, "input_tokens": 120, "output_tokens": 60, "estimated_cost_usd": 0.003, "tool_calls": ["lookup"], "loop_depth": 1}
```

Missing or malformed responses remain in the trace as failed tasks; they are not discarded.

## CLI

```bash
agentload run SCENARIO --host BASE_URL --output DIRECTORY
agentload analyze DIRECTORY/traces.jsonl --threshold 0.90 --output DIRECTORY
```

The report includes attempted tasks, success rate, throughput, p50/p95 latency, tokens, costs, 429 and timeout rates, maximum loop depth, and the first tested breaking point. To test a real agent, point `--host` and `endpoint` at its isolated test deployment, ensure it exposes the response fields above, then tune duration/ramp-up to its normal traffic profile.

## Limitations

The results measure only the supplied prompts and deterministic response assertions. They do not prove correctness beyond them, replace security testing, or predict untested concurrency levels.
