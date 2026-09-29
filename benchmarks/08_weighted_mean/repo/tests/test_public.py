import pytest
from stats import weighted_mean

def test_weighted():
    assert weighted_mean([10,20],[1,3]) == pytest.approx(17.5)
