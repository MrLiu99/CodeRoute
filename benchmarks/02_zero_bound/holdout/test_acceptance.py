from bounds import clamp

def test_zero_upper():
    assert clamp(3, upper=0) == 0

def test_absent():
    assert clamp(-5) == -5

def test_negative_bound():
    assert clamp(-8, lower=-3) == -3
