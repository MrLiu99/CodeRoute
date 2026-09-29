import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from coderoute.agents.base import RoleAgent
from coderoute.config import Config
from coderoute.models.client import ChatClient, ModelReply
from coderoute.models.functions import role_functions
from coderoute.models.multi_demo import MultiDemoClient
from coderoute.multi_harness import MultiAgentHarness
from coderoute.tools.review_checks import ReviewChecks
from coderoute.tools.workspace import Workspace


DEMO = Path(__file__).resolve().parents[1] / 'examples' / 'demo_repo'


def test_native_wire_and_observation_link(monkeypatch):
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'test-key')
    client = ChatClient(Config(base_url='https://api.deepseek.com', thinking_mode='disabled'))
    call = {'id': 'call_1', 'type': 'function',
            'function': {'name': 'read_file', 'arguments': '{"path":"config_reader.py"}'}}
    response = {'choices': [{'message': {'content': None, 'tool_calls': [call]}, 'finish_reason': 'tool_calls'}],
                'usage': {'completion_tokens': 20}}
    with patch('urllib.request.urlopen', return_value=io.BytesIO(json.dumps(response).encode())) as request:
        reply = client.complete_tools([], 3, role_functions('developer', {'change_summary': 'text'}))
    body = json.loads(request.call_args.args[0].data)
    assert 'response_format' not in body and body['tool_choice'] == 'required'
    assert body['parallel_tool_calls'] is False
    assert not reply.response_error()
    assert RoleAgent.parse(reply.content)['tool'] == 'read_file'
    agent = RoleAgent(client, 'issue', [])
    agent.messages.append(reply.assistant_message())
    agent.observe({'result': 'data'})
    assert agent.messages[-1]['role'] == 'tool'
    assert agent.messages[-1]['tool_call_id'] == 'call_1'


def test_multiple_calls_never_execute_partial_actions():
    calls = [{'id': 'a', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{}'}},
             {'id': 'b', 'type': 'function', 'function': {'name': 'read_file', 'arguments': '{}'}}]
    reply = ModelReply('', finish_reason='tool_calls', tool_calls=calls)
    assert reply.response_error() == 'multiple_tool_calls'
    agent = RoleAgent(None, 'issue', [])
    agent.messages.append(reply.assistant_message())
    agent.observe({'executed': False})
    assert [m['tool_call_id'] for m in agent.messages[-2:]] == ['a', 'b']


def test_probe_isolation_retention_and_revision(tmp_path):
    work = Workspace(DEMO, tmp_path / 'repair')
    before = work.revision()
    checks = ReviewChecks(tmp_path, 3)
    checks.add(['R1'], 'Blanks return an empty mapping',
               "from config_reader import read_config\ndef test_blank():\n    assert read_config(' ') == {}\n", {'R1'})
    assert checks.run(work, 15, 2000)['status'] == 'failed'
    assert work.revision() == before
    checks.add(['R1'], 'Extra check cannot mask prior failure', 'def test_extra():\n    assert 1 == 1\n', {'R1'})
    assert checks.run(work, 15, 2000)['status'] == 'failed'
    from coderoute.tools.files import FileTools
    FileTools(work).edit_file('config_reader.py', '    return json.loads(text)',
                             '    return json.loads(text) if text.strip() else {}')
    assert not checks.passed(work.revision())
    assert checks.run(work, 15, 2000)['status'] == 'passed'
    assert checks.passed(work.revision())
    assert not (work.root / '__coderoute_review__').exists()


def test_probe_cannot_rewrite_copy_and_claim_success(tmp_path):
    work = Workspace(DEMO, tmp_path / 'repair')
    checks = ReviewChecks(tmp_path, 1)
    checks.add(['R1'], 'mutation is detected',
               "from pathlib import Path\ndef test_change():\n    Path('config_reader.py').write_text('changed')\n", {'R1'})
    assert checks.run(work, 15, 2000)['status'] == 'workspace_changed_during_test'
    assert 'json.loads' in (work.root / 'config_reader.py').read_text()


@pytest.mark.parametrize('budget,expected_calls', [(1, 1), (8, 2)])
def test_one_empty_correction_uses_shared_call_budget(tmp_path, budget, expected_calls):
    class Empty:
        mode = 'live'
        def complete(self, messages, timeout):
            return ModelReply('', {'completion_tokens': 2}, 'fake', 'stop')
    root = tmp_path / 'run'
    state = MultiAgentHarness(Config(protocol_recovery=True, max_model_calls=budget), Empty()).run(DEMO, 'issue', root)
    metrics = json.loads((root / 'metrics.json').read_text())
    assert metrics['model_calls'] == expected_calls
    assert metrics['output_tokens'] == 2 * expected_calls
    assert metrics['tool_calls'] == 0
    assert state.status == ('budget_exhausted' if budget == 1 else 'execution_error')


def test_reviewer_must_run_probe_before_approval(tmp_path):
    class Client(MultiDemoClient):
        review_turn = 0
        saved = None
        def complete(self, messages, timeout):
            if "CodeRoute's reviewer agent" in messages[0]['content']:
                self.review_turn += 1
                if self.review_turn == 3:
                    assert 'Acceptance requires' in json.loads(messages[-1]['content'])['tool_observation']['result']['error']
                    return ModelReply(json.dumps({'tool': 'run_review_test', 'args': {'requirement_ids': ['R1'],
                        'reason': 'Whitespace contract', 'code': "from config_reader import read_config\ndef test_blank():\n    assert read_config(' ') == {}\n"}}))
                if self.review_turn == 4:
                    return self.saved
            reply = super().complete(messages, timeout)
            if self.review_turn == 2:
                self.saved = reply
            return reply
    root = tmp_path / 'run'
    state = MultiAgentHarness(Config(review_validation=True), Client()).run(DEMO, 'Handle blank input', root)
    assert state.status == 'succeeded', state.stop_reason
    assert json.loads((root / 'metrics.json').read_text())['review_test_runs'] == 1


def test_multiple_native_calls_get_one_correction_without_execution(tmp_path):
    class Client(MultiDemoClient):
        turns = 0
        def complete(self, messages, timeout):
            self.turns += 1
            if self.turns == 1:
                calls = [{'id': name, 'type': 'function', 'function': {'name': 'read_file',
                          'arguments': '{"path":"config_reader.py"}'}} for name in ['a', 'b']]
                return ModelReply('', finish_reason='tool_calls', tool_calls=calls)
            if self.turns == 2:
                assert [m['tool_call_id'] for m in messages[-2:]] == ['a', 'b']
                assert all(json.loads(m['content'])['result']['executed'] is False for m in messages[-2:])
            return super().complete(messages, timeout)
    root = tmp_path / 'run'
    state = MultiAgentHarness(Config(protocol_recovery=True), Client()).run(DEMO, 'blank', root)
    assert state.status == 'succeeded', state.stop_reason
    metrics = json.loads((root / 'metrics.json').read_text())
    assert metrics['response_errors']['multiple_tool_calls'] == 1
    assert metrics['protocol_errors'] == 1


def test_failed_probe_vetoes_claimed_approval_without_repeated_submit(tmp_path):
    class Client(MultiDemoClient):
        injected = False
        def complete(self, messages, timeout):
            if "CodeRoute's reviewer agent" in messages[0]['content'] and not self.injected:
                self.injected = True
                return ModelReply(json.dumps({'tool': 'run_review_test', 'args': {'requirement_ids': ['R1'],
                    'reason': 'Deliberately bad test fixture', 'code': 'def test_bad():\n    assert False\n'}}))
            return super().complete(messages, timeout)
    root = tmp_path / 'run'
    state = MultiAgentHarness(Config(review_validation=True, max_steps=7), Client()).run(DEMO, 'blank', root)
    assert state.review['accepted'] is False
    assert state.review['recommended_next_agent'] == 'analyzer'
    assert state.review['requirement_checks'][0]['status'] == 'uncertain'
    events = json.loads((root / 'trajectory.json').read_text())
    assert len([e for e in events if e.get('event') == 'review_approval_vetoed']) == 1
