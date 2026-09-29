import importlib.util
import json
from pathlib import Path

import pytest

from coderoute.evaluation import case_fingerprint
from coderoute.state import TestResult as Result


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("resume_evaluation", ROOT / "scripts" / "resume_evaluation.py")
resume_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(resume_module)


def experiment(tmp_path, monkeypatch):
    case = ROOT / "benchmarks" / "02_zero_bound"
    output = tmp_path / "evaluation"
    output.mkdir()
    (output / "experiment.json").write_text(json.dumps({"config": {}, "cases": {case.name: case_fingerprint(case)},
        "workflows": ["fixed"], "repeats": 1}))
    class NoPaidRun:
        def run(self, *args):
            pytest.fail("Completed model calls must not be repeated")
    monkeypatch.setattr(resume_module, "build_harness", lambda *args: NoPaidRun())
    monkeypatch.setattr(resume_module, "load_local_env", lambda *args: None)
    return output, case


def test_completed_rows_are_not_repeated(tmp_path, monkeypatch):
    output, case = experiment(tmp_path, monkeypatch)
    rows = [{"case": case.name, "workflow": "fixed", "repeat": 1, "success": True}]
    (output / "results.json").write_text(json.dumps(rows))
    assert resume_module.resume(output, ROOT / "benchmarks") == 0
    assert json.loads((output / "results.json").read_text()) == rows


def test_finished_repair_recovers_only_acceptance(tmp_path, monkeypatch):
    output, case = experiment(tmp_path, monkeypatch)
    run = output / (case.name + "-fixed-r1")
    (run / "workspace").mkdir(parents=True)
    (run / "acceptance_run").mkdir()
    (run / "final_state.json").write_text(json.dumps({"workspace": str(run / "workspace"),
        "status": "succeeded", "stop_reason": "accepted"}))
    (run / "metrics.json").write_text(json.dumps({"llm_calls": 12}))
    targets = []
    def acceptance(source, case, target, config):
        targets.append(target)
        return Result("passed", "revision", passed=5)
    monkeypatch.setattr(resume_module, "acceptance", acceptance)
    assert resume_module.resume(output, ROOT / "benchmarks") == 0
    assert len(targets) == 1 and targets[0].name.startswith("acceptance_resume-")
    row = json.loads((output / "results.json").read_text())[0]
    assert row["success"] and row["llm_calls"] == 12


def test_unfinished_repair_is_not_silently_rerun(tmp_path, monkeypatch):
    output, case = experiment(tmp_path, monkeypatch)
    (output / (case.name + "-fixed-r1")).mkdir()
    with pytest.raises(ValueError, match="Incomplete repair artifacts"):
        resume_module.resume(output, ROOT / "benchmarks")
