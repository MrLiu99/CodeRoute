from ledger import transfer

def apply_batch(accounts, transfers):
    for source, destination, amount in transfers:
        transfer(accounts, source, destination, amount)
