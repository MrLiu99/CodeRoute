import json
from pathlib import Path

import pytest

from coderoute.agents.roles import validate_result
from coderoute.config import Config
from coderoute.context import ContextBuilder
from coderoute.models.client import ModelReply
from coderoute.models.multi_demo import MultiDemoClient
from coderoute.multi_harness import MultiAgentHarness
from coderoute.routers.base import RouteDecision
from coderoute.state import RepairState, TestResult as Result
from coderoute.tools.workspace import Workspace


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_repo"
ANALYSIS = {"suspected_files": ["config_reader.py"], "hypothesis": "blank JSON", "confidence": 0.9,
            "requirement_plan": [{"id": "R1", "check": "Check blank inputs"}]}
REVIEW = {"accepted": True, "risk_level": "low", "reason": "focused fix",
          "requirement_checks": [{"id": "R1", "status": "met", "reason": "Blank strings yield an empty mapping",
                                  "evidence": [{"path": "config_reader.py", "quote": "return {}"}]}],
          "recommended_next_agent": "developer", "confidence": 0.9}


class Script:
    mode = "mock"

    def __init__(self, actions):
        self.actions = iter(actions)

    def complete(self, messages, timeout):
        tool, args = next(self.actions)
        return ModelReply(json.dumps({"tool": tool, "args": args}), model="test-script")


def test_multi_demo_real_retry_and_review(tmp_path):
    original = (DEMO / "config_reader.py").read_bytes()
    root = tmp_path / "run"
    state = MultiAgentHarness(Config(), MultiDemoClient()).run(DEMO, "blank input", root)
    assert state.status == "succeeded", state.stop_reason
    assert state.accepted()
    assert state.history == ["analyzer", "developer", "tester", "debugger", "developer", "tester", "reviewer"]
    assert state.test_result.passed == 5
    assert (DEMO / "config_reader.py").read_bytes() == original
    metrics = json.loads((root / "metrics.json").read_text())
    assert metrics["llm_calls"] == 0
    assert metrics["failed_test_runs"] == 1
    assert metrics["agent_calls"]["tester"] == 2


def test_reanalysis_and_rejected_review_require_new_tests(tmp_path):
    actions = [
        ("submit", ANALYSIS),
        ("submit", {"change_summary": "No change yet"}),
        ("submit", {"failure_type": "incorrect_hypothesis", "reason": "Recheck blank handling",
                    "recommended_next_agent": "analyzer", "confidence": 0.8}),
        ("submit", ANALYSIS),
        ("edit_file", {"path": "config_reader.py", "old": "    return json.loads(text)",
                       "new": "    if not text.strip():\n        return {}\n    return json.loads(text)"}),
        ("submit", {"change_summary": "Handle blank text"}),
        ("submit", dict(REVIEW, accepted=False, reason="Use explicit blank comparison")),
        ("edit_file", {"path": "config_reader.py", "old": "if not text.strip():",
                       "new": 'if text.strip() == "":'}),
        ("submit", {"change_summary": "Explicit comparison"}),
        ("submit", REVIEW),
    ]
    root = tmp_path / "run"
    state = MultiAgentHarness(Config(), Script(actions)).run(DEMO, "blank input", root)
    assert state.status == "succeeded", state.stop_reason
    assert state.history == ["analyzer", "developer", "tester", "debugger", "analyzer", "developer",
                             "tester", "reviewer", "developer", "tester", "reviewer"]
    events = json.loads((root / "trajectory.json").read_text())
    devs = [e for e in events if e["event"] == "role_complete" and e["agent"] == "developer"]
    assert devs[-1]["state_after"]["review"] == {}
    assert devs[-1]["state_after"]["test_result"] is None
    assert state.review_revision == state.test_result.revision == state.revision


def test_analyzer_cannot_edit_or_run_tests(tmp_path):
    actions = [("edit_file", {"path": "config_reader.py", "old": "json.loads(text)", "new": "{}"}),
               ("run_test", {}), ("submit", ANALYSIS)]
    root = tmp_path / "run"
    state = MultiAgentHarness(Config(max_steps=1), Script(actions)).run(DEMO, "issue", root)
    assert state.status == "budget_exhausted"
    assert state.modified_files == []
    events = json.loads((root / "trajectory.json").read_text())
    errors = [e["result"]["error"] for e in events if e["event"] == "role_turn" and "error" in e["result"]]
    assert errors == ["analyzer cannot use edit_file", "analyzer cannot use run_test"]


def test_role_and_global_model_budgets(tmp_path):
    for index, config in enumerate((Config(max_role_turns=1), Config(max_model_calls=1))):
        client = Script([("read_file", {"path": "config_reader.py"})] * 2)
        root = tmp_path / str(index)
        state = MultiAgentHarness(config, client).run(DEMO, "issue", root)
        assert state.status == "budget_exhausted"
        assert json.loads((root / "metrics.json").read_text())["model_calls"] == 1


def test_review_invalidation():
    state = RepairState("issue", "source", "work", "mock", revision="a")
    state.test_result = Result("passed", "a", passed=1)
    state.review = REVIEW
    state.review_revision = "a"
    assert state.accepted()
    state.update_revision("b")
    assert not state.accepted()
    assert state.review == {}


@pytest.mark.parametrize("override", [{"accepted": "true"}, {"confidence": float("nan")},
                                      {"recommended_next_agent": "finish"}])
def test_review_schema_validation(override):
    with pytest.raises(ValueError):
        validate_result("reviewer", dict(REVIEW, **override))


def test_bad_router_cannot_skip_verification(tmp_path):
    class Router:
        def route(self, state, query=None):
            return RouteDecision("finish", "test", "Invalid early finish")
    state = MultiAgentHarness(Config(), Script([]), Router()).run(DEMO, "issue", tmp_path / "run")
    assert state.status == "execution_error"
    assert "Finish rejected" in state.stop_reason


def test_role_specific_context(tmp_path):
    workspace = Workspace(DEMO, tmp_path / "run")
    builder = ContextBuilder(workspace, 12000)
    state = RepairState("issue", "source", str(workspace.root), "mock")
    assert "repository_files" in builder.build("analyzer", state)
    assert "test_result" not in builder.build("analyzer", state)
    assert "diff" in builder.build("developer", state)
    assert "test_result" in builder.build("debugger", state)
    assert "patch_summary" in builder.build("reviewer", state)
