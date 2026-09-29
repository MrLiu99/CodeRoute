import json
from pathlib import Path

import pytest

from coderoute.config import Config
from coderoute.models.client import ModelReply
from coderoute.multi_harness import MultiAgentHarness
from coderoute.tools.files import FileTools
from coderoute.tools.workspace import Workspace


DEMO = Path(__file__).resolve().parents[1] / 'examples' / 'demo_repo'


def test_batch_validates_all_edits_before_writing(tmp_path):
    work = Workspace(DEMO, tmp_path / 'run')
    tools = FileTools(work)
    before = work.revision()
    with pytest.raises(ValueError):
        tools.apply_edits([{'path': 'config_reader.py', 'old': 'json.loads(text)', 'new': '{}'},
                           {'path': 'tests/test_config_reader.py', 'old': 'irrelevant', 'new': 'bad'}])
    assert work.revision() == before
    with pytest.raises(ValueError):
        tools.apply_edits([{'path': 'config_reader.py', 'old': 'json.loads(text)', 'new': '{}'},
                           {'path': 'config_reader.py', 'old': 'nonexistent', 'new': ''}])
    assert work.revision() == before


def test_batch_edits_same_file_in_order_preserving_crlf(tmp_path):
    work = Workspace(DEMO, tmp_path / 'run')
    path = work.root / 'config_reader.py'
    path.write_bytes(b'import json\r\ndef read_config(text):\r\n    return json.loads(text)\r\n')
    FileTools(work).apply_edits([
        {'path': 'config_reader.py', 'old': 'json.loads(text)', 'new': 'json.loads(text.strip())'},
        {'path': 'config_reader.py', 'old': 'return json.loads(text.strip())',
         'new': 'return json.loads(text.strip()) if text.strip() else {}'}])
    assert b'else {}\r\n' in path.read_bytes()
    assert b'\n' not in path.read_bytes().replace(b'\r\n', b'')


@pytest.mark.parametrize('correct', [True, False])
def test_developer_turn_limit_hands_off_but_does_not_bypass_tests(tmp_path, correct):
    actions = [
        {'tool': 'submit', 'args': {'suspected_files': ['config_reader.py'], 'hypothesis': 'Handle blanks',
          'confidence': 0.9, 'requirement_plan': [{'id': 'R1', 'check': 'Blank strings return a mapping'}]}},
        {'tool': 'edit_file', 'args': {'path': 'config_reader.py', 'old': '    return json.loads(text)',
          'new': '    if not text.strip():\n        return {}\n    return json.loads(text)' if correct else '    return []'}},
        {'tool': 'submit', 'args': {'accepted': True, 'risk_level': 'low', 'reason': 'Verified blank handling',
          'recommended_next_agent': 'developer', 'confidence': 0.9, 'requirement_checks': [
              {'id': 'R1', 'status': 'met', 'reason': 'Returns an empty mapping for blanks',
               'evidence': [{'path': 'config_reader.py', 'quote': 'return {}'}]}]}}]
    class Client:
        mode = 'mock'
        def complete(self, messages, timeout):
            return ModelReply(json.dumps(actions.pop(0)))
    root = tmp_path / 'run'
    state = MultiAgentHarness(Config(max_role_turns=1, max_steps=4 if correct else 3,
                                     developer_budget_handoff=True), Client()).run(DEMO, 'Handle blanks', root)
    assert state.status == ('succeeded' if correct else 'budget_exhausted'), state.stop_reason
    assert state.test_result.status == ('passed' if correct else 'failed')
    assert json.loads((root / 'metrics.json').read_text())['developer_budget_handoffs'] == 1
