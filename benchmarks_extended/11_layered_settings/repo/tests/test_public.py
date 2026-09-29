from settings import load_settings

def test_recursive_and_no_mutation():
    defaults = {'db': {'pool': {'min': 1, 'max': 5}}}
    result = load_settings(defaults, {'db': {'pool': {'max': 9}}}, {})
    assert result == {'db': {'pool': {'min': 1, 'max': 9}}}
    assert defaults == {'db': {'pool': {'min': 1, 'max': 5}}}

def test_false():
    assert load_settings({'enabled': True}, {}, {'APP_ENABLED': 'false'})['enabled'] is False
