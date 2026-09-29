import pytest
from invoice import invoice_total
from taxes import tax_amount

def test_helper_contract():
    assert tax_amount(12,0.25) == 3

def test_totals():
    assert invoice_total([],0.2) == 0
    assert invoice_total([199,101],0) == 3
    assert invoice_total([100],0.2) == pytest.approx(1.2)
