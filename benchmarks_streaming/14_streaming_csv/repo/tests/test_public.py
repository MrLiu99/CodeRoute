import pytest
from reader import read_rows

def test_chunk_boundaries_and_unicode():
    data = 'name,value\r\n猫,"a,b"\r\n'.encode('utf-8')
    assert list(read_rows([data[i:i+1] for i in range(len(data))])) == [['name', 'value'], ['猫', 'a,b']]

def test_quotes_nulls_and_multiline():
    data = b',"",x\r\n"a""b","line1\r\nline2",\r\n'
    assert list(read_rows([data])) == [[None, '', 'x'], ['a"b', 'line1\r\nline2', None]]

@pytest.mark.parametrize('data', [b'"open', b'ba"d,x', b'"x"tail,y'])
def test_strict_syntax(data):
    with pytest.raises(ValueError):
        list(read_rows([data]))

def test_yields_before_reading_next_chunk():
    def chunks():
        yield b'a,b\n'
        raise AssertionError('read ahead')
    assert next(read_rows(chunks())) == ['a', 'b']

def test_blank_lines_and_final_record():
    assert list(read_rows([b'\r\n\n,\rx,y'])) == [[None, None], ['x', 'y']]
