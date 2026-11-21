"""Registro dei pacchetti per l'ispettore: le copie dello stesso pacchetto diventano una riga.

Gira sul thread del loop. Le voci restano in un buffer limitato per HOLD_S secondi, cosi'
le copie arrivate da altri gateway o radio si uniscono alla prima; poi `flush` le scrive a
blocchi (il commit lo fa il task periodico del Runtime)."""
import dataclasses
import json
import math
import time
from typing import Callable

from .events import RAW_MAX, MeshEvent, RawPacket
from .store import Store

HOLD_S = 5.0
BUFFER_MAX = 20_000
FLUSH_MAX = 2000
MAX_RECEPTIONS = 8
PACKETS_MAX_ROWS = 300_000
SUMMARY_MAX = 2000
TEXT_MAX = 200


def _clean(v):
    if isinstance(v, (bytes, bytearray)):
        return bytes(v).hex()
    if isinstance(v, float) and not math.isfinite(v):
        return None  # JSON valido: niente NaN/Infinity
    if isinstance(v, dict):
        return {k: _clean(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    return v


def summarize(ev: MeshEvent) -> dict:
    """Contenuto decodificato dell'evento, pronto per JSON (byte in esadecimale)."""
    out = _clean(dataclasses.asdict(ev.payload))
    if isinstance(out.get("text"), str):
        out["text"] = out["text"][:TEXT_MAX]
    return out


def _hops(hop_start: int | None, hop_limit: int | None) -> int | None:
    if hop_start is None or hop_limit is None or hop_start < hop_limit:
        return None
    return hop_start - hop_limit


def _reception(p: MeshEvent | RawPacket, hops: int | None) -> dict:
    return {"source": p.source, "broker": p.broker, "radio_id": p.radio_id,
            "gateway": p.gateway_id, "snr": p.snr, "rssi": p.rssi, "hops": hops,
            "relay_node": p.relay_node, "time": p.rx_time}


class PacketLog:
    def __init__(self, store: Store, get_mode: Callable[[], str], clock=time.time):
        self.store = store
        self.get_mode = get_mode
        self.clock = clock
        self.dropped = 0  # voci tolte dal buffer pieno prima di essere scritte
        # (from, packet_id) -> voce; i dict tengono l'ordine d'inserimento
        self._buf: dict[tuple[int, int], dict] = {}

    def _wanted(self, p: MeshEvent | RawPacket, archived: bool) -> bool:
        mode = self.get_mode()
        if mode == "off" or (mode != "all" and not archived):
            return False
        # replay del database nodi (senza id o senza ora) e rigiochi S&F: non e' traffico
        return bool(p.packet_id) and p.rx_time > 0 and not getattr(p, "replayed", False)

    def _add(self, key: tuple[int, int], entry: dict) -> None:
        while len(self._buf) >= BUFFER_MAX:
            del self._buf[next(iter(self._buf))]
            self.dropped += 1
        self._buf[key] = entry

    @staticmethod
    def _merge(entry: dict, rec: dict) -> None:
        entry["copies"] += 1
        if len(entry["_recs"]) < MAX_RECEPTIONS:
            entry["_recs"].append(rec)

    def _entry(self, p: MeshEvent | RawPacket, hops: int | None) -> dict:
        meta = p.meta
        raw = bytes(meta.raw[:RAW_MAX]) if meta is not None else b""
        return {"time": p.rx_time, "from_num": p.from_node, "to_num": p.to_node,
                "packet_id": p.packet_id, "source": p.source, "broker": p.broker,
                "radio_id": p.radio_id, "channel": p.channel,
                "portnum": meta.portnum if meta else None, "snr": p.snr, "rssi": p.rssi,
                "hops": hops, "hop_start": meta.hop_start if meta else None,
                "hop_limit": meta.hop_limit if meta else None, "relay_node": p.relay_node,
                "gateway": p.gateway_id, "copies": 1, "raw": raw, "size": len(raw),
                "_recs": [_reception(p, hops)], "_born": self.clock()}

    def observe(self, ev: MeshEvent, outcome: str, archived: bool) -> None:
        if outcome == "ignored" or not self._wanted(ev, archived):
            return
        key = (ev.from_node, ev.packet_id)
        entry = self._buf.get(key)
        if outcome == "dup":
            if entry is not None:  # copia tardiva gia' scritta: ignorata
                self._merge(entry, _reception(ev, ev.hops))
            return
        decoded = {"status": "ok", "kind": ev.kind,
                   "summary": json.dumps(summarize(ev), ensure_ascii=False)[:SUMMARY_MAX]}
        if entry is not None:  # prima arrivata non decodificata (altro broker): si completa
            self._merge(entry, _reception(ev, ev.hops))
            entry.update(decoded)
            if ev.meta is not None:
                raw = bytes(ev.meta.raw[:RAW_MAX])
                entry.update(portnum=ev.meta.portnum, raw=raw, size=len(raw))
            return
        self._add(key, {**self._entry(ev, ev.hops), **decoded})

    def observe_raw(self, raw: RawPacket, archived: bool) -> None:
        if not self._wanted(raw, archived):
            return
        hops = _hops(raw.meta.hop_start, raw.meta.hop_limit) if raw.meta else None
        key = (raw.from_node, raw.packet_id)
        entry = self._buf.get(key)
        if entry is not None:
            self._merge(entry, _reception(raw, hops))
            return
        self._add(key, {**self._entry(raw, hops), "status": raw.status, "kind": None,
                        "summary": None})

    def flush(self, now: float | None = None, force: bool = False) -> int:
        """Scrive le voci piu' vecchie di HOLD_S, al massimo FLUSH_MAX per chiamata;
        con `force` (chiusura) scrive tutto. Non fa commit."""
        now = self.clock() if now is None else now
        written = 0
        while self._buf:
            batch = []
            for key, entry in self._buf.items():
                if len(batch) >= FLUSH_MAX or (not force and now - entry["_born"] < HOLD_S):
                    break
                batch.append(key)
            if not batch:
                break
            rows = []
            for key in batch:
                entry = self._buf.pop(key)
                entry["receptions"] = json.dumps(entry.pop("_recs"), ensure_ascii=False)
                rows.append(entry)
            self.store.insert_packets(rows)
            written += len(rows)
            if not force:
                break
        return written
