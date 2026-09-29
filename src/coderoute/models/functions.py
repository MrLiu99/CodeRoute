"""Function schemas are transport hints; runtime permission checks remain authoritative."""


def schema(sample):
    if isinstance(sample, dict):
        return {'type': 'object', 'properties': {k: schema(v) for k, v in sample.items()},
                'required': list(sample), 'additionalProperties': False}
    if isinstance(sample, list):
        return {'type': 'array', 'items': schema(sample[0])}
    if isinstance(sample, bool):
        return {'type': 'boolean'}
    if isinstance(sample, (int, float)):
        return {'type': 'number'}
    return {'type': 'string'}


def function(name, description, sample):
    return {'type': 'function', 'function': {'name': name, 'description': description,
                                            'parameters': schema(sample)}}


def role_functions(role, submit, review_validation=False):
    result = [function('read_file', 'Read a current relative file.', {'path': 'file.py'}),
              function('search_code', 'Search repository text.', {'query': 'text'}),
              function('git_diff', 'Inspect the current patch.', {}),
              function('submit', 'Submit this role result, using exactly the declared fields.', submit)]
    if role == 'developer':
        result.append(function('apply_edits', 'Apply multiple focused edits in one call. All snippets are validated '
                               'before writing; edits to the same file are applied in order.',
                               {'edits': [{'path': 'file.py', 'old': 'old text', 'new': 'new text'}]}))
        result.append(function('edit_file', 'Replace one exact occurrence in an existing Python source file.',
                               {'path': 'file.py', 'old': 'old text', 'new': 'new text'}))
    if role == 'reviewer' and review_validation:
        result.append(function('run_review_test', 'Run additional pytest checks in a separate copy. '
                               'Previously added checks are retained. Derive checks only from the issue and public code.',
                               {'requirement_ids': ['R1'], 'reason': 'what edge cases this checks',
                                'code': 'def test_contract():\n    assert True'}))
    return result


def route_functions(allowed):
    result = function('route', 'Select exactly one allowed next role.',
                      {'choice': 'developer', 'confidence': 0.9, 'reason': 'evidence'})
    result['function']['parameters']['properties']['choice']['enum'] = list(allowed)
    return [result]
