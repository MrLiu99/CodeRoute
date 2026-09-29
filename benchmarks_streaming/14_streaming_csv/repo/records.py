def parse_records(parts):
    for part in parts:
        for line in part.splitlines():
            if line:
                yield [field or None for field in line.split(',')]
