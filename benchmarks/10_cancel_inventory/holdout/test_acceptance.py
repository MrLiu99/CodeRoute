import pytest
from inventory import Inventory

def test_multiple_and_repeat():
    inventory=Inventory(5)
    inventory.book('a',2)
    inventory.book('b',1)
    inventory.cancel('a')
    inventory.cancel('a')
    inventory.cancel('unknown')
    assert inventory.available==4
    assert inventory.bookings=={'b':1}

def test_invalid_booking():
    inventory=Inventory(3)
    inventory.book('a',2)
    with pytest.raises(ValueError): inventory.book('a',1)
    with pytest.raises(ValueError): inventory.book('b',2)
    assert inventory.available==1
