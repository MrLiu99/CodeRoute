def retry(operation, attempts=3):
    if attempts < 1:
        raise ValueError('attempts must be positive')
    for index in range(attempts):
        try:
            return operation()
        except ValueError:
            if index == attempts - 1:
                raise
