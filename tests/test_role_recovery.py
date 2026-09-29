import json
from pathlib import Path

from coderoute.config import Config
from coderoute.context import ContextBuilder
from coderoute.models.client import ModelReply
from coderoute.models.multi_demo import MultiDemoClient
from coderoute.multi_harness import MultiAgentHarness
from coderoute.state import RepairState
from coderoute.tools.workspace import Workspace


DEMO = Path(__file__).resolve().parents[1] / 'examples' / 'demo_repo'


def test_reviewer_has_real_paths_and_bounded_evidence(tmp_path):
    work = Workspace(DEMO, tmp_path / 'run')
    state = RepairState('issue', str(DEMO), str(work.root), 'mock')
    context = ContextBuilder(work, 80).build('reviewer', state)
    assert sum(len(x['content']) for x in context['review_evidence']) <= 80
    assert context['review_evidence_truncated']
    full = ContextBuilder(work, 12000).build('reviewer', state)
    assert 'tests/test_config_reader.py' in full['repository_files']
    assert any(e['path'] == 'tests/test_config_reader.py' for e in full['review_evidence'])


def test_reviewer_recovers_without_executing_concatenated_actions(tmp_path):
    class RecoveringClient(MultiDemoClient):
        reviewer_turn = 0

        def complete(self, messages, timeout):
            if "You are CodeRoute's reviewer agent" in messages[0]['content']:
                self.reviewer_turn += 1
                if self.reviewer_turn == 1:
                    return ModelReply('{"tool":"read_file","args":{"path":"bad.py"}}\n{"tool":"finish","args":{}}')
                if self.reviewer_turn == 2:
                    observation = json.loads(messages[-1]['content'])['tool_observation']
                    assert observation['result']['executed'] is False
                    assert observation['remaining_role_turns'] == 7
                    return ModelReply('{"tool":"read_file","args":{"path":"test_config.py"}}')
                if self.reviewer_turn == 3:
                    result = json.loads(messages[-1]['content'])['tool_observation']['result']
                    assert 'tests/test_config_reader.py' in result['available_files']
            return super().complete(messages, timeout)

    run = tmp_path / 'run'
    state = MultiAgentHarness(Config(), RecoveringClient()).run(DEMO, 'Handle blanks', run)
    assert state.status == 'succeeded', state.stop_reason
    metrics = json.loads((run / 'metrics.json').read_text())
    assert metrics['protocol_errors'] == 1
    assert metrics['file_lookup_errors'] == 1
    events = json.loads((run / 'trajectory.json').read_text())
    invalid = [e for e in events if e['event'] == 'role_turn' and e['result'].get('error_type') == 'invalid_json']
    assert len(invalid) == 1 and invalid[0]['action'] is None
