"""Deduplica i pacchetti Meshtastic gia' visti di recente, per (mittente, packet id)."""
from collections import OrderedDict

MAX_KEYS = 200_000


class Deduplicator:
    def __init__(self, window_s: float = 600):
        self.window_s = window_s
        # chiave (from, id) -> istante della prima vista; ordinato per tempo crescente
        self._seen: OrderedDict[tuple[int, int], float] = OrderedDict()

    def is_new(self, from_node: int, packet_id: int, now: float) -> bool:
        key = (from_node, packet_id)
        first_seen = self._seen.get(key)
        if first_seen is not None:
            if now - first_seen < self.window_s:
                return False
            # finestra scaduta: la chiave viene riammessa e riaccodata
            del self._seen[key]
        elif len(self._seen) >= MAX_KEYS:
            self._seen.popitem(last=False)
        self._seen[key] = now
        return True

    def prune(self, now: float) -> None:
        while self._seen:
            oldest_time = next(iter(self._seen.values()))
            if now - oldest_time < self.window_s:
                break
            self._seen.popitem(last=False)
