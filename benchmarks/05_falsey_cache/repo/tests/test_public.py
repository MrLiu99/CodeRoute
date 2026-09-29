from cache import Cache

def test_cached_zero():
    cache = Cache()
    cache.data['x'] = 0
    assert cache.get_or_compute('x', lambda: 99) == 0
