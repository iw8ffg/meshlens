"""Aggregati orari del traffico: pacchetti e ricezioni per tipo, pacchetti e SNR per nodo.

Gira sul thread del loop: conta in memoria e `flush` (ogni 60 s) somma i contatori nel
database. Non fa commit."""
from .events import MeshEvent
from .store import Store


class NetStats:
    def __init__(self, store: Store):
        self.store = store
        self._stats: dict[tuple[int, str, str], list[int]] = {}  # -> [packets, receptions]
        # (hour, node, source) -> [packets, snr_sum, snr_n, snr_max]
        self._nodes: dict[tuple[int, int, str], list] = {}

    def observe(self, ev: MeshEvent, outcome: str, archived: bool) -> None:
        # come il PacketLog: niente replay del database nodi ne' rigiochi S&F
        if outcome == "ignored" or not ev.packet_id or ev.rx_time <= 0 or ev.replayed:
            return
        new = outcome == "new"
        hour = int(ev.rx_time // 3600) * 3600
        s = self._stats.setdefault((hour, ev.source, ev.kind), [0, 0])
        s[0] += new
        s[1] += 1
        if not archived or (not new and ev.snr is None):
            return
        n = self._nodes.setdefault((hour, ev.from_node, ev.source), [0, 0.0, 0, None])
        n[0] += new
        if ev.snr is not None:
            n[1] += ev.snr
            n[2] += 1
            n[3] = ev.snr if n[3] is None else max(n[3], ev.snr)

    def flush(self) -> int:
        # ogni gruppo si azzera solo dopo la scrittura riuscita (la somma nel database e'
        # additiva: un gruppo gia' scritto non va riscritto al tentativo successivo)
        stats, nodes = self._stats, self._nodes
        self.store.upsert_stats_hourly([(*k, *v) for k, v in stats.items()])
        self._stats = {}
        self.store.upsert_node_hourly([(*k, *v) for k, v in nodes.items()])
        self._nodes = {}
        return len(stats) + len(nodes)
