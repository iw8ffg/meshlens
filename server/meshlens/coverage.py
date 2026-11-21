"""Prove di copertura: calcoli puri e registratore delle sessioni."""
import math
import time

from .events import MeshEvent, PositionData, RangeTestData, node_id

MAX_GAP_S = 120
SESSION_MAX_S = 8 * 3600  # il firmware spegne il mittente dopo 8 h


def precision_m(bits: int | None) -> int | None:
    """Raggio di incertezza in metri; None se la posizione e' esatta."""
    if bits is None or bits >= 32:
        return None
    return round(2 ** (32 - bits) * 1e-7 * 111320 / 2)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (math.sin((p2 - p1) / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2)
    return 2 * 6371000 * math.asin(math.sqrt(a))


def interpolate_position(track: list[dict], t: float,
                         max_gap: float = MAX_GAP_S) -> tuple[float, float, int | None] | None:
    """Posizione del mobile all'istante t: interpolata, oppure la piu' vicina, oppure None."""
    prev = nxt = None
    for p in track:  # percorso ordinato per tempo
        if p["time"] <= t:
            prev = p
        else:
            nxt = p
            break
    near_prev = prev is not None and t - prev["time"] <= max_gap
    near_next = nxt is not None and nxt["time"] - t <= max_gap
    if near_prev and near_next:
        span = nxt["time"] - prev["time"]
        f = (t - prev["time"]) / span if span else 0.0
        raw = (prev["precision_bits"], nxt["precision_bits"])
        bits = None if raw == (None, None) else min(b if b is not None else 32 for b in raw)
        return (prev["lat"] + (nxt["lat"] - prev["lat"]) * f,
                prev["lon"] + (nxt["lon"] - prev["lon"]) * f, bits)
    if near_prev and (not near_next or t - prev["time"] <= nxt["time"] - t):
        return prev["lat"], prev["lon"], prev["precision_bits"]
    if near_next:
        return nxt["lat"], nxt["lon"], nxt["precision_bits"]
    return None


def missing_points(points: list[dict], interval_s: int, track: list[dict]) -> list[dict]:
    """Seq assenti tra il minimo e il massimo ricevuti, per tratto."""
    segments: dict[int, dict[int, dict]] = {}
    for p in points:
        if p.get("seq") is not None:
            segments.setdefault(p["segment"], {})[p["seq"]] = p
    out = []
    for seg in sorted(segments):
        by_seq = segments[seg]
        if len(by_seq) < 2:
            continue
        seqs = sorted(by_seq)
        for s in range(seqs[0] + 1, seqs[-1]):
            if s in by_seq:
                continue
            before = max(q for q in seqs if q < s)
            after = min(q for q in seqs if q > s)
            tb, ta = by_seq[before]["time"], by_seq[after]["time"]
            t = tb + (ta - tb) * (s - before) / (after - before)
            pos = interpolate_position(track, t)
            out.append({"seq": s, "time": t, "lat": pos[0] if pos else None,
                        "lon": pos[1] if pos else None})
    return out


def summarize(session: dict, points: list[dict], missing: list[dict]) -> dict:
    rangetest = session["mode"] == "rangetest"
    received = len(points)
    expected = received + len(missing) if rangetest else None
    snrs = [p["snr"] for p in points if p.get("snr") is not None]
    radii = [precision_m(p.get("precision_bits")) for p in points]
    radii = [r for r in radii if r is not None]
    dists = []
    if session.get("base_lat") is not None and session.get("base_lon") is not None:
        dists = [haversine_m(session["base_lat"], session["base_lon"], p["lat"], p["lon"])
                 for p in points if p.get("lat") is not None]
    return {
        "id": session.get("id"), "name": session.get("name"), "radio_id": session.get("radio_id"),
        "mobile_id": node_id(session["mobile_num"]), "mode": session["mode"],
        "channel_index": session.get("channel_index"), "interval_s": session.get("interval_s"),
        "started": session.get("started"), "ended": session.get("ended"),
        "end_reason": session.get("end_reason"), "base_lat": session.get("base_lat"),
        "base_lon": session.get("base_lon"), "notes": session.get("notes"),
        "received": received, "expected": expected,
        "missing": len(missing) if rangetest else None,
        "loss_pct": (round(100 * len(missing) / expected, 1) if rangetest and expected else None),
        "best_snr": max(snrs) if snrs else None, "worst_snr": min(snrs) if snrs else None,
        "max_distance_m": max(dists) if dists else None,
        "approx_precision_m": max(radii) if radii else None,
    }


class SessionActive(RuntimeError):
    pass


class CoverageRecorder:
    def __init__(self, store, live, bus, clock=time.time, radio_node=None):
        self.store = store
        self.live = live
        self.bus = bus
        self._clock = clock
        self._radio_node = radio_node or (lambda radio_id: None)  # radio_id -> num del nodo
        self._rt_seen: dict[tuple[str | None, int], float] = {}
        self._session: dict | None = None
        self._track: list[dict] = []
        self._segment = 0
        self._last_seq: int | None = None

    def start(self) -> None:
        """Riprende la sessione attiva, il suo tratto e l'ultimo seq."""
        self._session = self.store.active_session()
        self._track, self._segment, self._last_seq = [], 0, None
        if self._session is None:
            return
        sid = self._session["id"]
        self._track = self.store.track(sid)
        for p in self.store.points(sid):  # ordinati per tempo
            if p["seq"] is not None:
                self._segment, self._last_seq = p["segment"], p["seq"]

    # ---- sessioni -----------------------------------------------------
    def _summary(self, session: dict) -> dict:
        points = self.store.points(session["id"])
        track = self._track if self._session and self._session["id"] == session["id"] \
            else self.store.track(session["id"])
        missing = (missing_points(points, session["interval_s"], track)
                   if session["mode"] == "rangetest" else [])
        return summarize(session, points, missing)

    def summary(self, session: dict) -> dict:
        return self._summary(session)

    def update_session(self, sid: int, **fields) -> dict:
        """Modifica nome, note o base; aggiorna anche la copia in memoria se e' attiva."""
        self.store.update_session(sid, **fields)
        self.store.commit()
        s = self.store.get_session(sid)
        if self._session is not None and self._session["id"] == sid:
            self._session = s
        return self._summary(s)

    def _publish(self, session: dict, point: dict | None = None) -> None:
        self.bus.publish({"type": "coverage", "session": self._summary(session), "point": point})

    def start_session(self, radio_id: str, mobile_num: int, mode: str = "rangetest",
                      interval_s: int = 30, name: str | None = None,
                      base_lat: float | None = None, base_lon: float | None = None,
                      channel_index: int | None = None) -> dict:
        if self._session is not None:
            raise SessionActive("C'è già una sessione in corso")
        if base_lat is None or base_lon is None:
            node = self.live.nodes.get(self._radio_node(radio_id) or -1)
            if node and node.get("lat") is not None:
                base_lat, base_lon = node["lat"], node["lon"]
        now = self._clock()
        if not name:
            name = "Prova " + time.strftime("%d/%m %H:%M", time.localtime(now))
        sid = self.store.create_session(
            name=name, radio_id=radio_id, mobile_num=mobile_num, mode=mode,
            channel_index=channel_index, interval_s=interval_s, started=now,
            base_lat=base_lat, base_lon=base_lon)
        self.store.commit()
        self._session = self.store.get_session(sid)
        self._track, self._segment, self._last_seq = [], 0, None
        self._publish(self._session)
        return self._summary(self._session)

    def stop_session(self, reason: str = "manual") -> dict | None:
        s = self._session
        if s is None:
            return None
        self.store.update_session(s["id"], ended=self._clock(), end_reason=reason)
        self.store.commit()
        summary = self._summary(self.store.get_session(s["id"]))
        self._session = None
        self.bus.publish({"type": "coverage", "session": summary, "point": None})
        return summary

    def tick(self) -> None:
        s = self._session
        if s is not None and self._clock() - s["started"] >= SESSION_MAX_S:
            self.stop_session("timeout")

    def detail(self, sid: int) -> dict:
        s = self.store.get_session(sid)
        points = self.store.points(sid)
        track = self.store.track(sid)
        missing = (missing_points(points, s["interval_s"], track)
                   if s["mode"] == "rangetest" else [])
        out = summarize(s, points, missing)
        out["points"] = [self._point_json(s, p) for p in points]
        out["missing_points"] = missing
        out["track"] = [{"time": t["time"], "lat": t["lat"], "lon": t["lon"],
                         "precision_bits": t["precision_bits"]} for t in track]
        return out

    @staticmethod
    def _point_json(s: dict, p: dict) -> dict:
        has_base = s["base_lat"] is not None and s["base_lon"] is not None
        return {"id": p["id"], "segment": p["segment"], "seq": p["seq"], "time": p["time"],
                "snr": p["snr"], "rssi": p["rssi"], "hops": p["hops"], "lat": p["lat"],
                "lon": p["lon"], "precision_bits": p["precision_bits"],
                "distance_m": (haversine_m(s["base_lat"], s["base_lon"], p["lat"], p["lon"])
                               if has_base and p["lat"] is not None else None)}

    def rangetest_age(self, radio_id: str, mobile_num: int) -> float | None:
        seen = self._rt_seen.get((radio_id, mobile_num))
        return None if seen is None else self._clock() - seen

    # ---- eventi -------------------------------------------------------
    def handle(self, ev: MeshEvent) -> None:
        now = ev.rx_time if ev.rx_time and ev.rx_time > 0 else self._clock()
        if ev.kind == "rangetest":
            # anche con testo non valido o fuori sessione: dimostra che il modulo e' attivo
            self._rt_seen[(ev.radio_id, ev.from_node)] = now
        s = self._session
        if s is None or ev.from_node != s["mobile_num"]:
            return
        mine = ev.source == "rf" and ev.radio_id == s["radio_id"]
        if ev.kind == "position" and isinstance(ev.payload, PositionData):
            self._on_position(s, ev, now, mine)
        elif (ev.kind == "rangetest" and isinstance(ev.payload, RangeTestData)
              and s["mode"] == "rangetest" and mine and ev.payload.seq is not None):
            if self._last_seq is not None and ev.payload.seq < self._last_seq:
                self._segment += 1  # il mobile e' ripartito da 0
            self._last_seq = ev.payload.seq
            self._add_point(s, ev, ev.payload.seq, now,
                            interpolate_position(self._track, now))

    def _add_point(self, s: dict, ev: MeshEvent, seq: int | None, now: float, pos) -> None:
        lat, lon, bits = pos if pos else (None, None, None)
        new = self.store.add_point(s["id"], self._segment, seq, now, ev.snr, ev.rssi, ev.hops,
                                   lat, lon, bits)
        self.store.commit()  # scrittura durevole; un doppione puo' aver migliorato l'SNR
        if not new:
            return
        pid = self.store.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        row = {"id": pid, "segment": self._segment, "seq": seq, "time": now, "snr": ev.snr,
               "rssi": ev.rssi, "hops": ev.hops, "lat": lat, "lon": lon, "precision_bits": bits}
        self._publish(s, self._point_json(s, row))

    def _on_position(self, s: dict, ev: MeshEvent, now: float, mine: bool) -> None:
        p = ev.payload
        last = self._track[-1] if self._track else None
        if last and (last["time"], last["lat"], last["lon"]) == (now, p.lat, p.lon):
            return  # copia identica (MQTT + RF)
        self.store.add_track(s["id"], now, p.lat, p.lon, p.precision_bits)
        self._track.append({"time": now, "lat": p.lat, "lon": p.lon,
                            "precision_bits": p.precision_bits})
        self._track.sort(key=lambda t: t["time"])
        if s["mode"] == "position" and mine:
            self._add_point(s, ev, None, now, (p.lat, p.lon, p.precision_bits))
        # completa e affina i punti degli ultimi 120 s e li ripubblica
        updated = []
        for pt in self.store.points_since(s["id"], now - MAX_GAP_S):
            if pt["time"] > now:
                continue
            pos = interpolate_position(self._track, pt["time"])
            if pos and pos != (pt["lat"], pt["lon"], pt["precision_bits"]):
                self.store.update_point_position(pt["id"], *pos)
                updated.append(pt | {"lat": pos[0], "lon": pos[1], "precision_bits": pos[2]})
        self.store.commit()
        if updated:
            summary = self._summary(s)
            for pt in updated:
                self.bus.publish({"type": "coverage", "session": summary,
                                  "point": self._point_json(s, pt)})
