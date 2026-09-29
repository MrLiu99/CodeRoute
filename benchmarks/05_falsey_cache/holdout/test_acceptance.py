import pytest
from cache import Cache

@pytest.mark.parametrize('value', [False, '', None])
def test_falsey(value):
    cache = Cache()
    cache.data['x'] = value
    def forbidden(): raise AssertionError('computed cached key')
    assert cache.get_or_compute('x', forbidden) == value

def test_miss_once():
    cache = Cache()
    calls = []
    def compute():
        calls.append(1)
        return 0
    assert cache.get_or_compute('x', compute) == 0
    assert cache.get_or_compute('x', compute) == 0
    assert len(calls) == 1
