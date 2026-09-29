from inventory import Inventory

def test_restore():
    inventory=Inventory(5)
    inventory.book('a',2)
    inventory.cancel('a')
    assert inventory.available == 5
