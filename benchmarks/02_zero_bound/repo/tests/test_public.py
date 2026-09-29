from bounds import clamp

def test_zero_lower():
    assert clamp(-3, lower=0) == 0

def test_normal():
    assert clamp(4, 1, 8) == 4
