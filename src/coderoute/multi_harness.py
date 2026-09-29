import json
import time
from collections import Counter
from dataclasses import asdict
from pathlib import Path

from .agents.roles import StructuredRoleAgent, validate_result
from .agents.tester import TesterAgent
from .context import ContextBuilder
from .routers.fixed import FixedRouter
from .routers.base import RouteDecision
from .routers.rules import RuleGate
from .state import RepairState
from .tools.files import FileTools
from .tools.workspace import Workspace
from .tracing import Tracer
from .requirements import validate_coverage
from .models.client import ModelResponseError
from .models.functions import role_functions, route_functions
from .agents.roles import SCHEMAS
from .tools.review_checks import ReviewChecks


class BudgetExceeded(Exception):
    pass


class MultiAgentHarness:
    def __init__(self, config, client, router=None, lightweight_client=None):
        self.config = config
        self.client = client
        self.router = router or FixedRouter()
        self.lightweight_client = lightweight_client
        if getattr(self.router, "name", "") == "hybrid" and lightweight_client is None:
            raise ValueError("Hybrid workflow requires an explicitly configured lightweight client")
        self.agent_registry = {role: StructuredRoleAgent for role in
                               ("analyzer", "developer", "debugger", "reviewer")}
        self.agent_registry["tester"] = TesterAgent()

    def remaining(self):
        remaining = self.config.wall_timeout - (time.monotonic() - self.started)
        if remaining <= 0:
            raise BudgetExceeded("Wall time limit reached")
        return remaining

    def query_model(self, messages, category, state, tracer, metrics, functions=None, allow_empty=False):
        remaining = self.remaining()
        if metrics["model_calls"] >= self.config.max_model_calls:
            raise BudgetExceeded("Total model call limit reached")
        if len(json.dumps(messages, ensure_ascii=False)) > self.config.max_context_chars:
            raise BudgetExceeded("Model context limit reached")
        metrics["model_calls"] += 1
        client = self.lightweight_client if category == "lightweight" else self.client
        metrics["mock_calls" if client.mode == "mock" else "llm_calls"] += 1
        metrics[category + "_model_calls"] += 1
        if category == "router" and getattr(self.router, "name", "") == "hybrid":
            metrics["llm_escalations"] += 1
        started = time.monotonic()
        try:
            timeout = self.config.lightweight_timeout if category == "lightweight" else self.config.model_timeout
            if self.config.native_tool_calls and functions and hasattr(client, 'complete_tools'):
                reply = client.complete_tools(messages, min(remaining, timeout), functions, routing=category != 'agent')
            else:
                reply = client.complete(messages, min(remaining, timeout))
        except Exception as error:
            metrics["usage_missing_calls"] += 1
            tracer.record({"event": "model_error", "category": category, "step": state.steps,
                           "error_type": type(error).__name__, "http_status": getattr(error, "status_code", None),
                           "latency_seconds": time.monotonic() - started})
            raise
        if reply.model not in metrics["api_models"]:
            metrics["api_models"].append(reply.model)
        usage = reply.usage
        for field, key in (("input_tokens", "prompt_tokens"), ("output_tokens", "completion_tokens")):
            metrics[field] += usage.get(key, 0)
            metrics[category + "_" + field] += usage.get(key, 0)
        metrics["usage_missing_calls"] += not bool(usage)
        tracer.record({"event": "model_response", "category": category, "step": state.steps,
                       "model": reply.model, "mode": client.mode, "usage": usage, "content": reply.content,
                       "finish_reason": reply.finish_reason, "response_error": reply.response_error(),
                       'tool_calls': reply.tool_calls,
                       "latency_seconds": time.monotonic() - started})
        if reply.response_error():
            errors = metrics.setdefault("response_errors", {})
            errors[reply.response_error()] = errors.get(reply.response_error(), 0) + 1
        if not (allow_empty and reply.response_error() in ('empty_response', 'missing_tool_call', 'multiple_tool_calls')):
            reply.require_complete()
        self.remaining()
        return reply

    def role_context(self, role, state, workspace):
        context = ContextBuilder(workspace, self.config.max_output_chars).build(role, state)
        context["max_role_turns"] = self.config.max_role_turns
        context['native_tool_calls'] = self.config.native_tool_calls
        context['review_validation'] = self.config.review_validation
        if self.config.review_validation:
            context['review_validation_context'] = {'probes': self.review_checks.probes,
                'last_result': self.review_checks.last_result, 'revision': self.review_checks.revision}
        return context

    def run_role(self, role, state, workspace, tracer, metrics):
        starting_revision = state.revision
        context = self.role_context(role, state, workspace)
        entry_feedback = {'revision': state.revision,
                          'test_result': json.dumps(context.get('test_result'), ensure_ascii=False)[-3000:],
                          'review_feedback': json.dumps(context.get('review_feedback'), ensure_ascii=False)[:3000]}
        agent = self.agent_registry[role](role, self.client, context)
        tools = FileTools(workspace, self.config.max_output_chars)
        tracer.record({"event": "role_start", "step": state.steps, "agent": role,
                       "messages": agent.messages.copy()})
        previous = None
        repeated = 0
        protocol_failures = 0
        recent_actions = []
        functions = role_functions(role, SCHEMAS[role], self.config.review_validation)
        for turn in range(1, self.config.max_role_turns + 1):
            size = len(json.dumps(agent.messages, ensure_ascii=False))
            if (self.config.role_context_refresh and len(agent.messages) > 2
                    and size > self.config.max_context_chars * 0.8):
                context = self.role_context(role, state, workspace)
                context['context_refresh'] = {
                    'reason': 'Earlier dialogue replaced by current workspace evidence and recent action outcomes.',
                    'remaining_role_turns': self.config.max_role_turns - turn + 1,
                    'recent_actions': recent_actions[-3:],
                    'role_entry_feedback': entry_feedback,
                    'instruction': 'Do not repeat completed edits. Use current source; submit when your role is complete.'}
                # Start a fresh complete conversation, never orphan native tool result messages.
                agent = self.agent_registry[role](role, self.client, context)
                metrics['context_refreshes'] = metrics.get('context_refreshes', 0) + 1
                tracer.record({'event': 'role_context_refresh', 'step': state.steps, 'agent': role,
                               'turn': turn, 'previous_chars': size,
                               'current_chars': len(json.dumps(agent.messages, ensure_ascii=False)),
                               'revision': state.revision, 'messages': agent.messages.copy()})
            started = time.monotonic()
            reply = self.query_model(agent.messages, "agent", state, tracer, metrics, functions,
                                     allow_empty=self.config.protocol_recovery)
            agent.messages.append(reply.assistant_message())
            usage = reply.usage
            action = None
            submitted = False
            try:
                self.remaining()
                if reply.response_error():
                    raise json.JSONDecodeError('No usable function response; no action executed', reply.content, 0)
                action = agent.parse(reply.content)
                tool, args = action["tool"], action["args"]
                if tool == "submit":
                    result = validate_result(role, args)
                    validate_coverage(role, result, context['issue_requirements'], tools)
                    if (role == 'reviewer' and result['accepted'] and self.config.review_validation
                            and self.review_checks.revision == state.revision
                            and self.review_checks.last_result and not self.review_checks.passed(state.revision)):
                        result = dict(result, accepted=False, recommended_next_agent='analyzer',
                            reason='Supplemental checks failed; independently diagnose whether the program or generated test '
                                   'violates the issue before editing. Approval was vetoed. ' +
                                   self.review_checks.last_result['summary'][-2000:])
                        affected = {i for p in self.review_checks.probes for i in p['requirement_ids']}
                        result['requirement_checks'] = [dict(check, status='uncertain',
                            reason='Supplemental failure requires diagnosis against the issue')
                            if check.get('id') in affected else check for check in result['requirement_checks']]
                        tracer.record({'event': 'review_approval_vetoed', 'step': state.steps,
                                       'probe_result': self.review_checks.last_result})
                    if role == 'reviewer' and result['accepted'] and self.config.review_validation:
                        if not self.review_checks.passed(state.revision):
                            raise ValueError('Acceptance requires passing supplemental tests for current revision. '
                                             'Run run_review_test or reject with concrete feedback.')
                    if role == "analyzer":
                        for name in result["suspected_files"]:
                            if not tools.resolve(name).is_file():
                                raise ValueError("Suspected file does not exist")
                    submitted = True
                elif tool not in agent.allowed_tools:
                    raise ValueError(f"{role} cannot use {tool}")
                elif tool == 'run_review_test':
                    self.review_checks.add(**args, allowed={r['id'] for r in context['issue_requirements']})
                    metrics['tool_calls'] += 1
                    metrics['review_test_runs'] = metrics.get('review_test_runs', 0) + 1
                    result = self.review_checks.run(workspace, min(self.remaining(), self.config.test_timeout),
                                                    self.config.max_output_chars)
                    tracer.save('review_probes.json', self.review_checks.probes)
                    metrics['failed_review_test_runs'] = metrics.get('failed_review_test_runs', 0) + (result['status'] != 'passed')
                    state.update_revision(workspace.revision())
                elif tool == "git_diff":
                    if args:
                        raise ValueError("git_diff takes no arguments")
                    metrics["tool_calls"] += 1
                    diff = workspace.diff()
                    result = {"diff": diff[:self.config.max_output_chars],
                              "truncated": len(diff) > self.config.max_output_chars}
                else:
                    metrics["tool_calls"] += 1
                    result = getattr(tools, tool)(**args)
                    state.update_revision(workspace.revision())
            except json.JSONDecodeError as error:
                protocol_failures += 1
                metrics["protocol_errors"] += 1
                result = {"error": str(error), "error_type": "invalid_json", "executed": False,
                          "correction": 'No action executed. Retry only the intended action with valid arguments. '
                                        'Use one function call in native mode; otherwise exactly one tool/args JSON object. '
                                        'Do not repeat reads unnecessarily or concatenate actions. Close all JSON braces.'}
            except FileNotFoundError:
                metrics["file_lookup_errors"] += 1
                result = {"error": "Requested file does not exist", "error_type": "missing_file",
                          "available_files": context["repository_files"],
                          "files_truncated": context["repository_files_truncated"],
                          "correction": "Use an observed relative path, or search_code to locate it."}
            except (ValueError, TypeError, OSError) as error:
                result = {"error": str(error)}
            tracer.record({"event": "role_turn", "step": state.steps, "agent": role,
                           "turn": turn, "action": action, "model_content": reply.content,
                           "result": result, "usage": usage, "model": reply.model,
                           "revision": state.revision, "latency_seconds": time.monotonic() - started})
            if submitted:
                return result
            recent_actions.append({'tool': action.get('tool') if action else None,
                                   'revision': state.revision,
                                   'outcome': json.dumps(result, ensure_ascii=False)[:2000]})
            if self.config.protocol_recovery and protocol_failures >= 2:
                raise ModelResponseError('protocol_recovery_exhausted')
            agent.observe({"result": result, "remaining_role_turns": self.config.max_role_turns - turn})
            signature = json.dumps([action, result, state.revision], sort_keys=True)
            repeated = repeated + 1 if signature == previous else 0
            previous = signature
            if repeated >= 2:
                raise RuntimeError("Role repeated an unchanged action three times")
        if role == 'developer' and self.config.developer_budget_handoff and state.revision != starting_revision:
            metrics['developer_budget_handoffs'] = metrics.get('developer_budget_handoffs', 0) + 1
            tracer.record({'event': 'developer_budget_handoff', 'step': state.steps, 'revision': state.revision})
            return {'change_summary': 'Role turn budget reached with unverified edits; hand current revision to Tester.'}
        raise BudgetExceeded(f"{role} exceeded its tool turn limit")

    def run(self, repo, issue, run_dir):
        self.started = time.monotonic()
        root = Path(run_dir).absolute().resolve()
        root.mkdir(parents=True, exist_ok=False)
        tracer = Tracer(root)
        self.review_checks = ReviewChecks(root, self.config.max_review_probes)
        state = RepairState(issue, str(Path(repo).resolve()), "", self.client.mode)
        metrics = {"mode": state.mode, "workflow": getattr(self.router, "name", "custom"), "model_calls": 0,
                   "llm_calls": 0, "mock_calls": 0, "input_tokens": 0, "output_tokens": 0,
                   "usage_missing_calls": 0, "tool_calls": 0, "test_runs": 0,
                   "failed_test_runs": 0, "router_calls": 0, "agent_calls": {}, "api_models": [],
                   "rule_decisions": 0, "agent_model_calls": 0, "router_model_calls": 0,
                   "agent_input_tokens": 0, "agent_output_tokens": 0,
                   "router_input_tokens": 0, "router_output_tokens": 0,
                   "lightweight_model_calls": 0, "lightweight_input_tokens": 0,
                   "lightweight_output_tokens": 0, "lightweight_decisions": 0,
                   "llm_escalations": 0, "confidence_threshold": getattr(self.router, "threshold", None),
                   "protocol_errors": 0, "file_lookup_errors": 0}
        workspace = None
        progress = Counter()
        try:
            workspace = Workspace(repo, root)
            state.workspace = str(workspace.root)
            state.update_revision(workspace.revision())
            while state.steps < self.config.max_steps:
                self.remaining()
                state.update_revision(workspace.revision())
                metrics["router_calls"] += 1
                allowed, gate_reason = RuleGate().allowed(state)
                def query_router(messages, tier="strong"):
                    if tier not in {"strong", "lightweight"}:
                        raise ValueError("Unknown router model tier")
                    tracer.record({"event": "router_input", "tier": tier,
                                   "step": state.steps, "messages": messages})
                    category = 'lightweight' if tier == 'lightweight' else 'router'
                    attempts = 2 if self.config.protocol_recovery and tier == 'strong' else 1
                    current = list(messages)
                    for attempt in range(attempts):
                        reply = self.query_model(current, category, state, tracer, metrics,
                                                 route_functions(allowed), allow_empty=attempts == 2)
                        try:
                            reply.require_complete()
                            parsed = json.loads(reply.content)
                            if not isinstance(parsed, dict) or set(parsed) != {'choice', 'confidence', 'reason'}:
                                raise ValueError('Routing needs choice, confidence, reason')
                            return reply
                        except (json.JSONDecodeError, ValueError, ModelResponseError):
                            if attempt + 1 == attempts:
                                raise
                            current.append(reply.assistant_message())
                            correction = {'error': 'No route executed. Call route once with valid choice, confidence and reason.'}
                            if reply.tool_calls:
                                for call in reply.tool_calls:
                                    current.append({'role': 'tool', 'tool_call_id': call['id'],
                                                    'content': json.dumps(correction)})
                            else:
                                current.append({'role': 'user', 'content': json.dumps(correction)})
                            tracer.record({'event': 'router_protocol_retry', 'step': state.steps, 'tier': tier})
                decision = self.router.route(state, query=query_router)
                if not isinstance(decision, RouteDecision):
                    raise ValueError("Router must return RouteDecision")
                role = decision.choice
                tracer.record({"event": "route_decision", "step": state.steps,
                               "decision": asdict(decision), "allowed_actions": list(allowed),
                               "constraint_reason": gate_reason})
                if role == "finish":
                    if not state.accepted():
                        raise ValueError("Finish rejected: current tests and review must both pass")
                    state.status = "succeeded"
                    state.stop_reason = "Current revision passed tests and Reviewer accepted"
                    break
                RuleGate().validate(state, role)
                metrics["rule_decisions"] += decision.source == "rule"
                metrics["lightweight_decisions"] += decision.source == "lightweight"
                if role not in self.agent_registry:
                    raise ValueError("Unknown role")
                if role == "reviewer" and not state.verified():
                    raise ValueError("Reviewer requires passing tests for current revision")
                state.steps += 1
                before = asdict(state)
                metrics["agent_calls"][role] = metrics["agent_calls"].get(role, 0) + 1
                started = time.monotonic()
                if role == "tester":
                    metrics["test_runs"] += 1
                    metrics["tool_calls"] += 1
                    state.test_result = self.agent_registry[role].run(workspace, root,
                        metrics["test_runs"], min(self.remaining(), self.config.test_timeout),
                        self.config.max_output_chars)
                    result = asdict(state.test_result)
                    metrics["failed_test_runs"] += state.test_result.status != "passed"
                    state.update_revision(workspace.revision())
                else:
                    if role == 'reviewer' and self.config.review_validation and self.review_checks.probes:
                        if self.review_checks.revision != state.revision:
                            metrics['review_test_runs'] = metrics.get('review_test_runs', 0) + 1
                            probe_result = self.review_checks.run(workspace, min(self.remaining(), self.config.test_timeout),
                                                                 self.config.max_output_chars)
                            metrics['failed_review_test_runs'] = metrics.get('failed_review_test_runs', 0) + (probe_result['status'] != 'passed')
                            tracer.record({'event': 'review_revalidation', 'step': state.steps, 'result': probe_result})
                            state.update_revision(workspace.revision())
                    result = self.run_role(role, state, workspace, tracer, metrics)
                    if role == "analyzer":
                        state.analysis = result
                    elif role == "developer":
                        state.developer_result = result
                    elif role == "debugger":
                        state.debug_feedback = result
                    else:
                        state.review = result
                        state.review_revision = state.revision
                state.current_agent = role
                state.history.append(role)
                state.modified_files = workspace.modified_files()
                tracer.record({"event": "role_complete", "step": state.steps, "agent": role,
                               "router": asdict(decision), "result": result,
                               "state_before": before, "state_after": asdict(state),
                               "latency_seconds": time.monotonic() - started})
                if state.accepted():
                    state.status = "succeeded"
                    state.stop_reason = "Current revision passed tests and Reviewer accepted"
                    break
                progress[(role, state.revision)] += 1
                if progress[(role, state.revision)] >= 3:
                    state.status = "stalled"
                    state.stop_reason = "Same role revisited unchanged code three times"
                    break
            if state.status == "running":
                raise BudgetExceeded("Maximum role steps reached")
        except BudgetExceeded as error:
            state.status = "budget_exhausted"
            state.stop_reason = str(error)
        except Exception as error:
            state.status = "execution_error"
            state.stop_reason = f"{type(error).__name__}: {error}"
        finally:
            if workspace:
                try:
                    state.update_revision(workspace.revision())
                    state.modified_files = workspace.modified_files()
                    (root / "final.diff").write_text(workspace.diff(), encoding="utf-8")
                    if state.status == "succeeded" and not state.accepted():
                        state.status = "execution_error"
                        state.stop_reason = "Final verification became stale"
                except Exception as error:
                    state.status = "execution_error"
                    state.stop_reason = f"Finalization failed: {error}"
            tracer.record({"event": "run_end", "status": state.status, "reason": state.stop_reason})
            metrics.update({"status": state.status, "success": state.status == "succeeded",
                            "success_scope": "tests_and_review", "steps": state.steps,
                            "latency_seconds": time.monotonic() - self.started})
            tracer.save("final_state.json", state)
            tracer.save("metrics.json", metrics)
            tracer.save("trajectory.json", tracer.events)
        return state
