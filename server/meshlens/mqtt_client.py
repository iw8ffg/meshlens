"""Connettore MQTT: sottoscrizione e, solo su richiesta esplicita dell'utente, publish di
messaggi di testo (vedi mqtt_publish.py).
I callback di paho girano in un thread dedicato: qui si decodifica soltanto, poi
gli eventi passano al loop asyncio attraverso una coda limitata (vedi inbox.py)."""
import asyncio
import collections
import logging
import secrets
import ssl
import threading
import time
from typing import Callable

import paho.mqtt.client as mqtt

from .events import MeshEvent
from .inbox import EventInbox
from .mqtt_decode import EnvelopeDecoder
from .settings import scrub_text

RATE_WINDOW_S = 5.0
DROP_KEYS = ("empty", "unsupported_port", "undecodable", "json_topic", "not_protobuf")
AUTH_REFUSED = ("bad user name or password", "not authorized")
PUBACK_TIMEOUT_S = 15.0
PUB_TIMEOUT_TEXT = "Il broker non ha confermato il messaggio"
PUB_REFUSED_TEXT = "Il broker ha rifiutato il messaggio"
ALL_SUBS_REFUSED_TEXT = ("Il broker ha rifiutato tutte le sottoscrizioni: "
                         "controlla i topic o i permessi dell'account")
log = logging.getLogger(__name__)


def _is_failure(code) -> bool:
    """Reason code di paho v2 (ReasonCode) o, con paho v1, QoS concesso intero (128 = rifiuto)."""
    if hasattr(code, "is_failure"):
        return bool(code.is_failure)
    try:
        return int(code) >= 0x80
    except (TypeError, ValueError):
        return False


def _default_factory(client_id: str):
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)


class MqttConnector:
    def __init__(self, cfg: dict, decoder: EnvelopeDecoder, loop: asyncio.AbstractEventLoop,
                 on_event: Callable[[MeshEvent], None], client_factory=None):
        self.cfg = cfg
        self.label = cfg.get("name") or cfg.get("host")
        self.decoder = decoder
        self.loop = loop
        self.on_event = on_event
        self.inbox = EventInbox(loop, on_event)  # raffiche: scarta i piu' vecchi e li conta
        self._factory = client_factory or _default_factory
        self._client = None
        self._connected = False
        self._stamps: collections.deque = collections.deque()
        self._lock = threading.Lock()
        self._connected_since: float | None = None
        self._connects = 0
        self._last_msg: float | None = None
        self._last_error: str | None = None
        self._last_error_at: float | None = None
        # sottoscrizioni della connessione corrente: mid -> topic, e topic rifiutati
        self._sub_mids: dict[int, str] = {}
        self._sub_answered = 0
        self._refused: list[str] = []
        # pubblicazioni QoS 1 in attesa di PUBACK (solo thread del loop): mid -> (esito, timer)
        self._pending_pub: dict[int, tuple[Callable[[bool, str | None], None], asyncio.TimerHandle]] = {}

    def _scrub(self, text: str) -> str:
        """Toglie dai testi d'errore utente e password MQTT: non devono mai uscire."""
        return scrub_text(text, self.cfg.get("password"), self.cfg.get("username"))

    def set_error(self, message: str) -> None:
        self._last_error = self._scrub(message)
        self._last_error_at = time.time()

    def start(self) -> None:
        client = self._factory(f"meshlens-{secrets.token_hex(4)}")
        self._client = client
        client.username_pw_set(self.cfg.get("username") or None, self.cfg.get("password") or None)
        client.reconnect_delay_set(1, 60)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_connect_fail = self._on_connect_fail
        client.on_subscribe = self._on_subscribe
        client.on_publish = self._on_publish
        try:
            if self.cfg.get("tls"):
                client.tls_set_context(ssl.create_default_context())
            client.connect_async(self.cfg["host"], int(self.cfg["port"]), keepalive=60)
            client.loop_start()
        except (OSError, ssl.SSLError) as e:
            self._connected = False
            self.set_error(f"Broker non raggiungibile: {e}")
            log.info("MQTT %s: avvio della connessione non riuscito (%s)", self.label, self._scrub(str(e)))

    def stop(self) -> None:
        client, self._client = self._client, None
        self._connected = False
        if client is None:
            return
        try:
            client.disconnect()
            client.loop_stop()
        except Exception:
            pass

    def publish(self, topic: str, payload: bytes,
                on_result: Callable[[bool, str | None], None] | None = None) -> bool:
        """Pubblica con QoS 1; False se non connesso o se il client rifiuta.
        on_result(ok, errore) arriva sul loop asyncio una sola volta: al PUBACK del broker
        oppure, se manca, dopo PUBACK_TIMEOUT_S. Va chiamata dal thread del loop."""
        client = self._client
        if client is None or not self._connected:
            return False
        try:
            info = client.publish(topic, payload, qos=1)
        except Exception:
            return False
        if getattr(info, "rc", 0) != 0:
            # paho tiene comunque il messaggio in coda e lo rimanderebbe alla riconnessione
            self._discard_paho_message(getattr(info, "mid", None), info)
            return False
        mid = getattr(info, "mid", None)
        if on_result is not None and mid is not None:
            # l'esito del PUBACK passa per call_soon_threadsafe: arriva sempre dopo questa riga
            timer = self.loop.call_later(PUBACK_TIMEOUT_S, self._publish_timeout, mid, info)
            self._pending_pub[mid] = (on_result, timer)
        return True

    def _publish_timeout(self, mid: int, info) -> None:
        """Thread del loop: PUBACK mancato. Il messaggio esce dalla coda di paho, altrimenti
        verrebbe rimandato alla riconnessione mentre l'utente lo vede come fallito."""
        self._discard_paho_message(mid, info)
        self._publish_done(mid, False, PUB_TIMEOUT_TEXT)

    def _discard_paho_message(self, mid, info) -> None:
        """Toglie un QoS 1 dalla coda di uscita di paho e libera lo slot "inflight" (max 20).
        paho non ha un'API pubblica per farlo: si usano gli attributi interni _out_messages,
        _inflight_messages e _out_message_mutex (paho 2.x). Non solleva mai: se gli interni
        cambiano, resta il comportamento precedente. Il messaggio si rimuove solo se e'
        quello di `info` (il mid puo' essere stato riusato)."""
        client = self._client
        try:
            if client is None or mid is None:
                return
            with client._out_message_mutex:
                msg = client._out_messages.get(mid)
                if msg is None or (info is not None and getattr(msg, "info", None) is not info):
                    return
                del client._out_messages[mid]
                # solo i messaggi gia' spediti occupano uno slot inflight
                if msg.state == mqtt.mqtt_ms_wait_for_puback and client._inflight_messages > 0:
                    client._inflight_messages -= 1
        except Exception:
            log.debug("MQTT %s: coda di paho non accessibile", self.label, exc_info=True)

    def _publish_done(self, mid: int, ok: bool, error: str | None) -> None:
        """Thread del loop: primo esito per quel mid (PUBACK o timeout); gli altri si ignorano."""
        entry = self._pending_pub.pop(mid, None)
        if entry is None:
            return
        on_result, timer = entry
        timer.cancel()
        try:
            on_result(ok, error)
        except Exception:
            log.exception("MQTT %s: esito della pubblicazione", self.label)

    def status(self) -> dict:
        now = time.time()
        with self._lock:
            while self._stamps and now - self._stamps[0] > RATE_WINDOW_S:
                self._stamps.popleft()
            n = len(self._stamps)
            last_msg = self._last_msg
            refused = list(self._refused)
        stats = self.decoder.stats
        return {"connected": self._connected, "msgs_per_s": n / RATE_WINDOW_S,
                "undecodable": stats["undecodable"],
                "connected_since": self._connected_since,
                "last_msg_age_s": None if last_msg is None else max(0.0, now - last_msg),
                "reconnects": max(0, self._connects - 1),
                "last_error": self._last_error, "last_error_at": self._last_error_at,
                "decoded": stats["ok"], "refused_topics": refused,
                "drops": {k: stats[k] for k in DROP_KEYS},
                "queue_dropped": self.inbox.dropped, "raw_dropped": self.inbox.raw_dropped, "queue_size": self.inbox.size()}

    # ---- callback (thread paho); firme tolleranti a paho v1 e v2 ----
    def _on_connect(self, client, userdata, *args):
        rc = args[1] if len(args) > 1 else 0
        failed = rc.is_failure if hasattr(rc, "is_failure") else bool(rc)
        if failed:
            self._connected = False
            text = str(rc)
            if any(k in text.lower() for k in AUTH_REFUSED):
                self.set_error("Utente o password MQTT rifiutati")
            else:
                self.set_error(f"Connessione rifiutata dal broker: {text}")
            log.info("MQTT %s: connessione rifiutata (motivo: %s)", self.label, rc)
            return
        self._connected = True
        self._connected_since = time.time()
        self._connects += 1
        log.info("MQTT %s: connesso a %s:%s", self.label, self.cfg.get("host"), self.cfg.get("port"))
        with self._lock:
            self._sub_mids.clear()
            self._sub_answered = 0
            self._refused = []
        for topic in self.cfg["topics"]:
            res = client.subscribe(topic, 0)
            mid = res[1] if isinstance(res, tuple) and len(res) > 1 else None
            if mid is not None:
                with self._lock:
                    self._sub_mids[mid] = topic

    def _on_subscribe(self, client, userdata, mid, reason_codes, *args):
        """SUBACK: un codice per topic; >= 0x80 vuol dire sottoscrizione rifiutata."""
        with self._lock:
            topic = self._sub_mids.pop(mid, None)
            if topic is None:
                return  # risposta di una connessione precedente
            self._sub_answered += 1
            codes = reason_codes if isinstance(reason_codes, (list, tuple)) else [reason_codes]
            refused = any(_is_failure(c) for c in codes)
            if refused and topic not in self._refused:
                self._refused.append(topic)
            total = len(self.cfg["topics"])
            all_refused = (not self._sub_mids and self._sub_answered >= total
                           and len(self._refused) >= total)
        if refused:
            log.warning("MQTT %s: sottoscrizione rifiutata dal broker: %s",
                        self.label, self._scrub(topic))
        if all_refused:
            self.set_error(ALL_SUBS_REFUSED_TEXT)

    def _on_publish(self, client, userdata, mid, *args):
        """PUBACK (thread paho). Con MQTT 3.1.1 il PUBACK non ha codice: paho riporta successo."""
        rc = args[0] if args else None
        failed = rc is not None and _is_failure(rc)
        if failed:
            log.info("MQTT %s: pubblicazione rifiutata dal broker (motivo: %s)", self.label, rc)
        try:
            self.loop.call_soon_threadsafe(self._publish_done, mid, not failed,
                                           PUB_REFUSED_TEXT if failed else None)
        except RuntimeError:
            pass  # loop chiuso: nessuno aspetta piu' l'esito

    def _on_connect_fail(self, client, userdata):
        self._connected = False
        self.set_error("Connessione non riuscita: controlla host, porta e TLS")

    def _on_disconnect(self, client, userdata, *args):
        if self._connected:
            reason = args[1] if len(args) > 1 else (args[0] if args else "sconosciuto")
            log.info("MQTT %s: disconnesso (motivo: %s)", self.label, reason)
            lost = reason.is_failure if hasattr(reason, "is_failure") else bool(reason)
            if lost:
                self.set_error(f"Connessione persa: {reason}")
        self._connected = False

    def _on_message(self, client, userdata, msg):
        now = time.time()
        with self._lock:
            self._stamps.append(now)
            self._last_msg = now
        ev = self.decoder.decode_any(msg.topic, msg.payload, now)
        if ev is not None:  # MeshEvent o RawPacket
            self.inbox.put(ev)
