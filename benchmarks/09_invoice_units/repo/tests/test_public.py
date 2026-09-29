import pytest
from invoice import invoice_total

def test_invoice():
    assert invoice_total([1000,500],0.1) == pytest.approx(16.5)
