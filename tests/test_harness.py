import json
import subprocess
import sys
from pathlib import Path

import pytest

from coderoute.config import Config
from coderoute.harness import RepairHarness
from coderoute.models.client import DemoClient, ModelReply
from coderoute.state import RepairState, TestResult as Result
from coderoute.tools.files import FileTools
from coderoute.tools.pytest_runner import run_tests
from coderoute.tools.workspace import Workspace


DEMO = Path(__file__).resolve().parents[1] / "examples" / "demo_repo"


def test_demo_runs_real_tests_and_preserves_source(tmp_path):
    original = (DEMO / "config_reader.py").read_bytes()
    run = tmp_path / "run"
    state = RepairHarness(Config(), DemoClient()).run(DEMO, "Handle blank configuration", run)
    assert state.status == "succeeded", state.stop_reason
    assert state.test_result.passed == 5
    assert state.modified_files == ["config_reader.py"]
    assert (DEMO / "config_reader.py").read_bytes() == original
    events = json.loads((run / "trajectory.json").read_text())
    results = [e["result"]["status"] for e in events if e.get("action", {}).get("tool") == "run_test"]
    assert results == ["failed", "failed", "passed"]
    assert "if not text.strip():" in (run / "final.diff").read_text()
    metrics = json.loads((run / "metrics.json").read_text())
    assert metrics["llm_calls"] == 0
    assert metrics["mock_calls"] == 9
    assert metrics["failed_test_runs"] == 2


def test_revision_invalidates_verification():
    state = RepairState("issue", "source", "work", "mock", revision="a")
    state.test_result = Result("passed", "a", passed=1)
    assert state.verified()
    state.update_revision("b")
    assert state.test_result is None
    assert not state.verified()


def test_tools_reject_escape_and_test_modification(tmp_path):
    workspace = Workspace(DEMO, tmp_path / "run")
    tools = FileTools(workspace)
    for name in ("../outside.py", str(tmp_path / "outside.py"), ".git/config", ".env"):
        with pytest.raises(ValueError):
            tools.read_file(name)
    with pytest.raises(ValueError):
        tools.edit_file("tests/test_config_reader.py", "assert", "pass #")
    with pytest.raises(ValueError):
        tools.edit_file("config_reader.py", "not present", "replacement")


class ScriptClient:
    mode = "mock"

    def __init__(self, actions):
        self.actions = iter(actions)

    def complete(self, messages, timeout):
        return ModelReply(next(self.actions), model="test-script")


def action(tool, **args):
    return json.dumps({"tool": tool, "args": args})


def test_cannot_finish_without_tests_and_stops_loop(tmp_path):
    client = ScriptClient([action("finish", summary="done")] * 3)
    state = RepairHarness(Config(), client).run(DEMO, "issue", tmp_path / "run")
    assert state.status == "stalled"
    assert state.steps == 3


def test_malformed_json_is_recoverable_and_budget_is_enforced(tmp_path):
    client = ScriptClient(["not json", action("read_file", path="config_reader.py")])
    state = RepairHarness(Config(max_steps=2), client).run(DEMO, "issue", tmp_path / "run")
    assert state.status == "budget_exhausted"
    events = json.loads((tmp_path / "run" / "trajectory.json").read_text())
    assert "error" in events[0]["result"]
    assert "content" in events[1]["result"]


def make_workspace(tmp_path, text):
    source = tmp_path / "source"
    source.mkdir()
    if text is not None:
        (source / "test_sample.py").write_text(text)
    return Workspace(source, tmp_path / "run")


@pytest.mark.parametrize("text,expected", [
    (None, "no_tests"),
    ("def test_bad(:\n pass", "collection_or_fixture_error"),
    ("import pytest\n@pytest.mark.skip\ndef test_skip(): pass", "no_tests"),
])
def test_test_runner_does_not_confuse_errors_with_success(tmp_path, text, expected):
    workspace = make_workspace(tmp_path, text)
    result = run_tests(workspace, tmp_path / "run", 1, 20)
    assert result.status == expected, result.summary


def test_test_timeout(tmp_path):
    workspace = make_workspace(tmp_path, "import time\ndef test_wait(): time.sleep(30)")
    result = run_tests(workspace, tmp_path / "run", 1, 1)
    assert result.status == "timeout"


def test_test_that_changes_workspace_cannot_verify_it(tmp_path):
    workspace = make_workspace(tmp_path,
        "from pathlib import Path\ndef test_write(): Path('generated.py').write_text('x=1')")
    result = run_tests(workspace, tmp_path / "run", 1, 20)
    assert result.status == "workspace_changed_during_test"


def test_diff_includes_new_files(tmp_path):
    workspace = Workspace(DEMO, tmp_path / "run")
    (workspace.root / "new_file.py").write_text("value = 1\n")
    assert "+value = 1" in workspace.diff()
    assert "new_file.py" in workspace.modified_files()


def test_api_failure_still_saves_artifacts(tmp_path):
    class FailingClient:
        mode = "live"

        def complete(self, messages, timeout):
            raise RuntimeError("Model API returned HTTP 401")

    run = tmp_path / "run"
    state = RepairHarness(Config(), FailingClient()).run(DEMO, "issue", run)
    assert state.status == "execution_error"
    assert (run / "final_state.json").exists()
    assert json.loads((run / "metrics.json").read_text())["llm_calls"] == 1


def test_output_inside_source_is_rejected(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with pytest.raises(ValueError, match="outside"):
        Workspace(source, source / "runs" / "example")


def test_cli_with_nonexistent_relative_output(tmp_path):
    main = Path(__file__).resolve().parents[1] / "main.py"
    process = subprocess.run([sys.executable, str(main), "--repo", str(DEMO),
        "--issue", "Fix blank configuration", "--mode", "mock", "--output", "new-output"],
        cwd=str(tmp_path), capture_output=True, text=True, timeout=60)
    assert process.returncode == 0, process.stdout + process.stderr
    result = json.loads(process.stdout)
    assert Path(result["artifacts"]).is_absolute()
    assert (Path(result["artifacts"]) / "pytest-003.xml").is_file()


def test_passing_test_becomes_stale_after_edit(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "module.py").write_text("value = 1\n")
    (source / "test_module.py").write_text("from module import value\ndef test_value(): assert value == 1\n")
    client = ScriptClient([
        action("run_test"),
        action("edit_file", path="module.py", old="value = 1", new="value = 2"),
        action("finish", summary="done"),
    ])
    state = RepairHarness(Config(max_steps=3), client).run(source, "issue", tmp_path / "run")
    assert state.status == "budget_exhausted"
    assert state.test_result is None


def test_multiline_edit_preserves_windows_newlines(tmp_path):
    work = Workspace(DEMO, tmp_path / "run")
    path = work.root / "windows.py"
    path.write_bytes(b"def value():\r\n    return 1\r\n")
    tools = FileTools(work)
    snippet = tools.read_file("windows.py")["content"]
    tools.edit_file("windows.py", snippet, "def value():\n    return 2\n")
    assert path.read_bytes() == b"def value():\r\n    return 2\r\n"
