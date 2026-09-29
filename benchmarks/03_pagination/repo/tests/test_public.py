from pagination import page_items

def test_first():
    assert page_items([1,2,3,4], 1, 2) == [1,2]
