import pytest
from pagination import page_items

def test_later():
    assert page_items([1,2,3,4,5], 3, 2) == [5]
    assert page_items([1], 4, 2) == []

@pytest.mark.parametrize('page,size', [(0,2),(1,0),(-1,2)])
def test_invalid(page,size):
    with pytest.raises(ValueError): page_items([1], page, size)
