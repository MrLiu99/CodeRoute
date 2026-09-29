from unique import unique

def test_mixed():
    assert unique(['x', 1, 'x', None]) == ['x', 1, None]

def test_input_preserved():
    items = [2,1,2]
    assert unique(items) == [2,1]
    assert items == [2,1,2]
    assert unique([]) == []
