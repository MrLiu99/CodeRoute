from cache import Cache

def test_snapshots():
    cache = Cache()
    value = {'items': [1]}
    cache.put('a', 'x', value, 0, 10)
    value['items'].append(2)
    first = cache.get('a', 'x', 1)
    assert first == {'items': [1]}
    first['items'].append(3)
    assert cache.get('a', 'x', 1) == {'items': [1]}

def test_none_zero_and_key_collision():
    cache = Cache()
    cache.put('a', 'none', None, 0, 10)
    assert cache.get('a', 'none', 1, 'miss') is None
    cache.put('a', 'zero', 1, 0, 0)
    assert cache.get('a', 'zero', 0, 'miss') == 'miss'
    cache.put('a:b', 'c', 1, 0, 10)
    cache.put('a', 'b:c', 2, 0, 10)
    assert cache.get('a:b', 'c', 1) == 1
