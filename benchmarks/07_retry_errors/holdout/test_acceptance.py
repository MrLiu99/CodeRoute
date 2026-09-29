import pytest
from retry import retry

@pytest.mark.parametrize('error,count', [(OSError,3),(ValueError,1),(TypeError,1)])
def test_attempts(error,count):
    calls=[]
    def operation():
        calls.append(1)
        raise error('broken')
    with pytest.raises(error): retry(operation,3)
    assert len(calls)==count

def test_invalid():
    with pytest.raises(ValueError): retry(lambda: 1,0)
