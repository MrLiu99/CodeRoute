from retry import retry

def test_transient():
    calls = []
    def operation():
        calls.append(1)
        if len(calls) == 1: raise OSError('temporary')
        return 'ok'
    assert retry(operation) == 'ok'
    assert len(calls) == 2
