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
