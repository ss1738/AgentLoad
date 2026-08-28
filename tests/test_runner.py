from agentload.config import Assertions, Scenario
from agentload.runner import _trace
from agentload.trace import FailureCategory

SCENARIO = Scenario("test", "/agent", [1], 1, 1, .9, [{"prompt": "secret prompt"}], Assertions("success", True, max_cost_usd=.1, max_loop_depth=2, max_latency_ms=10))

class Response:
    def __init__(self, status_code): self.status_code = status_code

def test_transport_error_creates_immutable_failure_trace():
    trace = _trace(1, None, None, 3, SCENARIO, TimeoutError("Authorization: token\nsecret"))
    assert not trace.task_success
    assert trace.failure_category is FailureCategory.TIMEOUT
    assert "\n" not in trace.error_message
    assert "secret prompt" not in trace.as_dict().__str__()

def test_connection_unknown_and_http_paths_create_one_failure_trace():
    cases = [(ConnectionError("offline"), FailureCategory.CONNECTION_ERROR), (RuntimeError(), FailureCategory.UNKNOWN_ERROR), (None, FailureCategory.HTTP_429), (None, FailureCategory.HTTP_4XX), (None, FailureCategory.HTTP_5XX)]
    for index, (error, category) in enumerate(cases):
        status = [None, None, 429, 404, 500][index]
        trace = _trace(1, Response(status) if status else None, None, 1, SCENARIO, error)
        assert trace.failure_category is category and not trace.task_success

def test_runner_trace_uses_shared_classification_for_json_and_limits():
    assert _trace(1, Response(200), {"success": True}, 1, SCENARIO).failure_category is FailureCategory.SUCCESS
    assert _trace(1, Response(200), None, 1, SCENARIO).failure_category is FailureCategory.INVALID_JSON
    assert _trace(1, Response(200), {"success": False}, 1, SCENARIO).failure_category is FailureCategory.SUCCESS_ASSERTION_FAILED
    assert _trace(1, Response(200), {"success": True, "estimated_cost_usd": .2}, 1, SCENARIO).failure_category is FailureCategory.COST_LIMIT_EXCEEDED
    assert _trace(1, Response(200), {"success": True, "loop_depth": 3}, 1, SCENARIO).failure_category is FailureCategory.LOOP_LIMIT_EXCEEDED
    assert _trace(1, Response(200), {"success": True}, 11, SCENARIO).failure_category is FailureCategory.LATENCY_LIMIT_EXCEEDED
