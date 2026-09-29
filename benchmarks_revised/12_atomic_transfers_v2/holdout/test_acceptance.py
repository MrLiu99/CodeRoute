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
