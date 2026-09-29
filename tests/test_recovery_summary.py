import importlib.util
from pathlib import Path


spec = importlib.util.spec_from_file_location('recovery_summary',
    Path(__file__).resolve().parents[1] / 'scripts' / 'summarize_recovery.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def event(step, role, status=None, revision=None):
    return {'event': 'role_complete', 'step': step, 'agent': role,
            'result': {'status': status, 'revision': revision}}


def test_true_repair_requires_failed_test_debugger_new_patch_and_passing_test():
    events = [event(3, 'tester', 'failed', 'old'), event(4, 'debugger'),
              event(5, 'analyzer'), event(6, 'developer'), event(7, 'tester', 'passed', 'new')]
    evidence = module.recovery_evidence(events, True)
    assert evidence['accepted_debugger_recovery']
    assert evidence['debugger_test_recoveries'][0]['steps'] == [3, 4, 6, 7]
    assert not module.recovery_evidence(events, False)['accepted_debugger_recovery']


def test_no_false_evidence_from_timeout_unchanged_patch_or_direct_repair():
    for first, revision, middle in [('timeout', 'new', ['debugger', 'developer']),
                                    ('failed', 'old', ['debugger', 'developer']),
                                    ('failed', 'new', ['developer', 'debugger'])]:
        events = [event(1, 'tester', first, 'old')]
        events += [event(i + 2, role) for i, role in enumerate(middle)]
        events += [event(4, 'tester', 'passed', revision)]
        assert not module.recovery_evidence(events, True)['accepted_debugger_recovery']


def test_later_failed_patch_gets_its_own_recovery_attempt():
    events = [event(1, 'tester', 'failed', 'a'), event(2, 'debugger'),
              event(3, 'developer'), event(4, 'tester', 'failed', 'b'),
              event(5, 'debugger'), event(6, 'developer'), event(7, 'tester', 'passed', 'c')]
    evidence = module.recovery_evidence(events, True)
    assert len(evidence['debugger_test_recoveries']) == 1
    assert evidence['debugger_test_recoveries'][0]['failed_revision'] == 'b'
