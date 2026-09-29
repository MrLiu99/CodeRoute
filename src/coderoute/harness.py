import json
import time
from dataclasses import asdict
from pathlib import Path

from .agents.base import RoleAgent
from .state import RepairState
from .tools.files import FileTools
from .tools.pytest_runner import run_tests
from .tools.workspace import Workspace, files
from .tracing import Tracer


class RepairHarness:
    def __init__(self, config, client):
        self.config = config
        self.client = client

    def run(self, repo, issue, run_dir):
        started = time.monotonic()
        root = Path(run_dir).absolute().resolve()
        root.mkdir(parents=True, exist_ok=False)
        tracer = Tracer(root)
        state = RepairState(issue, str(Path(repo).resolve()), "", self.client.mode)
        metrics = {"mode": self.client.mode, "model_calls": 0, "llm_calls": 0,
                   "mock_calls": 0, "input_tokens": 0, "output_tokens": 0,
                   "usage_missing_calls": 0, "test_runs": 0, "failed_test_runs": 0,
                   "tool_calls": 0, "api_models": []}
        workspace = None
        try:
            workspace = Workspace(repo, root)
            state.workspace = str(workspace.root)
            state.update_revision(workspace.revision())
            file_tools = FileTools(workspace, self.config.max_output_chars)
            tree = [p.relative_to(workspace.root).as_posix() for p in files(workspace.root)]
            agent = RoleAgent(self.client, issue, tree)
            tracer.save("initial_messages.json", agent.messages)
            unchanged = 0
            previous_signature = None
            while state.steps < self.config.max_steps:
                remaining = self.config.wall_timeout - (time.monotonic() - started)
                if remaining <= 0 or agent.context_size() > self.config.max_context_chars:
                    state.status = "budget_exhausted"
                    state.stop_reason = "Wall time or context budget reached"
                    break
                state.steps += 1
                step_start = time.monotonic()
                before = asdict(state)
                metrics["model_calls"] += 1
                metrics["mock_calls" if state.mode == "mock" else "llm_calls"] += 1
                reply = agent.next(min(self.config.model_timeout, remaining))
                if reply.model not in metrics["api_models"]:
                    metrics["api_models"].append(reply.model)
                usage = reply.usage
                metrics["input_tokens"] += usage.get("prompt_tokens", 0)
                metrics["output_tokens"] += usage.get("completion_tokens", 0)
                if not usage:
                    metrics["usage_missing_calls"] += 1
                if reply.response_error():
                    metrics.setdefault("response_errors", {})[reply.response_error()] = 1
                    tracer.record({"event": "model_response", "step": state.steps,
                                   "model": reply.model, "content": reply.content, "usage": usage,
                                   "finish_reason": reply.finish_reason, "response_error": reply.response_error()})
                reply.require_complete()
                action = None
                try:
                    action = agent.parse(reply.content)
                    tool, args = action["tool"], action["args"]
                    remaining = self.config.wall_timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        state.status = "budget_exhausted"
                        state.stop_reason = "Wall time reached after model call"
                        result = {"error": state.stop_reason}
                    elif tool in {"read_file", "search_code", "edit_file"}:
                        metrics["tool_calls"] += 1
                        result = getattr(file_tools, tool)(**args)
                        state.update_revision(workspace.revision())
                    elif tool == "run_test" and not args:
                        metrics["tool_calls"] += 1
                        metrics["test_runs"] += 1
                        state.test_result = run_tests(workspace, root, metrics["test_runs"],
                            min(self.config.test_timeout, remaining), self.config.max_output_chars)
                        result = asdict(state.test_result)
                        if state.test_result.status != "passed":
                            metrics["failed_test_runs"] += 1
                        state.update_revision(workspace.revision())
                    elif tool == "git_diff" and not args:
                        metrics["tool_calls"] += 1
                        diff = workspace.diff()
                        result = {"diff": diff[:self.config.max_output_chars],
                                  "truncated": len(diff) > self.config.max_output_chars}
                    elif tool == "finish" and set(args) == {"summary"} and isinstance(args["summary"], str):
                        state.update_revision(workspace.revision())
                        if not state.verified():
                            raise ValueError("Cannot finish: current code has no passing test evidence")
                        state.status = "succeeded"
                        state.stop_reason = args["summary"]
                        result = {"accepted": True, "scope": "stage_one_tests_only"}
                    else:
                        raise ValueError("Unknown tool or invalid arguments")
                except (ValueError, TypeError, OSError) as error:
                    result = {"error": str(error)}
                agent.observe(result)
                tracer.record({"step": state.steps, "agent": "single_coder",
                               "state_before": before, "model_content": reply.content,
                               "model": reply.model, "action": action, "result": result,
                               "finish_reason": reply.finish_reason,
                               "usage": usage, "state_after": asdict(state),
                               "latency_seconds": time.monotonic() - step_start})
                if state.status != "running":
                    break
                signature = json.dumps([action, result, state.revision], sort_keys=True)
                unchanged = unchanged + 1 if signature == previous_signature else 0
                previous_signature = signature
                if unchanged >= 2:
                    state.status = "stalled"
                    state.stop_reason = "Same action and observation repeated three times"
                    break
            if state.status == "running":
                state.status = "budget_exhausted"
                state.stop_reason = "Maximum tool turns reached"
        except Exception as error:
            state.status = "execution_error"
            state.stop_reason = f"{type(error).__name__}: {error}"
            tracer.record({"step": state.steps, "error": state.stop_reason})
        finally:
            if workspace is not None:
                try:
                    state.update_revision(workspace.revision())
                    state.modified_files = workspace.modified_files()
                    (root / "final.diff").write_text(workspace.diff(), encoding="utf-8")
                    if state.status == "succeeded" and not state.verified():
                        state.status = "execution_error"
                        state.stop_reason = "Verification became stale during finalization"
                except Exception as error:
                    state.status = "execution_error"
                    state.stop_reason = f"Finalization failed: {error}"
            metrics.update({"status": state.status, "success": state.status == "succeeded",
                            "success_scope": "stage_one_tests_only", "steps": state.steps,
                            "latency_seconds": time.monotonic() - started})
            tracer.save("final_state.json", state)
            tracer.save("metrics.json", metrics)
            tracer.save("trajectory.json", tracer.events)
        return state
