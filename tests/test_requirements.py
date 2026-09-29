import copy
import json
from pathlib import Path

import pytest

from coderoute.config import Config
from coderoute.models.client import ModelReply
from coderoute.models.multi_demo import MultiDemoClient
from coderoute.multi_harness import MultiAgentHarness
from coderoute.requirements import issue_requirements, validate_coverage
from coderoute.tools.files import FileTools
from coderoute.tools.workspace import Workspace


DEMO = Path(__file__).resolve().parents[1] / 'examples' / 'demo_repo'


def test_original_scope_survives_sentence_and_decimal_splitting():
    clauses = issue_requirements('Keep 1.5 unchanged. Strip BOM; preserve bytes.\n允许空值。保留顺序。')
    assert [r['id'] for r in clauses] == ['R1', 'R2', 'R3', 'R4', 'R5']
    assert clauses[0]['text'] == 'Keep 1.5 unchanged.'
    assert clauses[1]['text'] == 'Strip BOM;'


@pytest.fixture
def tools(tmp_path):
    return FileTools(Workspace(DEMO, tmp_path / 'run'))


def review():
    return {'accepted': True, 'requirement_checks': [
        {'id': 'R1', 'status': 'met', 'reason': 'Uses the JSON parser',
         'evidence': [{'path': 'config_reader.py', 'quote': 'return json.loads(text)'}]}]}


@pytest.mark.parametrize('kind', ['missing', 'duplicate', 'invented', 'uncertain', 'unmet', 'empty_quote', 'invented_quote'])
def test_approval_requires_complete_checklist_and_real_evidence(tools, kind):
    result = review()
    checks = result['requirement_checks']
    if kind == 'missing':
        checks.clear()
    elif kind == 'duplicate':
        checks.append(copy.deepcopy(checks[0]))
    elif kind == 'invented':
        checks[0]['id'] = 'R99'
    elif kind in ('uncertain', 'unmet'):
        checks[0]['status'] = kind
    elif kind == 'empty_quote':
        checks[0]['evidence'] = []
    else:
        checks[0]['evidence'][0]['quote'] = 'nonexistent implementation'
    with pytest.raises(ValueError):
        validate_coverage('reviewer', result, issue_requirements('Parse JSON.'), tools)


def test_rejecting_uncertainty_and_accepting_current_evidence(tools):
    requirements = issue_requirements('Parse JSON.')
    validate_coverage('reviewer', review(), requirements, tools)
    result = review()
    result['accepted'] = False
    result['requirement_checks'][0].update(status='uncertain', evidence=[])
    validate_coverage('reviewer', result, requirements, tools)
    tools.edit_file('config_reader.py', 'return json.loads(text)', 'return {}')
    with pytest.raises(ValueError, match='does not match current file'):
        validate_coverage('reviewer', review(), requirements, tools)


def test_analyzer_cannot_drop_an_issue_clause(tools):
    with pytest.raises(ValueError, match='every issue requirement'):
        validate_coverage('analyzer', {'requirement_plan': [{'id': 'R1', 'check': 'Parse'}]},
                          issue_requirements('Parse JSON. Preserve BOM behavior.'), tools)


def test_invalid_review_does_not_finish_run(tmp_path):
    class Client(MultiDemoClient):
        injected = False

        def complete(self, messages, timeout):
            if "CodeRoute's reviewer agent" in messages[0]['content'] and not self.injected:
                self.injected = True
                args = {'accepted': True, 'risk_level': 'low', 'reason': 'Tests passed',
                        'confidence': 0.9, 'recommended_next_agent': 'developer', 'requirement_checks': []}
                return ModelReply(json.dumps({'tool': 'submit', 'args': args}))
            return super().complete(messages, timeout)

    root = tmp_path / 'run'
    state = MultiAgentHarness(Config(), Client()).run(DEMO, 'Handle blank input.', root)
    assert state.status == 'succeeded', state.stop_reason
    assert state.review['requirement_checks']
    events = json.loads((root / 'trajectory.json').read_text())
    rejected = [e for e in events if e.get('event') == 'role_turn' and e.get('agent') == 'reviewer'
                and 'error' in e.get('result', {})]
    assert len(rejected) == 1
