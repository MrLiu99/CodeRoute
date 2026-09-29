import pytest
from stats import weighted_mean

@pytest.mark.parametrize('values,weights', [([],[]),([1],[1,2]),([1,2],[0,0])])
def test_invalid(values,weights):
    with pytest.raises(ValueError): weighted_mean(values,weights)

def test_zero_item():
    assert weighted_mean([99,4],[0,2]) == 4
