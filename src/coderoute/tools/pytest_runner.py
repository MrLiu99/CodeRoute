import os
import signal
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from ..state import TestResult


def run_tests(workspace, run_dir, number, timeout, output_limit=12000, test_paths=None):
    run_dir = Path(run_dir).absolute().resolve()
    log = run_dir / f"pytest-{number:03d}.log"
    report = run_dir / f"pytest-{number:03d}.xml"
    before = workspace.revision()
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTEST_DISABLE_PLUGIN_AUTOLOAD"] = "1"
    env['PYTHONIOENCODING'] = 'utf-8'
    env.pop("PYTEST_ADDOPTS", None)
    command = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
               "--junitxml=" + str(report)]
    if test_paths:
        command.extend(test_paths)
    with log.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(command, cwd=str(workspace.root), env=env,
                                   stdout=output, stderr=subprocess.STDOUT,
                                   start_new_session=os.name != "nt")
        timed_out = False
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               capture_output=True, timeout=10)
            else:
                os.killpg(process.pid, signal.SIGKILL)
            if process.poll() is None:
                process.kill()
            process.wait(timeout=10)
    # Keep full logs on disk, send only the tail to the agent.
    with log.open("rb") as handle:
        handle.seek(0, 2)
        handle.seek(max(0, handle.tell() - output_limit * 4))
        tail = handle.read().decode("utf-8", errors="replace")[-output_limit:]
    result = TestResult("execution_error", before, returncode=process.returncode,
                        log_path=str(log), summary=tail)
    if timed_out:
        result.status = "timeout"
        return result
    if report.exists():
        try:
            cases = list(ET.parse(report).getroot().iter("testcase"))
            result.failed = sum(c.find("failure") is not None for c in cases)
            result.errors = sum(c.find("error") is not None for c in cases)
            result.skipped = sum(c.find("skipped") is not None for c in cases)
            result.passed = len(cases) - result.failed - result.errors - result.skipped
            if process.returncode == 0 and result.passed > 0 and not (result.failed or result.errors):
                result.status = "passed"
            elif process.returncode == 1 and result.failed:
                result.status = "failed"
            elif process.returncode == 5 or (process.returncode == 0 and not result.passed):
                result.status = "no_tests"
            elif result.errors:
                result.status = "collection_or_fixture_error"
        except ET.ParseError:
            result.status = "invalid_report"
    if workspace.revision() != before:
        result.status = "workspace_changed_during_test"
    return result
