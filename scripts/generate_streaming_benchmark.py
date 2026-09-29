"""Streaming parser fixture with ordinary public regressions, no forced failures."""
from pathlib import Path
from textwrap import dedent

import generate_benchmarks as fixtures


def code(value):
    return dedent(value).lstrip()


decoder = code('''
    def decode_chunks(chunks):
        for chunk in chunks:
            yield chunk.decode('utf-8')
''')
parser = code('''
    def parse_records(parts):
        for part in parts:
            for line in part.splitlines():
                if line:
                    yield [field or None for field in line.split(',')]
''')
reader = code('''
    from decoder import decode_chunks
    from records import parse_records

    def read_rows(chunks):
        yield from parse_records(decode_chunks(chunks))
''')
fixed_decoder = code('''
    import codecs

    def decode_chunks(chunks):
        decoder = codecs.getincrementaldecoder('utf-8-sig')()
        for chunk in chunks:
            yield decoder.decode(chunk)
        tail = decoder.decode(b'', final=True)
        if tail:
            yield tail
''')
fixed_parser = code('''
    def parse_records(parts):
        fields, text = [], []
        state = 'start'
        after_cr = False
        for part in parts:
            for char in part:
                if after_cr:
                    after_cr = False
                    if char == '\\n':
                        continue
                if state == 'quoted':
                    if char == '"':
                        state = 'closed'
                    else:
                        text.append(char)
                    continue
                if state == 'closed' and char == '"':
                    text.append('"')
                    state = 'quoted'
                    continue
                if char == ',':
                    fields.append(''.join(text) if state != 'start' else None)
                    text, state = [], 'start'
                elif char in '\\r\\n':
                    if state != 'start' or fields:
                        fields.append(''.join(text) if state != 'start' else None)
                        yield fields
                    fields, text, state = [], [], 'start'
                    after_cr = char == '\\r'
                elif state == 'closed':
                    raise ValueError('characters after closing quote')
                elif char == '"':
                    if state != 'start':
                        raise ValueError('quote in unquoted field')
                    state = 'quoted'
                else:
                    text.append(char)
                    state = 'bare'
        if state == 'quoted':
            raise ValueError('unterminated quoted field')
        if state != 'start' or fields:
            fields.append(''.join(text) if state != 'start' else None)
            yield fields
''')
public = code(r'''
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
''')
holdout = code(r'''
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
''')

fixtures.CASES = [(
    '14_streaming_csv', 'hard',
    'Repair read_rows(chunks), decode_chunks(chunks), and parse_records(parts). '
    'Input chunks are arbitrary bytes including empty chunks; decode UTF-8 incrementally, strip only an initial BOM, '
    'and raise UnicodeDecodeError for invalid or incomplete UTF-8. decode_chunks yields text fragments; '
    'parse_records accepts arbitrary text fragments and yields lists of fields. '
    'CSV uses comma delimiters, double-quoted fields, doubled quotes as escapes, and CR/LF/CRLF record separators. '
    'Preserve CR/LF literally inside quoted fields. Unquoted empty fields are None; quoted empty fields are empty strings. '
    'Preserve whitespace. Quotes may start only at field start; after a closing quote only delimiter, record separator or EOF is valid. '
    'Malformed quotes raise ValueError. Skip blank physical records outside quotes, preserve trailing empty fields, '
    'and accept a final record without a terminator. Chunk boundaries must not affect results. '
    'All helpers remain lazy: yield each complete row before requesting the next input chunk or parsing later text, '
    'including when later text in the same chunk has malformed CSV syntax. Do not collect the entire stream. '
    'The three helper contracts are public; preserve them.',
    {'decoder.py': decoder, 'records.py': parser, 'reader.py': reader},
    public, holdout,
    [('decoder.py', decoder, fixed_decoder), ('records.py', parser, fixed_parser)]
)]


if __name__ == '__main__':
    fixtures.generate(Path(__file__).resolve().parents[1] / 'benchmarks_streaming')
