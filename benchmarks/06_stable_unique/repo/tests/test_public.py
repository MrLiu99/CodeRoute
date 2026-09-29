from unique import unique

def test_order():
    assert unique([3,1,3,2]) == [3,1,2]
