"""Deduplica i pacchetti Meshtastic gia' visti di recente, per (mittente, packet id).
Unica per tutte le sorgenti (radio e broker): ricorda anche da quali sorgenti e' arrivato
ogni pacchetto, cosi' chi conta i gateway MQTT non tiene un secondo registro."""
from collections import OrderedDict

MAX_KEYS = 200_000
SOURCE_BITS = {"rf": 1, "mqtt": 2}


class Deduplicator:
    def __init__(self, window_s: float = 600):
        self.window_s = window_s
        # chiave (from, id) -> [istante della prima vista, bit delle sorgenti];
        # ordinato per prima vista crescente
        self._seen: OrderedDict[tuple[int, int], list] = OrderedDict()

    def observe(self, from_node: int, packet_id: int, now: float,
                source: str | None = None) -> tuple[bool, bool]:
        """(nuovo, gia' visto da questa sorgente). Senza sorgente non si segna nessun bit."""
        key = (from_node, packet_id)
        bit = SOURCE_BITS.get(source, 0) if source is not None else 0
        entry = self._seen.get(key)
        if entry is not None:
            if now - entry[0] < self.window_s:
                seen_before = bool(entry[1] & bit)
                entry[1] |= bit
                return False, seen_before
            # finestra scaduta: la chiave viene riammessa e riaccodata
            del self._seen[key]
        elif len(self._seen) >= MAX_KEYS:
            self._seen.popitem(last=False)
        self._seen[key] = [now, bit]
        return True, False

    def is_new(self, from_node: int, packet_id: int, now: float) -> bool:
        return self.observe(from_node, packet_id, now, None)[0]

    def prune(self, now: float) -> None:
        while self._seen:
            oldest_time = next(iter(self._seen.values()))[0]
            if now - oldest_time < self.window_s:
                break
            self._seen.popitem(last=False)
