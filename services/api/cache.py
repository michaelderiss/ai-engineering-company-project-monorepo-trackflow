from collections import OrderedDict
import json
from threading import RLock
from time import monotonic

from fastapi.encoders import jsonable_encoder
from fastapi.responses import Response


class TTLCache:
    def __init__(self, ttl: float, max_entries: int, max_value_bytes: int):
        if ttl <= 0 or max_entries <= 0 or max_value_bytes <= 0:
            raise ValueError("Cache limits must be positive")
        self.ttl = ttl
        self.max_entries = max_entries
        self.max_value_bytes = max_value_bytes
        self._entries = OrderedDict()
        self._lock = RLock()

    def get_or_load(self, key, loader):
        with self._lock:
            now = monotonic()
            for expired_key in [key for key, (expiry, _) in self._entries.items() if expiry <= now]:
                del self._entries[expired_key]
            if key in self._entries:
                self._entries.move_to_end(key)
                return self._entries[key][1]
            value = loader()
            if len(value) <= self.max_value_bytes:
                self._entries[key] = (monotonic() + self.ttl, value)
                while len(self._entries) > self.max_entries:
                    self._entries.popitem(last=False)
            return value

    def clear(self):
        with self._lock:
            self._entries.clear()


catalog_cache = TTLCache(ttl=15, max_entries=4, max_value_bytes=1024 * 1024)
summary_cache = TTLCache(ttl=30, max_entries=128, max_value_bytes=16 * 1024)


def cached_json(cache, key, loader):
    body = cache.get_or_load(
        key,
        lambda: json.dumps(jsonable_encoder(loader()), separators=(",", ":"), allow_nan=False).encode(),
    )
    return Response(body, media_type="application/json", headers={"Cache-Control": "no-store"})