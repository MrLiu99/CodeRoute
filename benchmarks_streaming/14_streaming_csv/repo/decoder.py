def decode_chunks(chunks):
    for chunk in chunks:
        yield chunk.decode('utf-8')
