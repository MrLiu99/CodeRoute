import json
from pathlib import Path

import pytest

from coderoute.config import Config
from coderoute.models.client import ModelReply
from coderoute.models.multi_demo import MultiDemoClient
from coderoute.multi_harness import MultiAgentHarness
from coderoute.routers.base import RouteDecision
from coderoute.routers.llm import LLMRouter, RuleLLMRouter
from coderoute.routers.rules import RuleGate
from coderoute.routers.summary import StateSummarizer
from coderoute.state import RepairState, TestResult as Result


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_repo"


def state():
    return RepairState("issue", "source", "work", "mock", revision="a")


def analyzed():
    s = state()
    s.analysis = {"hypothesis": "blank input", "confidence": 0.8}
    s.current_agent = "analyzer"
    return s


@pytest.mark.parametrize("router,expected_calls,expected_rules", [
    (RuleLLMRouter, 3, 4), (LLMRouter, 7, 0)])
def test_routing_real_tools_and_separate_accounting(tmp_path, router, expected_calls, expected_rules):
    root = tmp_path / "run"
    s = MultiAgentHarness(Config(), MultiDemoClient(), router()).run(DEMO, "blank input", root)
    assert s.status == "succeeded", s.stop_reason
    assert s.history == ["analyzer", "developer", "tester", "debugger", "developer", "tester", "reviewer"]
    metrics = json.loads((root / "metrics.json").read_text())
    assert metrics["router_model_calls"] == expected_calls
    assert metrics["rule_decisions"] == expected_rules
    assert metrics["agent_model_calls"] == 9
    assert metrics["model_calls"] == expected_calls + 9
    assert metrics["llm_calls"] == 0


def test_rule_gate_forces_test_and_review():
    s = analyzed()
    s.current_agent = "developer"
    assert RuleGate().allowed(s)[0] == ("tester",)
    s.current_agent = "tester"
    s.test_result = Result("passed", "a", passed=1)
    assert RuleGate().allowed(s)[0] == ("reviewer",)
    s.review = {"accepted": False}
    s.review_revision = "a"
    assert RuleGate().allowed(s)[0] == ("analyzer", "developer")
    s.review = {"accepted": True}
    assert RuleGate().allowed(s)[0] == ("finish",)
    s.update_revision("b")
    assert "finish" not in RuleGate().allowed(s)[0]
    assert "reviewer" not in RuleGate().allowed(s)[0]


def test_dynamic_singleton_does_not_query():
    def forbidden(messages):
        pytest.fail("Deterministic gate should not query the model")
    assert RuleLLMRouter().route(state(), forbidden).choice == "analyzer"


@pytest.mark.parametrize("body", [
    'not JSON',
    '{"choice":"finish","confidence":0.9,"reason":"skip verification"}',
    '{"choice":"developer","confidence":true,"reason":"invalid"}',
    '{"choice":"developer","confidence":NaN,"reason":"invalid"}',
    '{"choice":"developer","confidence":0.9,"reason":""}',
    '{"choice":"developer","confidence":0.9,"reason":"valid","extra":1}',
])
def test_router_rejects_bad_output(body):
    with pytest.raises(ValueError):
        LLMRouter().route(analyzed(), lambda messages: ModelReply(body))


def test_model_can_choose_reanalysis_over_agent_recommendation():
    s = analyzed()
    s.current_agent = "debugger"
    s.debug_feedback = {"recommended_next_agent": "developer", "reason": "uncertain location"}
    result = RuleLLMRouter().route(s, lambda messages: ModelReply(json.dumps({
        "choice": "analyzer", "confidence": 0.7, "reason": "Location is not supported by evidence"})))
    assert result.choice == "analyzer"
    assert result.source == "llm"


def test_router_uses_shared_budget(tmp_path):
    root = tmp_path / "run"
    s = MultiAgentHarness(Config(max_model_calls=2), MultiDemoClient(), RuleLLMRouter()).run(DEMO, "issue", root)
    assert s.status == "budget_exhausted"
    assert s.history == ["analyzer"]
    metrics = json.loads((root / "metrics.json").read_text())
    assert metrics["model_calls"] == 2
    assert metrics["router_model_calls"] == 0


def test_invalid_model_decision_is_logged_and_never_executed(tmp_path):
    class BadRouterClient(MultiDemoClient):
        def complete(self, messages, timeout):
            if messages[0]["content"].startswith("You are CodeRoute's runtime router."):
                return ModelReply('{"choice":"finish","confidence":0.99,"reason":"skip"}',
                                  {"prompt_tokens": 10, "completion_tokens": 5}, "fake-router")
            return super().complete(messages, timeout)
    root = tmp_path / "run"
    s = MultiAgentHarness(Config(), BadRouterClient(), RuleLLMRouter()).run(DEMO, "issue", root)
    assert s.status == "execution_error"
    assert s.history == ["analyzer"]
    events = json.loads((root / "trajectory.json").read_text())
    assert any(e["event"] == "model_response" and e["category"] == "router" for e in events)
    metrics = json.loads((root / "metrics.json").read_text())
    assert metrics["router_input_tokens"] == 10
    assert metrics["router_output_tokens"] == 5
    assert metrics["input_tokens"] == 10


def test_summary_is_bounded_and_excludes_diff():
    s = analyzed()
    s.issue = "x" * 100000
    s.analysis["hypothesis"] = "y" * 100000
    summary = StateSummarizer().summarize(s, ("analyzer", "developer"), "reason")
    assert len(summary["issue"]) == 2000
    assert len(summary["hypothesis"]) == 1500
    assert "diff" not in summary


def test_harness_rechecks_custom_router_permissions(tmp_path):
    class BadRouter:
        def route(self, state, query=None):
            return RouteDecision("developer", "custom", "skip initial analysis")
    s = MultiAgentHarness(Config(), MultiDemoClient(), BadRouter()).run(DEMO, "issue", tmp_path / "run")
    assert s.status == "execution_error"
    assert s.steps == 0
    assert s.modified_files == []
