class Cache:
    def __init__(self):
        self.data = {}

    def get_or_compute(self, key, compute):
        value = self.data.get(key)
        if not value:
            value = compute()
            self.data[key] = value
        return value
