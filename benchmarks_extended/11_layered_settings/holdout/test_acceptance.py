import pytest
from settings import load_settings

def test_no_aliasing():
    defaults = {'tags': ['a']}
    override = {'other': {'list': [1]}}
    result = load_settings(defaults, override, {})
    result['tags'].append('b')
    result['other']['list'].append(2)
    assert defaults == {'tags': ['a']}
    assert override == {'other': {'list': [1]}}

def test_scalar_replace():
    assert load_settings({'x': {'a': 1}}, {'x': None}, {}) == {'x': None}

def test_env():
    assert load_settings({'enabled': False}, {}, {})['enabled'] is False
    assert load_settings({}, {}, {'APP_ENABLED': ' TRUE '})['enabled'] is True
    with pytest.raises(ValueError): load_settings({}, {}, {'APP_ENABLED': 'maybe'})
