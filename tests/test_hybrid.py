import json
from pathlib import Path

import pytest

from coderoute.config import Config
from coderoute.models.client import ModelReply
from coderoute.models.lightweight_demo import LightweightDemoClient
from coderoute.models.multi_demo import MultiDemoClient
from coderoute.multi_harness import BudgetExceeded, MultiAgentHarness
from coderoute.routers.hybrid import HybridRouter
from coderoute.state import RepairState


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_repo"


def analyzed():
    s = RepairState("issue", "source", "work", "mock", revision="a")
    s.analysis = {"hypothesis": "blank input", "confidence": 0.8}
    s.current_agent = "analyzer"
    return s


def reply(confidence=0.9, choice="developer"):
    return ModelReply(json.dumps({"choice": choice, "confidence": confidence, "reason": "evidence"}),
                      {"prompt_tokens": 10, "completion_tokens": 5}, "test-model")


@pytest.mark.parametrize("confidence,tiers,source", [
    (0.9, ["lightweight"], "lightweight"),
    (0.65, ["lightweight"], "lightweight"),
    (0.64, ["lightweight", "strong"], "llm"),
])
def test_threshold_boundary_and_call_order(confidence, tiers, source):
    calls = []
    def query(messages, tier):
        calls.append(tier)
        return reply(confidence if tier == "lightweight" else 0.9)
    decision = HybridRouter().route(analyzed(), query)
    assert calls == tiers
    assert decision.source == source
    assert decision.escalation_reason == ("low_confidence" if confidence < 0.65 else None)
    assert len(decision.attempts) == len(tiers)


@pytest.mark.parametrize("bad_reply", [ModelReply("not json"), reply(choice="finish"),
                                       reply(float("nan")), reply(True)])
def test_invalid_lightweight_result_escalates(bad_reply):
    calls = []
    def query(messages, tier):
        calls.append(tier)
        return bad_reply if tier == "lightweight" else reply()
    decision = HybridRouter().route(analyzed(), query)
    assert calls == ["lightweight", "strong"]
    assert decision.choice == "developer"
    assert decision.escalation_reason == "lightweight_error"


@pytest.mark.parametrize("error", [RuntimeError("HTTP 503"), TimeoutError("timeout")])
def test_lightweight_transport_failure_escalates(error):
    def query(messages, tier):
        if tier == "lightweight":
            raise error
        return reply()
    assert HybridRouter().route(analyzed(), query).escalation_reason == "lightweight_error"


def test_budget_exhaustion_never_escalates():
    calls = []
    def query(messages, tier):
        calls.append(tier)
        raise BudgetExceeded("No calls left")
    with pytest.raises(BudgetExceeded):
        HybridRouter().route(analyzed(), query)
    assert calls == ["lightweight"]


def test_strong_invalid_output_stops():
    calls = []
    def query(messages, tier):
        calls.append(tier)
        return reply(0.1) if tier == "lightweight" else reply(choice="finish")
    with pytest.raises(ValueError):
        HybridRouter().route(analyzed(), query)
    assert calls == ["lightweight", "strong"]


def test_rule_shortcut_calls_neither_model():
    def query(*args, **kwargs):
        pytest.fail("Rule must skip both model tiers")
    s = analyzed()
    s.current_agent = "developer"
    assert HybridRouter().route(s, query).choice == "tester"


def test_hybrid_end_to_end_with_real_tools_and_escalation(tmp_path):
    class MeteredLight(LightweightDemoClient):
        def complete(self, messages, timeout):
            result = super().complete(messages, timeout)
            result.usage = {"prompt_tokens": 10, "completion_tokens": 5}
            return result
    root = tmp_path / "run"
    s = MultiAgentHarness(Config(), MultiDemoClient(), HybridRouter(), MeteredLight()).run(DEMO, "blank", root)
    assert s.status == "succeeded", s.stop_reason
    assert s.accepted()
    assert s.history == ["analyzer", "developer", "tester", "debugger", "developer", "tester", "reviewer"]
    m = json.loads((root / "metrics.json").read_text())
    assert m["lightweight_model_calls"] == 3
    assert m["lightweight_decisions"] == 2
    assert m["llm_escalations"] == m["router_model_calls"] == 1
    assert m["confidence_threshold"] == 0.65
    assert m["rule_decisions"] == 4
    assert m["model_calls"] == m["mock_calls"] == 13
    assert m["llm_calls"] == 0
    assert m["input_tokens"] == m["lightweight_input_tokens"] == 30
    events = json.loads((root / "trajectory.json").read_text())
    escalated = [e for e in events if e["event"] == "route_decision" and e["decision"]["escalation_reason"]]
    assert len(escalated) == 1
    assert escalated[0]["decision"]["attempts"][0]["confidence"] == 0.4


def test_total_budget_counts_lightweight_before_escalation(tmp_path):
    class LowClient:
        mode = "mock"
        def complete(self, messages, timeout):
            return reply(0.1)
    root = tmp_path / "run"
    s = MultiAgentHarness(Config(max_model_calls=3), MultiDemoClient(), HybridRouter(), LowClient()).run(DEMO, "blank", root)
    assert s.status == "budget_exhausted"
    m = json.loads((root / "metrics.json").read_text())
    assert m["agent_model_calls"] == 2
    assert m["lightweight_model_calls"] == 1
    assert m["router_model_calls"] == m["llm_escalations"] == 0


def test_lightweight_client_required():
    with pytest.raises(ValueError, match="lightweight client"):
        MultiAgentHarness(Config(), MultiDemoClient(), HybridRouter())


@pytest.mark.parametrize("threshold", [-0.1, 1.1, True, "0.65", float("nan")])
def test_invalid_threshold(tmp_path, threshold):
    with pytest.raises(ValueError):
        HybridRouter(threshold)
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"confidence_threshold": threshold}))
    with pytest.raises(ValueError):
        Config.load(path)
