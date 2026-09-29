from keys import cache_key
from expiry import expired

class Cache:
    def __init__(self):
        self.entries = {}

    def put(self, tenant, key, value, now, ttl):
        self.entries[cache_key(tenant, key)] = (value, now + ttl)

    def get(self, tenant, key, now, default=None):
        entry = self.entries.get(cache_key(tenant, key))
        if entry is None or expired(now, entry[1]):
            return default
        return entry[0]
