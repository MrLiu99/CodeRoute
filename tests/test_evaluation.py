import json
from pathlib import Path

import pytest

from coderoute.config import Config
from coderoute.evaluation import case_fingerprint, evaluate, main, summarize, validate_cases
from coderoute.state import RepairState
from coderoute.tools.files import FileTools
from coderoute.tools.pytest_runner import run_tests
from coderoute.tools.workspace import Workspace


BENCHMARKS = Path(__file__).resolve().parents[1] / "benchmarks"


def test_reference_validation_and_source_preservation(tmp_path):
    case = BENCHMARKS / "08_weighted_mean"
    before = case_fingerprint(case)
    result = validate_cases([case], tmp_path, Config())
    assert result[0]["valid"]
    assert result[0]["reference_tests"] == 5
    assert before == case_fingerprint(case)


def test_holdout_catches_public_test_only_fix(tmp_path, monkeypatch):
    class PublicOnlyHarness:
        def run(self, repo, issue, root):
            root.mkdir()
            work = Workspace(repo, root)
            assert not (work.root / "tests" / "acceptance").exists()
            FileTools(work).edit_file("bounds.py", "if lower and", "if lower is not None and")
            test = run_tests(work, root, 1, 20)
            assert test.status == "passed"
            state = RepairState(issue, str(repo), str(work.root), "live", revision=work.revision(), status="succeeded")
            state.test_result = test
            state.review = {"accepted": True}
            state.review_revision = state.revision
            (root / "metrics.json").write_text(json.dumps({"steps": 4, "llm_calls": 1}))
            return state
    monkeypatch.setattr("coderoute.evaluation.build_harness", lambda *args: PublicOnlyHarness())
    rows = evaluate([BENCHMARKS / "02_zero_bound"], ["fixed"], 1, tmp_path, Config())
    assert rows[0]["status"] == "succeeded"
    assert rows[0]["acceptance_status"] == "failed"
    assert rows[0]["success"] is False
    assert rows[0]["source_unchanged"]
    assert "0/1" in (tmp_path / "report.md").read_text()
    assert not (Path(rows[0]["artifacts"]) / "workspace" / "tests" / "acceptance").exists()


def test_summary_keeps_failures_in_denominator():
    base = {"workflow": "hybrid", "steps": 4, "llm_calls": 12, "router_model_calls": 1,
            "lightweight_model_calls": 2, "llm_escalations": 1,
            "input_tokens": 100, "output_tokens": 20, "latency_seconds": 5}
    summary = summarize([dict(base, success=True), dict(base, success=False)])
    assert summary[0]["runs"] == 2
    assert summary[0]["success_rate"] == 0.5


def test_live_batch_limit_blocks_before_model_construction(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("coderoute.evaluation.build_harness", lambda *args: pytest.fail("No model may be constructed"))
    with pytest.raises(SystemExit) as error:
        main(["--benchmarks", str(BENCHMARKS), "--live"])
    assert error.value.code == 2
