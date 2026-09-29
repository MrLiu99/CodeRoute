def transfer(accounts, source, destination, amount):
    if accounts[source] < amount:
        raise ValueError('insufficient funds')
    accounts[source] -= amount
    accounts[destination] += amount
