"""Issue clauses stay visible independently of the model's analysis summary."""
import re


def issue_requirements(issue):
    clauses = [s.strip() for s in re.split(r'(?<=[.!?;])\s+|(?<=[。！？；])|\n+', issue) if s.strip()]
    return [{'id': 'R' + str(index + 1), 'text': text} for index, text in enumerate(clauses)]


def validate_coverage(role, result, requirements, tools):
    if role not in {'analyzer', 'reviewer'}:
        return
    key = 'requirement_plan' if role == 'analyzer' else 'requirement_checks'
    entries = result[key]
    expected = {item['id'] for item in requirements}
    if not isinstance(entries, list) or not entries or not all(isinstance(e, dict) for e in entries):
        raise ValueError(key + ' must contain one entry per issue requirement')
    ids = [entry.get('id') for entry in entries]
    if not all(isinstance(i, str) for i in ids) or len(ids) != len(set(ids)) or set(ids) != expected:
        raise ValueError('Cover every issue requirement exactly once: ' + ', '.join(sorted(expected)))
    for entry in entries:
        if role == 'analyzer':
            if set(entry) != {'id', 'check'} or not isinstance(entry['check'], str) or not entry['check'].strip():
                raise ValueError('Each requirement_plan entry needs id and a nonempty check')
            continue
        if set(entry) != {'id', 'status', 'reason', 'evidence'}:
            raise ValueError('Each requirement_checks entry needs id, status, reason, evidence')
        if entry['status'] not in ('met', 'unmet', 'uncertain'):
            raise ValueError('Requirement status must be met, unmet, or uncertain')
        if not isinstance(entry['reason'], str) or not entry['reason'].strip():
            raise ValueError('Each requirement check needs a reason')
        evidence = entry['evidence']
        if not isinstance(evidence, list) or len(evidence) > 3:
            raise ValueError('Evidence must be a list of at most three source excerpts')
        if entry['status'] == 'met' and not evidence:
            raise ValueError('A met requirement needs an exact source or test excerpt')
        for excerpt in evidence:
            if not isinstance(excerpt, dict) or set(excerpt) != {'path', 'quote'}:
                raise ValueError('Evidence needs path and quote')
            path, quote = excerpt['path'], excerpt['quote']
            if not isinstance(path, str) or not isinstance(quote, str) or not quote.strip() or len(quote) > 1500:
                raise ValueError('Evidence needs a relative path and a nonempty quote of at most 1500 characters')
            target = tools.resolve(path)
            if target.suffix != '.py' or not target.is_file() or target.stat().st_size > 1_000_000:
                raise ValueError('Evidence must cite an existing Python source or test file under 1 MB')
            if quote not in target.read_text(encoding='utf-8'):
                raise ValueError('Evidence quote does not match current file: ' + path)
        if result['accepted'] and entry['status'] != 'met':
            raise ValueError('Cannot accept while any requirement is unmet or uncertain')
