from cache import Cache

def test_tenants():
    cache = Cache()
    cache.put('a', 'x', 1, 0, 10)
    cache.put('b', 'x', 2, 0, 10)
    assert cache.get('a', 'x', 1) == 1
    assert cache.get('b', 'x', 1) == 2

def test_expiry_boundary():
    cache = Cache()
    cache.put('a', 'x', 1, 2, 3)
    assert cache.get('a', 'x', 5, 'miss') == 'miss'
