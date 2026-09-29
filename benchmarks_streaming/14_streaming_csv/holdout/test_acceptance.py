import pytest
from decoder import decode_chunks
from records import parse_records
from reader import read_rows

def test_all_two_way_splits():
    data = '\ufeff"猫","a""b"\r\n, "space"\n'.encode('utf-8')
    # The quote after a leading space is invalid, independent of chunking.
    for split in range(len(data)+1):
        with pytest.raises(ValueError):
            list(read_rows([data[:split], b'', data[split:]]))
    data = '\ufeff"猫","a""b"\r\n,""\rZ,\n'.encode('utf-8')
    for split in range(len(data)+1):
        assert list(read_rows([data[:split], b'', data[split:]])) == [['猫', 'a"b'], [None, ''], ['Z', None]]

def test_public_helper_contracts():
    assert ''.join(decode_chunks([b'\xef', b'\xbb\xbf', b'\xe7', b'\x8c\xab'])) == '猫'
    assert list(parse_records(['"a', '""', 'b",', 'c\r', '\n'])) == [['a"b', 'c']]

def test_first_row_before_later_syntax_error_in_same_chunk():
    rows = read_rows([b'ok,yes\n"broken'])
    assert next(rows) == ['ok', 'yes']
    with pytest.raises(ValueError):
        next(rows)

@pytest.mark.parametrize('data', [b'\xe7', b'\xff'])
def test_invalid_utf8(data):
    with pytest.raises(UnicodeDecodeError):
        list(read_rows([data]))

def test_empty_and_preserved_whitespace():
    assert list(read_rows([])) == []
    assert list(read_rows([b'', b'\r', b'\n'])) == []
    assert list(read_rows([b' a ," b "\n""'])) == [[' a ', ' b '], ['']]
