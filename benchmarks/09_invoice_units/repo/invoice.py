from taxes import tax_amount

def invoice_total(prices_cents, rate):
    subtotal = sum(prices_cents)
    return subtotal / 100 + tax_amount(subtotal, rate)
