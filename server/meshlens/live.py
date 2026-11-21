"""Stato in memoria: nodi, ultimi messaggi, nodi modificati da inviare ai client."""
import collections


class LiveState:
    def __init__(self, max_messages: int = 2000):
        self.nodes: dict[int, dict] = {}
        self.messages: collections.deque = collections.deque(maxlen=max_messages)
        self._changed: set[int] = set()

    def load(self, nodes: list[dict]) -> None:
        for node in nodes:
            self.nodes[node["num"]] = node

    def mark_changed(self, num: int) -> None:
        self._changed.add(num)

    def take_changed(self) -> list[dict]:
        changed = [self.nodes[n] for n in self._changed if n in self.nodes]
        self._changed.clear()
        return changed

    def evict_older_than(self, cutoff: float) -> int:
        """Rimuove i nodi non sentiti dopo `cutoff` (esclusi i propri e i preferiti). Ritorna quanti."""
        stale = [n for n, node in self.nodes.items()
                 if (node.get("last_heard") or 0) < cutoff and not node.get("is_mine")
                 and not node.get("is_favorite")]
        for n in stale:
            del self.nodes[n]
            self._changed.discard(n)
        return len(stale)
