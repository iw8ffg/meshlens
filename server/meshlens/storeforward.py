"""Store & Forward: router S&F sentiti dalle radio, richiesta dello storico e rigioco.

Il router rimanda i messaggi salvati come pacchetti STORE_FORWARD_APP con mittente, id e ora
originali: si rigiocano come testi normali (replayed=True), saltando quelli gia' presenti."""
import json
import logging
import math
import secrets
import time
from dataclasses import dataclass
from typing import Any, Callable

from google.protobuf.json_format import ParseDict
from meshtastic.protobuf.storeforward_pb2 import StoreAndForward

from .events import MeshEvent, TextData, node_id

log = logging.getLogger(__name__)

# testi esatti con cui il firmware rifiuta una richiesta (messaggi di testo dal router)
REFUSED_PUBLIC = "S&F not permitted on the public channel."
REFUSED_BUSY = "S&F - Busy. Try again shortly."

REQUEST_MIN_INTERVAL_S = 300  # duty cycle: una richiesta di storico per router ogni 5 minuti
HISTORY_TIMEOUT_S = 60  # nessuna risposta del router entro questo tempo: fallito
IDLE_TIMEOUT_S = 30  # in ricezione senza pacchetti da questo tempo: concluso

BROADCAST_NUM = 0xFFFFFFFF
MAX_JOBS = 50

MSG_NOT_CONNECTED = "Radio non connessa"
MSG_BUSY_RADIO = "C'è già un recupero in corso su questa radio"
MSG_NO_ANSWER = "Nessuna risposta dal router"
MSG_RADIO_LOST = "Radio scollegata durante il recupero"
MSG_REFUSED_PUBLIC = ("Il router rifiuta le richieste sul canale pubblico: scegli un canale "
                      "privato condiviso con il router")
MSG_ROUTER_BUSY = "Router occupato: riprova tra poco"
MSG_ROUTER_ERROR = "Il router ha risposto con un errore"

_ROUTER_INFO = ("ROUTER_HEARTBEAT", "ROUTER_STATS", "ROUTER_PONG")
_ACTIVE = ("waiting", "receiving")


@dataclass
class SfPacket:
    rr: str
    stats: dict | None
    history: dict | None
    heartbeat: dict | None
    text: bytes | None
    rx_time: float | None


class SfError(Exception):
    def __init__(self, message: str, status: int, retry_after: int | None = None):
        super().__init__(message)
        self.status = status
        self.retry_after = retry_after


def _fields(msg) -> dict:
    """Sotto-messaggio in dict con chiavi snake_case, valori di default compresi."""
    return {f.name: getattr(msg, f.name) for f in msg.DESCRIPTOR.fields}


def _decode(decoded: dict) -> StoreAndForward | None:
    payload = decoded.get("payload")
    if payload is not None:
        try:
            return StoreAndForward.FromString(bytes(payload))
        except Exception:
            pass
    fallback = decoded.get("storeforward")  # dict di MessageToDict (bytes in base64)
    if isinstance(fallback, dict):
        try:
            return ParseDict(fallback, StoreAndForward(), ignore_unknown_fields=True)
        except Exception:
            return None
    return None


def parse_sf(packet: dict) -> SfPacket | None:
    msg = _decode(packet.get("decoded") or {})
    if msg is None:
        return None
    variant = msg.WhichOneof("variant")
    return SfPacket(
        rr=StoreAndForward.RequestResponse.Name(msg.rr),
        stats=_fields(msg.stats) if variant == "stats" else None,
        history=_fields(msg.history) if variant == "history" else None,
        heartbeat=_fields(msg.heartbeat) if variant == "heartbeat" else None,
        text=bytes(msg.text) if variant == "text" else None,
        rx_time=packet.get("rxTime") or None,
    )


class StoreForwardService:
    def __init__(self, store, live, handle_event: Callable[[MeshEvent], None], bus,
                 connector: Callable[[str], Any], clock=time.time):
        self.store = store
        self.live = live
        self.handle_event = handle_event
        self.bus = bus
        self.connector = connector
        self.clock = clock
        self._jobs: dict[str, dict] = {}  # id -> SfJob, dal piu' vecchio
        self._activity: dict[str, float] = {}  # id lavoro -> ultimo pacchetto ricevuto
        self._sending: set[str] = set()  # radio con una richiesta in invio
        self._router_nums: dict[str, int] = {}  # id lavoro -> numero del router
        self._last_request: dict[int, float] = {
            r["num"]: r["last_request"] for r in store.conn.execute(
                "SELECT num, last_request FROM sf_routers WHERE last_request IS NOT NULL")}

    # ---- pacchetti S&F ------------------------------------------------
    def handle(self, ev: MeshEvent) -> None:
        sfp: SfPacket = ev.payload
        rr = sfp.rr
        if rr in _ROUTER_INFO:
            self._update_router(ev, sfp)
        elif rr == "ROUTER_HISTORY":
            job = self._active_job(ev.radio_id)
            if job is not None and self._router_nums.get(job["id"]) == ev.from_node:
                job["status"] = "receiving"
                job["expected"] = (sfp.history or {}).get("history_messages")
                self._activity[job["id"]] = self.clock()
                self._publish_job(job)
        elif rr in ("ROUTER_TEXT_BROADCAST", "ROUTER_TEXT_DIRECT"):
            self._replay(ev, sfp)
        elif rr in ("ROUTER_BUSY", "ROUTER_ERROR"):
            job = self._active_job(ev.radio_id)
            if job is not None and self._router_nums.get(job["id"]) == ev.from_node:
                self._finish(job, "failed",
                             MSG_ROUTER_BUSY if rr == "ROUTER_BUSY" else MSG_ROUTER_ERROR)

    def _update_router(self, ev: MeshEvent, sfp: SfPacket) -> None:
        hb = sfp.heartbeat or {}
        period = hb.get("period")
        secondary = None if not sfp.heartbeat else int(bool(hb.get("secondary")))
        stats = json.dumps(sfp.stats) if sfp.stats is not None else None
        self.store.conn.execute(
            "INSERT INTO sf_routers(num, radio_id, last_seen, heartbeat_period, secondary, stats)"
            " VALUES(?,?,?,?,?,?) ON CONFLICT(num) DO UPDATE SET"
            " radio_id=excluded.radio_id, last_seen=excluded.last_seen,"
            " heartbeat_period=COALESCE(excluded.heartbeat_period, heartbeat_period),"
            " secondary=COALESCE(excluded.secondary, secondary),"
            " stats=COALESCE(excluded.stats, stats)",
            (ev.from_node, ev.radio_id, ev.rx_time or self.clock(), period, secondary, stats))
        self._publish_routers()

    def _replay(self, ev: MeshEvent, sfp: SfPacket) -> None:
        if sfp.text is None:
            return
        job = self._active_job(ev.radio_id)
        if job is not None:
            # testi senza ROUTER_HISTORY (perso per strada): la ricezione e' comunque iniziata
            job["status"] = "receiving"
            self._activity[job["id"]] = self.clock()
        key = f"{ev.from_node}:{ev.packet_id}"
        # gia' noto: stessa chiave, oppure inviato da un'altra radio locale (direction 'out')
        known = (self.store.conn.execute(
            "SELECT 1 FROM messages WHERE key=? OR (direction='out' AND packet_id=?)",
            (key, ev.packet_id)).fetchone() is not None
            or any(m.get("key") == key
                   or (m.get("direction") == "out" and m.get("packet_id") == ev.packet_id)
                   for m in self.live.messages))
        if known:
            if job is not None:
                job["duplicates"] += 1
        else:
            self.handle_event(MeshEvent(
                source=ev.source, from_node=ev.from_node,
                to_node=BROADCAST_NUM if sfp.rr == "ROUTER_TEXT_BROADCAST" else ev.to_node,
                packet_id=ev.packet_id, channel=ev.channel,
                rx_time=sfp.rx_time or self.clock(), snr=None, rssi=None, hops=None,
                gateway_id=None, radio_id=ev.radio_id, kind="text",
                payload=TextData(sfp.text.decode("utf-8", "replace")), replayed=True))
            if job is not None:
                job["received"] += 1
        if job is not None:
            self._publish_job(job)

    def observe_text(self, ev: MeshEvent) -> None:
        """Testo normale: se e' il rifiuto del router di un recupero in corso, il lavoro fallisce."""
        text = getattr(ev.payload, "text", None)
        if text not in (REFUSED_PUBLIC, REFUSED_BUSY):
            return
        for job in self._jobs.values():
            if (job["status"] in _ACTIVE and self._router_nums.get(job["id"]) == ev.from_node
                    and (ev.radio_id is None or job["radio_id"] == ev.radio_id)):
                self._finish(job, "failed",
                             MSG_REFUSED_PUBLIC if text == REFUSED_PUBLIC else MSG_ROUTER_BUSY)

    # ---- richieste ----------------------------------------------------
    def _connected(self, radio_id: str):
        try:
            conn = self.connector(radio_id)
        except KeyError:
            return None
        if conn is None or conn.state().get("state") != "connected":
            return None
        return conn

    async def request(self, radio_id: str, router_num: int, window_min: int,
                      channel_index: int) -> dict:
        conn = self._connected(radio_id)
        if conn is None:
            raise SfError(MSG_NOT_CONNECTED, 409)
        if radio_id in self._sending or self._active_job(radio_id) is not None:
            raise SfError(MSG_BUSY_RADIO, 409)
        now = self.clock()
        last = self._last_request.get(router_num)
        if last is not None and now - last < REQUEST_MIN_INTERVAL_S:
            wait = math.ceil(REQUEST_MIN_INTERVAL_S - (now - last))
            raise SfError(f"Attendi {wait} s prima di una nuova richiesta a questo router",
                          429, retry_after=wait)
        self._sending.add(radio_id)
        # prenota subito il limite di frequenza: un'altra radio non puo' passare durante l'await
        previous = last
        self._last_request[router_num] = now
        try:
            await conn.send_storeforward(router_num, "CLIENT_HISTORY", window_min, channel_index)
        except BaseException as err:
            if previous is None:
                self._last_request.pop(router_num, None)
            else:
                self._last_request[router_num] = previous
            if isinstance(err, RuntimeError):
                raise SfError(str(err), 409) from err
            raise
        finally:
            self._sending.discard(radio_id)
        now = self.clock()
        self._last_request[router_num] = now
        self.store.conn.execute(
            "INSERT INTO sf_routers(num, last_request) VALUES(?,?)"
            " ON CONFLICT(num) DO UPDATE SET last_request=excluded.last_request",
            (router_num, now))
        job = {"id": secrets.token_hex(8), "radio_id": radio_id,
               "router_id": node_id(router_num), "window_min": window_min,
               "channel_index": channel_index, "status": "waiting", "expected": None,
               "received": 0, "duplicates": 0, "error": None, "started": now, "ended": None}
        self._jobs[job["id"]] = job
        self._router_nums[job["id"]] = router_num
        self._trim_jobs()
        self._publish_routers()
        self._publish_job(job)
        return dict(job)

    async def probe(self, radio_id: str, router_num: int, channel_index: int) -> None:
        conn = self._connected(radio_id)
        if conn is None:
            raise SfError(MSG_NOT_CONNECTED, 409)
        try:
            await conn.send_storeforward(router_num, "CLIENT_STATS", None, channel_index)
        except RuntimeError as err:
            raise SfError(str(err), 409) from err

    # ---- scadenze -----------------------------------------------------
    def check(self) -> None:
        now = self.clock()
        for job in list(self._jobs.values()):
            if job["status"] not in _ACTIVE:
                continue
            if self._connected(job["radio_id"]) is None:
                self._finish(job, "failed", MSG_RADIO_LOST)
            elif job["status"] == "waiting":
                if now - job["started"] > HISTORY_TIMEOUT_S:
                    self._finish(job, "failed", MSG_NO_ANSWER)
            elif ((job["expected"] is not None
                   and job["received"] + job["duplicates"] >= job["expected"])
                  or now - self._activity.get(job["id"], job["started"]) >= IDLE_TIMEOUT_S):
                self._finish(job, "done", None)

    # ---- stato --------------------------------------------------------
    def routers(self) -> list[dict]:
        out = []
        for r in self.store.conn.execute("SELECT * FROM sf_routers WHERE last_seen IS NOT NULL ORDER BY last_seen DESC"):
            node = self.live.nodes.get(r["num"]) or {}
            out.append({"id": node_id(r["num"]), "name": node.get("long_name"),
                        "radio_id": r["radio_id"], "last_seen": r["last_seen"],
                        "heartbeat_period": r["heartbeat_period"],
                        "secondary": bool(r["secondary"]),
                        "stats": json.loads(r["stats"]) if r["stats"] else None,
                        "last_request": r["last_request"]})
        return out

    def jobs(self) -> list[dict]:
        return [dict(j) for j in reversed(self._jobs.values())]  # dal piu' recente

    def _active_job(self, radio_id: str | None) -> dict | None:
        for job in reversed(self._jobs.values()):
            if job["radio_id"] == radio_id and job["status"] in _ACTIVE:
                return job
        return None

    def _finish(self, job: dict, status: str, error: str | None) -> None:
        job.update(status=status, error=error, ended=self.clock())
        self._activity.pop(job["id"], None)
        self._publish_job(job)

    def _trim_jobs(self) -> None:
        for jid in list(self._jobs)[:-MAX_JOBS]:
            if self._jobs[jid]["status"] not in _ACTIVE:
                del self._jobs[jid]
                self._router_nums.pop(jid, None)

    def _publish_job(self, job: dict) -> None:
        self.bus.publish({"type": "sf_job", "job": dict(job)})

    def _publish_routers(self) -> None:
        self.bus.publish({"type": "sf_routers", "routers": self.routers()})
