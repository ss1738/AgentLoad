import pytest
from agentload.classify import classify
from agentload.config import Assertions
from agentload.trace import FailureCategory

A = Assertions("success", True, max_loop_depth=2, max_cost_usd=.1, max_latency_ms=10)
@pytest.mark.parametrize(("status","payload","latency","expected"), [(429, {}, 1, FailureCategory.HTTP_429), (404, {}, 1, FailureCategory.HTTP_4XX), (500, {}, 1, FailureCategory.HTTP_5XX), (200, None, 1, FailureCategory.INVALID_JSON), (200, {"success":False}, 1, FailureCategory.SUCCESS_ASSERTION_FAILED), (200, {"success":True,"estimated_cost_usd":.2}, 1, FailureCategory.COST_LIMIT_EXCEEDED), (200, {"success":True,"loop_depth":3}, 1, FailureCategory.LOOP_LIMIT_EXCEEDED), (200, {"success":True}, 11, FailureCategory.LATENCY_LIMIT_EXCEEDED), (200, {"success":True}, 1, FailureCategory.SUCCESS)])
def test_classification_precedence(status, payload, latency, expected):
    assert classify(status, payload, A, latency)[0] is expected
def test_transport_error_is_sanitized():
    category, message = classify(None, None, A, 0, TimeoutError("token=secret\nnext"))
    assert category is FailureCategory.TIMEOUT and "\n" not in message and len(message) <= 240
