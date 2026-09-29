import json
from pathlib import Path

import pytest

from coderoute.config import Config
from coderoute.context import ContextBuilder
from coderoute.evaluation import suite_cases
from coderoute.models.client import ModelReply
from coderoute.multi_harness import MultiAgentHarness
from coderoute.state import RepairState, TestResult as Result
from coderoute.tools.workspace import Workspace


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / 'examples' / 'demo_repo'


def test_direct_developer_receives_actual_test_failure(tmp_path):
    work = Workspace(DEMO, tmp_path / 'run')
    state = RepairState('Handle blanks', str(DEMO), str(work.root), 'mock', revision=work.revision())
    state.test_result = Result('failed', state.revision, failed=1, summary='AssertionError: expected empty mapping')
    context = ContextBuilder(work, 12000).build('developer', state)
    assert context['debug_feedback'] == {}
    assert context['test_result']['summary'] == state.test_result.summary
    assert context['test_result']['revision'] == work.revision()


@pytest.mark.parametrize('call_limit', [2, 3])
def test_native_context_refresh_preserves_edits_and_global_budget(tmp_path, call_limit):
    class Client:
        mode = 'mock'
        calls = 0

        def complete_tools(self, messages, timeout, functions, routing=False):
            self.calls += 1
            if self.calls == 1:
                name, args = 'submit', {'suspected_files': ['config_reader.py'], 'hypothesis': 'Handle blanks',
                    'confidence': 0.9, 'requirement_plan': [{'id': 'R1', 'check': 'Blanks return a mapping'}]}
            elif self.calls == 2:
                name, args = 'edit_file', {'path': 'config_reader.py', 'old': '    return json.loads(text)',
                    'new': '    return json.loads(text) if text.strip() else {}\n#' + 'x' * 13000}
            else:
                assert [m['role'] for m in messages] == ['system', 'user']
                context = json.loads(messages[1]['content'])
                assert context['context_refresh']['remaining_role_turns'] == 2
                assert context['context_refresh']['recent_actions'][-1]['tool'] == 'edit_file'
                assert context['context_refresh']['recent_actions'][-1]['revision'] == context['revision']
                assert 'if text.strip() else {}' in context['review_evidence'][0]['content']
                assert len(json.dumps(messages, ensure_ascii=False)) < 12000
                name, args = 'submit', {'change_summary': 'Blank input fixed'}
            call = {'id': 'call_' + str(self.calls), 'type': 'function',
                    'function': {'name': name, 'arguments': json.dumps(args)}}
            return ModelReply(json.dumps({'tool': name, 'args': args}), tool_calls=[call], native=True)

    root = tmp_path / 'run'
    client = Client()
    state = MultiAgentHarness(Config(native_tool_calls=True, role_context_refresh=True,
        max_context_chars=12000, max_output_chars=500, max_role_turns=3,
        max_model_calls=call_limit, max_steps=2), client).run(DEMO, 'Handle blanks', root)
    metrics = json.loads((root / 'metrics.json').read_text())
    assert metrics['context_refreshes'] == 1
    assert metrics['model_calls'] == client.calls == call_limit
    assert state.status == 'budget_exhausted'
    assert state.test_result is None and not state.accepted()
    assert 'if text.strip() else {}' in (Path(state.workspace) / 'config_reader.py').read_text()
    if call_limit == 3:
        assert state.history == ['analyzer', 'developer']
    else:
        assert state.stop_reason == 'Total model call limit reached'


def test_suite_rejects_duplicates_and_missing_cases(tmp_path):
    path = tmp_path / 'suite.json'
    case = str(ROOT / 'benchmarks' / '01_blank_config')
    path.write_text(json.dumps([case, case]))
    with pytest.raises(ValueError, match='unique'):
        suite_cases(path)
    path.write_text(json.dumps(['missing']))
    with pytest.raises(ValueError, match='incomplete'):
        suite_cases(path)
    path.write_text(json.dumps([case]))
    assert suite_cases(path) == [Path(case)]
