"""Bot di MeshLens (E15): risponde a comandi espliciti sui canali scelti dall'utente.

Regole (contratto §0.7, §6.5 e decisione R5.2):
- risponde solo a messaggi di canale dal vivo il cui testo INIZIA con un comando abilitato
  o con una parola personalizzata; mai a testi che iniziano col marcatore "[bot]" e mai ai
  nodi visti usarlo (altri bot);
- risposte in italiano, sempre con il prefisso "[bot] ", al massimo 200 byte UTF-8, mai con
  nomi di nodi o testo altrui;
- invio solo attraverso RadioManager.send / MqttSender.send (conferma pubblica mai data in
  automatico), mai override del duty cycle; coda con limiti e pausa sui rifiuti del firmware.
"""
import json
import logging
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

BOT_MARK = "[bot]"
MAX_REPLY_BYTES = 200

# parola del comando (casefold) -> nome del comando (settings.BOT_COMMANDS)
COMMAND_WORDS: dict[str, str] = {
    "!ping": "ping", "!info": "info", "!nodi": "nodes", "!nodes": "nodes",
    "!ora": "time", "!time": "time", "!meteo": "weather", "!weather": "weather",
}


@dataclass(frozen=True)
class Request:
    kind: str  # "command" | "reply"
    name: str  # nome del comando o trigger della risposta personalizzata
    reply_text: str | None  # solo "reply": testo scelto dall'utente


@dataclass(frozen=True)
class ReplyContext:
    snr: float | None
    rssi: int | None
    hops: int | None
    via_mqtt: bool
    version: str
    now: float
    nodes_active_1h: int
    nodes_total: int
    heard_1h: int
    heard_24h: int
    weather: dict | None  # None = nodo meteo non valido (nessuna risposta)


def clamp_utf8(text: str, max_bytes: int = MAX_REPLY_BYTES) -> str:
    """Taglia a max_bytes byte UTF-8 su un confine di carattere."""
    data = text.encode("utf-8")
    if len(data) <= max_bytes:
        return text
    return data[:max_bytes].decode("utf-8", errors="ignore")


def is_marked(text: str) -> bool:
    """Testo che inizia col marcatore delle risposte di un bot (senza maiuscole)."""
    return (text or "").strip().casefold().startswith(BOT_MARK)


def parse_request(text: str, commands: list[str], replies: list[dict]) -> Request | None:
    """Richiesta esplicita: il testo inizia con la parola di un comando abilitato (prima
    parola) o con un trigger di bot_replies seguito da fine testo o da un carattere non
    alfanumerico. I comandi integrati hanno la precedenza."""
    stripped = (text or "").strip()
    if not stripped or is_marked(stripped):
        return None
    word = stripped.split()[0].casefold()
    name = COMMAND_WORDS.get(word)
    if name is not None and name in commands:
        return Request("command", name, None)
    folded = stripped.casefold()
    for r in replies or []:
        trigger = (r.get("trigger") or "").casefold()
        if not trigger or not folded.startswith(trigger):
            continue
        rest = folded[len(trigger):]
        if rest and rest[0].isalnum():
            continue
        return Request("reply", r["trigger"], r.get("text") or "")
    return None


def match_target(msg: dict, targets: list[dict]) -> dict | None:
    """Bersaglio di bot_targets a cui appartiene il messaggio (radio+canale o broker+canale)."""
    for t in targets or []:
        if t.get("kind") == "radio":
            if (msg.get("source") == "rf" and msg.get("radio_id") == t.get("radio_id")
                    and msg.get("channel_index") == t.get("channel_index")):
                return t
        elif t.get("kind") == "mqtt":
            if (msg.get("source") == "mqtt" and msg.get("broker") == t.get("broker")
                    and msg.get("channel") == t.get("channel")):
                return t
    return None


def _hops_text(hops: int | None) -> str:
    if hops is None:
        return "salti n/d"
    if hops == 0:
        return "diretto"
    return "1 salto" if hops == 1 else f"{hops} salti"


def _weather_text(w: dict) -> str:
    parts = []
    if w.get("temperature") is not None:
        parts.append(f"{w['temperature']:.1f} °C")
    if w.get("relative_humidity") is not None:
        parts.append(f"UR {w['relative_humidity']:.0f}%")
    if w.get("barometric_pressure") is not None:
        parts.append(f"{w['barometric_pressure']:.0f} hPa")
    if not parts:
        return f"{BOT_MARK} Meteo non disponibile"
    return f"{BOT_MARK} Meteo: " + ", ".join(parts)


def build_reply(request: Request, ctx: ReplyContext) -> str | None:
    """Testo della risposta (con prefisso, tagliato a 200 byte) o None se non si risponde."""
    if request.kind == "reply":
        text = f"{BOT_MARK} {request.reply_text or ''}"
    elif request.name == "ping":
        if ctx.via_mqtt:
            text = f"{BOT_MARK} pong! via MQTT, {_hops_text(ctx.hops)}"
        else:
            snr = "n/d" if ctx.snr is None else f"{ctx.snr:+.1f} dB"
            rssi = "n/d" if ctx.rssi is None else f"{int(ctx.rssi)} dBm"
            text = f"{BOT_MARK} pong! SNR {snr}, RSSI {rssi}, {_hops_text(ctx.hops)}"
    elif request.name == "info":
        text = (f"{BOT_MARK} MeshLens {ctx.version}: {ctx.nodes_active_1h} nodi attivi "
                f"nell'ultima ora, {ctx.nodes_total} noti")
    elif request.name == "nodes":
        text = (f"{BOT_MARK} Nodi sentiti: {ctx.heard_1h} nell'ultima ora, "
                f"{ctx.heard_24h} nelle ultime 24 h")
    elif request.name == "time":
        text = time.strftime(f"{BOT_MARK} Ora: %H:%M del %d/%m/%Y", time.localtime(ctx.now))
    elif request.name == "weather":
        if ctx.weather is None:
            return None
        text = _weather_text(ctx.weather)
    else:
        return None
    return clamp_utf8(text)


# ---- motore: ammissione, coda, limiti, pausa sui rifiuti --------------------------------
QUEUE_MAX = 10
JOB_TTL_S = 300
MSG_MAX_AGE_S = 120
BOT_NODE_TTL_S = 86400
BOT_NODES_MAX = 256
COOLDOWN_MAP_MAX = 512
MAX_ATTEMPTS = 2
INFLIGHT_TTL_S = 120
BACKOFF_BASE_S = 300
BACKOFF_MAX_S = 3600
BACKOFF_RESET_S = 7200
WEATHER_MAX_AGE_S = 7200
HOUR_S = 3600
BROADCAST_ID = "!ffffffff"
NAK_BACKOFF = ("DUTY_CYCLE_LIMIT", "RATE_LIMIT_EXCEEDED")
WEATHER_METRICS = ("temperature", "relative_humidity", "barometric_pressure")


def weather_lookup(conn, num: int, now: float) -> dict:
    """Ultimo valore delle metriche ambientali del nodo entro WEATHER_MAX_AGE_S ({} se nessuno).
    Va chiamata dal loop (connessione principale)."""
    out: dict = {}
    for r in conn.execute(
            "SELECT metric, value FROM metrics WHERE node_num=? AND variant='environment' "
            "AND time >= ? ORDER BY time DESC", (num, now - WEATHER_MAX_AGE_S)):
        if r[0] in WEATHER_METRICS and r[0] not in out:
            out[r[0]] = r[1]
    return out


@dataclass
class Job:
    target: dict
    text: str
    reply_id: int | None
    sender: str
    created: float
    attempts: int = 0
    not_before: float = 0.0


def _num(node_id: str | None) -> int | None:
    try:
        return int(node_id[1:], 16) if node_id and node_id.startswith("!") else None
    except ValueError:
        return None


class Bot:
    """Le dipendenze sono funzioni o oggetti iniettati (test con radio e MQTT finti):
    radios.send (async) e mqtt_sender.send sono gli UNICI percorsi d'invio."""

    def __init__(self, get_settings, clock, radios, mqtt_sender, live, local_ids,
                 own_node_ids, weather_lookup, publish, version: str,
                 state_path: Path | None = None):
        self.get_settings, self.clock = get_settings, clock
        self.radios, self.mqtt_sender, self.live = radios, mqtt_sender, live
        self.local_ids, self.own_node_ids = local_ids, own_node_ids
        self.weather_lookup, self.publish, self.version = weather_lookup, publish, version
        self._queue: list[Job] = []
        self._last_reply: dict[str, float] = {}  # mittente -> ultima risposta accettata
        self._bot_nodes: dict[str, float] = {}  # mittente -> scadenza (altri bot)
        self._sent_ts: list[float] = []
        self._inflight: dict[str, tuple[float, Job]] = {}  # chiave del messaggio -> (ora, job)
        self._blocked: dict[str, object] = {}  # broker -> impostazioni al momento del blocco
        self.last_sent = float("-inf")
        self.paused_until = 0.0
        self._strikes = 0
        self._last_backoff = float("-inf")
        self.last_error: str | None = None
        self.dropped: dict[str, int] = {}
        self._published: dict | None = None
        # invii dell'ultima ora, ultimo invio e pausa sopravvivono al riavvio (M2)
        self.state_path = Path(state_path) if state_path else None
        self._load_state()

    # ---- stato persistente ------------------------------------------------------------
    def _load_state(self) -> None:
        if self.state_path is None:
            return
        try:
            data = json.loads(self.state_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return
        except (OSError, ValueError):
            log.warning("Bot: stato salvato illeggibile, ignorato")
            return
        if not isinstance(data, dict):
            return
        now = self.clock()

        def num(v) -> float | None:
            ok = isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
            return float(v) if ok else None

        sent = data.get("sent_ts")
        if isinstance(sent, list):
            self._sent_ts = sorted(t for t in map(num, sent)
                                   if t is not None and now - HOUR_S < t <= now + 60)
        last = num(data.get("last_sent"))
        if last is not None and last > now - HOUR_S:
            self.last_sent = min(last, now)
        paused = num(data.get("paused_until"))
        if paused is not None and paused > now:
            self.paused_until = min(paused, now + BACKOFF_MAX_S)
        backoff = num(data.get("last_backoff"))
        strikes = data.get("strikes")
        if (backoff is not None and isinstance(strikes, int) and not isinstance(strikes, bool)
                and 0 <= strikes <= 64 and now - backoff < BACKOFF_RESET_S):
            self._last_backoff, self._strikes = min(backoff, now), strikes

    def _save_state(self) -> None:
        if self.state_path is None:
            return
        now = self.clock()
        data = {"sent_ts": [t for t in self._sent_ts if now - t < HOUR_S],
                "last_sent": self.last_sent if math.isfinite(self.last_sent) else None,
                "paused_until": self.paused_until,
                "strikes": self._strikes,
                "last_backoff": (self._last_backoff if math.isfinite(self._last_backoff)
                                 else None)}
        tmp = self.state_path.with_name(self.state_path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(data), encoding="utf-8")
            os.replace(tmp, self.state_path)
        except OSError:
            log.warning("Bot: stato non salvato")

    # ---- ammissione (aggancio dei messaggi: sincrona, senza I/O) --------------------
    def _drop(self, reason: str) -> None:
        self.dropped[reason] = self.dropped.get(reason, 0) + 1

    def _prune_bot_nodes(self, now: float) -> None:
        for k in [k for k, exp in self._bot_nodes.items() if exp <= now]:
            del self._bot_nodes[k]
        while len(self._bot_nodes) > BOT_NODES_MAX:
            del self._bot_nodes[min(self._bot_nodes, key=self._bot_nodes.get)]

    def _prune_cooldowns(self) -> None:
        if len(self._last_reply) <= COOLDOWN_MAP_MAX:
            return
        for k in sorted(self._last_reply, key=self._last_reply.get)[
                :len(self._last_reply) - COOLDOWN_MAP_MAX]:
            del self._last_reply[k]

    def _is_own(self, sender: str, settings: dict) -> bool:
        if sender in (self.local_ids() or set()) or sender in (self.own_node_ids() or set()):
            return True
        mqtt_id = (settings.get("mqtt_node_id") or "").strip().lower()
        if mqtt_id and sender.lower() == mqtt_id:
            return True
        node = self.live.nodes.get(_num(sender))
        return bool(node and node.get("is_mine"))

    def _is_ignored(self, sender: str) -> bool:
        node = self.live.nodes.get(_num(sender))
        return bool(node and node.get("is_ignored"))

    def _broker_blocked(self, broker: str, settings: dict) -> bool:
        from .mqtt_publish import is_confirmed  # import locale: niente cicli all'avvio
        if broker in self._blocked:
            if self._blocked[broker] is settings:
                return True
            del self._blocked[broker]  # impostazioni cambiate: si riprova
        return not is_confirmed(settings, broker)

    def _weather(self, settings: dict, now: float) -> dict | None:
        num = _num(settings.get("bot_weather_node") or "")
        node = self.live.nodes.get(num) if num is not None else None
        if not node or not node.get("is_mine"):
            return None
        return self.weather_lookup(num) or {}

    def _counts(self, now: float) -> tuple[int, int, int]:
        h1 = h24 = 0
        for n in self.live.nodes.values():
            if n.get("is_ignored"):
                continue
            heard = n.get("last_heard") or 0
            if now - heard <= HOUR_S:
                h1 += 1
            if now - heard <= 24 * HOUR_S:
                h24 += 1
        return h1, h24, len(self.live.nodes)

    def on_message(self, msg: dict, meta) -> None:
        s = self.get_settings()
        now = self.clock()
        targets = s.get("bot_targets") or []
        if not s.get("bot_enabled") or not targets:
            return self._drop("disabled")
        if not meta.live or msg.get("direction") != "in":
            return self._drop("not_live")
        text = msg.get("text") or ""
        if (msg.get("emoji") or not text.strip() or msg.get("to") != BROADCAST_ID
                or now - (msg.get("time") or 0) > MSG_MAX_AGE_S):
            return self._drop("filtered")
        target = match_target(msg, targets)
        if target is None:
            return self._drop("no_target")
        sender = msg.get("from") or ""
        if self._is_own(sender, s):
            return self._drop("own")
        if self._is_ignored(sender):
            return self._drop("ignored")
        self._prune_bot_nodes(now)
        if is_marked(text):
            self._bot_nodes[sender] = now + BOT_NODE_TTL_S
            self._prune_bot_nodes(now)
            return self._drop("bot_marked")
        if sender in self._bot_nodes:
            return self._drop("bot_node")
        request = parse_request(text, s.get("bot_commands") or [], s.get("bot_replies") or [])
        if request is None:
            return self._drop("no_request")
        if now < self.paused_until:
            return self._drop("paused")
        if target["kind"] == "mqtt" and self._broker_blocked(target["broker"], s):
            return self._drop("broker_not_confirmed")
        prev = self._last_reply.get(sender)
        if prev is not None and now - prev < s.get("bot_node_cooldown_s", 300):
            return self._drop("cooldown")
        self._last_reply[sender] = now  # prenotato subito: una raffica produce una risposta

        def restore(reason: str) -> None:
            if prev is None:
                self._last_reply.pop(sender, None)
            else:
                self._last_reply[sender] = prev
            self._drop(reason)

        if len(self._queue) >= QUEUE_MAX:
            return restore("queue_full")
        if any(j.sender == sender for j in self._queue):
            return restore("pending")
        ev = meta.event
        h1, h24, total = self._counts(now)
        rctx = ReplyContext(
            snr=getattr(ev, "snr", None), rssi=getattr(ev, "rssi", None),
            hops=getattr(ev, "hops", None), via_mqtt=msg.get("source") == "mqtt",
            version=self.version, now=now, nodes_active_1h=h1, nodes_total=total,
            heard_1h=h1, heard_24h=h24,
            weather=self._weather(s, now) if request.name == "weather" else None)
        reply = build_reply(request, rctx)
        if reply is None:
            return restore("no_reply")
        self._queue.append(Job(dict(target), reply, msg.get("packet_id"), sender, now))
        self._prune_cooldowns()

    # ---- invio (task periodico, al piu' un invio per giro) ------------------------------
    def _target_active(self, target: dict, settings: dict) -> bool:
        return target in (settings.get("bot_targets") or [])

    def _requeue(self, job: Job, settings: dict, now: float) -> None:
        job.attempts += 1
        if job.attempts >= MAX_ATTEMPTS:
            self.last_error = "busy"
            return
        job.not_before = now + settings.get("bot_min_interval_s", 30)
        self._queue.insert(0, job)

    async def _send(self, job: Job, settings: dict, now: float) -> None:
        from .mqtt_publish import MqttSendError
        from .radio import RadioBusy
        t = job.target
        try:
            if t["kind"] == "radio":
                message = await self.radios.send(t["radio_id"], job.text, t["channel_index"],
                                                 to=None, reply_id=job.reply_id)
            else:
                if self.mqtt_sender is None:
                    self.last_error = "mqtt_disconnected"
                    return
                message = self.mqtt_sender.send(job.text, t["channel"], None, False,
                                                broker=t["broker"], reply_id=job.reply_id)
        except RadioBusy:
            self._requeue(job, settings, now)
            return
        except MqttSendError as e:
            if e.status == 429:
                self._requeue(job, settings, now)
            elif e.status == 409:
                self._blocked[t["broker"]] = settings
                self._queue = [j for j in self._queue
                               if not (j.target.get("kind") == "mqtt"
                                       and j.target.get("broker") == t["broker"])]
                self.last_error = "broker_not_confirmed"
            elif e.status == 503:
                self.last_error = "mqtt_disconnected"
            else:
                self.last_error = "invalid"
            return
        except KeyError:  # radio eliminata
            self.last_error = "radio_not_connected"
            return
        except ValueError as e:
            self.last_error = "radio_not_connected" if "connessa" in str(e) else "invalid"
            return
        self.last_sent = now
        self._sent_ts.append(now)
        self._save_state()
        key = (message or {}).get("key")
        if key:
            self._inflight[key] = (now, job)

    async def pump(self) -> None:
        try:
            await self._pump()
        finally:
            self._publish_status()

    async def _pump(self) -> None:
        s = self.get_settings()
        now = self.clock()
        if not s.get("bot_enabled"):
            self._queue.clear()
            return
        self._queue = [j for j in self._queue if now - j.created <= JOB_TTL_S]
        self._sent_ts = [t for t in self._sent_ts if now - t < HOUR_S]
        for k in [k for k, (t, _) in self._inflight.items() if now - t > INFLIGHT_TTL_S]:
            del self._inflight[k]
        while self._queue:
            if now < self.paused_until:
                return
            if now - self.last_sent < s.get("bot_min_interval_s", 30):
                return
            if self._queue[0].not_before > now:
                return
            if len(self._sent_ts) >= s.get("bot_max_per_hour", 20):
                return
            job = self._queue.pop(0)
            if not self._target_active(job.target, s):
                continue  # bersaglio tolto: scartato senza inviare
            await self._send(job, s, now)
            return

    # ---- esiti dal bus ----------------------------------------------------------------
    def on_bus(self, msg: dict) -> None:
        kind = msg.get("type")
        if kind == "message":
            m = msg.get("message") or {}
            old = m.get("replaces")
            if old and old in self._inflight and m.get("key"):
                self._inflight[m["key"]] = self._inflight.pop(old)
        elif kind == "message_status":
            key = msg.get("key")
            if key not in self._inflight or msg.get("status") != "failed":
                return
            self._inflight.pop(key, None)
            error = msg.get("error") or "SEND_FAILED"
            if error in NAK_BACKOFF:
                self._backoff(error)
            else:
                self.last_error = "send_failed" if error == "SEND_FAILED" else str(error).lower()

    def _backoff(self, error: str) -> None:
        now = self.clock()
        if now - self._last_backoff >= BACKOFF_RESET_S:
            self._strikes = 0
        self._strikes += 1
        self._last_backoff = now
        pause = min(BACKOFF_BASE_S * 2 ** (self._strikes - 1), BACKOFF_MAX_S)
        self.paused_until = now + pause
        self._queue.clear()
        self.last_error = error.lower()
        self._save_state()
        log.warning("Bot in pausa per %d s: %s", pause, error)

    # ---- stato ------------------------------------------------------------------------
    def status(self) -> dict:
        s = self.get_settings()
        now = self.clock()
        return {"enabled": bool(s.get("bot_enabled")), "queued": len(self._queue),
                "sent_last_hour": sum(1 for t in self._sent_ts if now - t < HOUR_S),
                "paused_until": self.paused_until if now < self.paused_until else None,
                "last_error": self.last_error, "dropped": dict(self.dropped)}

    def _publish_status(self) -> None:
        st = self.status()
        core = {k: v for k, v in st.items() if k != "dropped"}
        if core != self._published:
            self._published = core
            self.publish({"type": "bot", "status": st})

    def preview(self, text: str) -> dict:
        """Risposta che il bot darebbe a `text` (nessun invio; per !ping valori di esempio)."""
        s = self.get_settings()
        now = self.clock()
        req = parse_request(text, s.get("bot_commands") or [], s.get("bot_replies") or [])
        if req is None:
            return {"command": None, "trigger": None, "reply": None, "sample": False}
        sample = req.kind == "command" and req.name == "ping"
        h1, h24, total = self._counts(now)
        rctx = ReplyContext(snr=6.0, rssi=-90, hops=1, via_mqtt=False, version=self.version,
                            now=now, nodes_active_1h=h1, nodes_total=total, heard_1h=h1,
                            heard_24h=h24,
                            weather=self._weather(s, now) if req.name == "weather" else None)
        return {"command": req.name if req.kind == "command" else None,
                "trigger": req.name if req.kind == "reply" else None,
                "reply": build_reply(req, rctx), "sample": sample}

    def reset(self) -> None:
        """Bot spento dall'utente: coda e invii in attesa dimenticati (la pausa resta)."""
        self._queue.clear()
        self._inflight.clear()
        self._blocked.clear()
        self.last_error = None
        self._publish_status()
