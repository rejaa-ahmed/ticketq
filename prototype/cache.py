"""Cache layer: a tiny in-memory TTL cache standing in for Redis / ElastiCache."""
import threading
import time


class TTLCache:
    def __init__(self, ttl_seconds=30):
        self.ttl = ttl_seconds
        self._data = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if item and item[1] > time.time():
                self.hits += 1
                return item[0]
            self.misses += 1
            return None

    def set(self, key, value):
        with self._lock:
            self._data[key] = (value, time.time() + self.ttl)

    def invalidate(self, key):
        with self._lock:
            self._data.pop(key, None)


cache = TTLCache(ttl_seconds=30)
