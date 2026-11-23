"""Stato in memoria: nodi, ultimi messaggi, nodi modificati da inviare ai client."""
import collections
import heapq

MAX_LIVE_NODES = 50_000
CAP_TARGET = 0.95  # oltre il limite si scende al 95 %, per non potare a ogni nodo nuovo


def _protected(node: dict) -> bool:
    # un nodo ignorato resta in memoria: tolto, riapparirebbe al prossimo pacchetto
    return (bool(node.get("is_mine")) or bool(node.get("is_favorite"))
            or bool(node.get("is_ignored")))


class LiveState:
    def __init__(self, max_messages: int = 2000, max_nodes: int = MAX_LIVE_NODES):
        self.nodes: dict[int, dict] = {}
        self.messages: collections.deque = collections.deque(maxlen=max_messages)
        self.max_nodes = max_nodes
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

    def _remove(self, nums: list[int]) -> int:
        for n in nums:
            del self.nodes[n]
            self._changed.discard(n)
        return len(nums)

    def evict_older_than(self, cutoff: float) -> int:
        """Rimuove i nodi non sentiti dopo `cutoff` (esclusi i propri e i preferiti). Ritorna quanti."""
        return self._remove([n for n, node in self.nodes.items()
                             if (node.get("last_heard") or 0) < cutoff and not _protected(node)])

    def enforce_cap(self) -> int:
        """Oltre `max_nodes` toglie i nodi sentiti meno di recente (esclusi propri e preferiti)
        fino al 95 % del limite. Ritorna quanti."""
        if len(self.nodes) <= self.max_nodes:
            return 0
        excess = len(self.nodes) - int(self.max_nodes * CAP_TARGET)
        candidates = ((node.get("last_heard") or 0, n) for n, node in self.nodes.items()
                      if not _protected(node))
        return self._remove([n for _, n in heapq.nsmallest(excess, candidates)])
