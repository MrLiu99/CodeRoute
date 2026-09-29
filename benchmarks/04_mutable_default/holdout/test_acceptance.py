from tags import add_tag

def test_explicit_list():
    values = ['start']
    result = add_tag('next', values)
    assert result is values
    assert values == ['start', 'next']

def test_empty_list():
    values = []
    assert add_tag('x', values) is values
