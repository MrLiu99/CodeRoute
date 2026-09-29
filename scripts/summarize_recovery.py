"""Summarize actual test/debug/repair evidence; never calls a model or edits a run."""
import argparse
import json
from pathlib import Path


def recovery_evidence(events, accepted):
    roles = [event for event in events if event.get('event') == 'role_complete']
    attempts = []
    for index, event in enumerate(roles):
        if event.get('agent') != 'tester' or event.get('result', {}).get('status') != 'failed':
            continue
        failed_revision = event['result'].get('revision')
        stage = 'debugger'
        steps = [event.get('step')]
        for later in roles[index + 1:]:
            agent = later.get('agent')
            if stage == 'debugger' and agent == 'developer':
                # Direct repair is valid, but not evidence of Debugger-assisted recovery.
                break
            if agent != stage:
                continue
            if stage == 'tester':
                result = later.get('result', {})
                if result.get('status') != 'passed' or result.get('revision') == failed_revision:
                    break
                steps.append(later.get('step'))
                attempts.append({'steps': steps, 'failed_revision': failed_revision,
                                 'passing_revision': result.get('revision')})
                break
            steps.append(later.get('step'))
            stage = 'developer' if stage == 'debugger' else 'tester'
    return {'roles': [e['agent'] for e in roles],
            'failed_test_steps': [e.get('step') for e in roles if e.get('agent') == 'tester'
                                  and e.get('result', {}).get('status') == 'failed'],
            'debugger_steps': [e.get('step') for e in roles if e.get('agent') == 'debugger'],
            'debugger_test_recoveries': attempts,
            'accepted_debugger_recovery': bool(attempts) and accepted}


def summarize(batch):
    batch = Path(batch)
    rows = json.loads((batch / 'results.json').read_text(encoding='utf-8'))
    summary = []
    for row in rows:
        root = Path(row['artifacts'])
        events = json.loads((root / 'trajectory.json').read_text(encoding='utf-8'))
        metrics = json.loads((root / 'metrics.json').read_text(encoding='utf-8'))
        empty = [e for e in events if e.get('event') == 'model_response'
                 and not e.get('content', '').strip()]
        summary.append({**{k: row[k] for k in ('case', 'workflow', 'repeat', 'success', 'status',
                                               'acceptance_status', 'stop_reason')},
                        **recovery_evidence(events, row['success']),
                        'protocol_errors': metrics.get('protocol_errors', 0),
                        'empty_responses': len(empty),
                        'empty_response_completion_tokens': [e.get('usage', {}).get('completion_tokens') for e in empty]})
    return summary


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('batch')
    args = parser.parse_args()
    print(json.dumps(summarize(args.batch), indent=2, ensure_ascii=False))
