from decoder import decode_chunks
from records import parse_records

def read_rows(chunks):
    yield from parse_records(decode_chunks(chunks))
