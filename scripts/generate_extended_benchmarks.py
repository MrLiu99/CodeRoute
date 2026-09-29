"""Separate harder fixtures; never overwrite the original ten-case dataset."""
from pathlib import Path
from textwrap import dedent

import generate_benchmarks as fixtures


def code(text):
    return dedent(text).lstrip()


fixtures.CASES = [
    ("11_layered_settings", "extended", "load_settings must recursively merge nested overrides without modifying or sharing mutable lists/dicts with defaults or overrides. APP_ENABLED accepts case-insensitive true/false with surrounding whitespace; false must not become true. Missing environment value keeps the merged setting; invalid values raise ValueError.",
     {"merge.py": code('''
        def merge(base, override):
            result = base.copy()
            for key, value in override.items():
                if isinstance(value, dict) and isinstance(result.get(key), dict):
                    result[key].update(value)
                else:
                    result[key] = value
            return result
     '''), "settings.py": code('''
        from merge import merge

        def load_settings(defaults, overrides, environ):
            result = merge(defaults, overrides)
            if 'APP_ENABLED' in environ:
                result['enabled'] = bool(environ['APP_ENABLED'])
            return result
     ''')},
     code('''
        from settings import load_settings

        def test_recursive_and_no_mutation():
            defaults = {'db': {'pool': {'min': 1, 'max': 5}}}
            result = load_settings(defaults, {'db': {'pool': {'max': 9}}}, {})
            assert result == {'db': {'pool': {'min': 1, 'max': 9}}}
            assert defaults == {'db': {'pool': {'min': 1, 'max': 5}}}

        def test_false():
            assert load_settings({'enabled': True}, {}, {'APP_ENABLED': 'false'})['enabled'] is False
     '''),
     code('''
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
     '''),
     [("merge.py", "def merge(base, override):", "from copy import deepcopy\n\ndef merge(base, override):"),
      ("merge.py", "result = base.copy()", "result = deepcopy(base)"),
      ("merge.py", "result[key].update(value)", "result[key] = merge(result[key], value)"),
      ("merge.py", "result[key] = value", "result[key] = deepcopy(value)"),
      ("settings.py", "        result['enabled'] = bool(environ['APP_ENABLED'])",
       "        value = environ['APP_ENABLED'].strip().lower()\n        if value not in {'true', 'false'}:\n            raise ValueError('invalid boolean')\n        result['enabled'] = value == 'true'")]),
    ("12_atomic_transfers", "extended", "apply_batch(accounts, transfers) must atomically apply an ordered sequence of (source, destination, amount) transfers. All names must exist, amounts must be positive, and each transfer must have sufficient funds at its point in the sequence. On any error, preserve the entire original mapping. Keep the caller's mapping identity, return None on success, and allow funded positive self-transfers as no-ops. transfer itself must reject nonpositive amounts before changing balances.",
     {"ledger.py": code('''
        def transfer(accounts, source, destination, amount):
            if accounts[source] < amount:
                raise ValueError('insufficient funds')
            accounts[source] -= amount
            accounts[destination] += amount
     '''), "batch.py": code('''
        from ledger import transfer

        def apply_batch(accounts, transfers):
            for source, destination, amount in transfers:
                transfer(accounts, source, destination, amount)
     ''')},
     code('''
        import pytest
        from batch import apply_batch

        def test_rollback_late_failure():
            balances = {'a': 10, 'b': 0}
            with pytest.raises(ValueError): apply_batch(balances, [('a', 'b', 5), ('a', 'b', 6)])
            assert balances == {'a': 10, 'b': 0}

        def test_ordered_success():
            balances = {'a': 10, 'b': 0, 'c': 0}
            assert apply_batch(balances, [('a', 'b', 5), ('b', 'c', 3)]) is None
            assert balances == {'a': 5, 'b': 2, 'c': 3}
     '''),
     code('''
        import pytest
        from batch import apply_batch
        from ledger import transfer

        def test_unknown_destination():
            accounts = {'a': 10}
            with pytest.raises(KeyError): apply_batch(accounts, [('a', 'missing', 1)])
            assert accounts == {'a': 10}

        @pytest.mark.parametrize('amount', [0, -2])
        def test_invalid_amount(amount):
            accounts = {'a': 10, 'b': 0}
            with pytest.raises(ValueError): transfer(accounts, 'a', 'b', amount)
            assert accounts == {'a': 10, 'b': 0}

        def test_identity_self_and_empty():
            accounts = {'a': 10}
            alias = accounts
            apply_batch(accounts, [('a', 'a', 4)])
            apply_batch(accounts, [])
            assert accounts is alias and accounts == {'a': 10}
     '''),
     [("ledger.py", "    if accounts[source] < amount:", "    if amount <= 0:\n        raise ValueError('amount must be positive')\n    if accounts[source] < amount:"),
      ("batch.py", "    for source, destination, amount in transfers:\n        transfer(accounts, source, destination, amount)",
       "    working = accounts.copy()\n    for source, destination, amount in transfers:\n        transfer(working, source, destination, amount)\n    accounts.clear()\n    accounts.update(working)")]),
    ("13_tenant_cache", "extended", "Cache must isolate tenant/key pairs, expire entries when now >= expires_at, and preserve values as snapshots: mutating a value after put or a retrieved value after get must not mutate the stored data, including nested containers. Store None as a valid cached value. get returns its default for missing/expired entries. A zero TTL expires immediately. Time is passed explicitly; do not use system time.",
     {"keys.py": code('''
        def cache_key(tenant, key):
            return key
     '''), "expiry.py": code('''
        def expired(now, expires_at):
            return now > expires_at
     '''), "cache.py": code('''
        from keys import cache_key
        from expiry import expired

        class Cache:
            def __init__(self):
                self.entries = {}

            def put(self, tenant, key, value, now, ttl):
                self.entries[cache_key(tenant, key)] = (value, now + ttl)

            def get(self, tenant, key, now, default=None):
                entry = self.entries.get(cache_key(tenant, key))
                if entry is None or expired(now, entry[1]):
                    return default
                return entry[0]
     ''')},
     code('''
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
     '''),
     code('''
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
     '''),
     [("keys.py", "return key", "return (tenant, key)"),
      ("expiry.py", "now > expires_at", "now >= expires_at"),
      ("cache.py", "from keys import cache_key", "from copy import deepcopy\nfrom keys import cache_key"),
      ("cache.py", "= (value, now + ttl)", "= (deepcopy(value), now + ttl)"),
      ("cache.py", "return entry[0]", "return deepcopy(entry[0])")]),
]


if __name__ == "__main__":
    fixtures.generate(Path(__file__).resolve().parents[1] / "benchmarks_extended")
