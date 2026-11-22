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
log = logging.getLogger(__name__)


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

    def publish(self, topic: str, payload: bytes) -> bool:
        """Pubblica con QoS 0; False se non connesso o se il client rifiuta."""
        client = self._client
        if client is None or not self._connected:
            return False
        try:
            info = client.publish(topic, payload, qos=0)
        except Exception:
            return False
        return getattr(info, "rc", 0) == 0

    def status(self) -> dict:
        now = time.time()
        with self._lock:
            while self._stamps and now - self._stamps[0] > RATE_WINDOW_S:
                self._stamps.popleft()
            n = len(self._stamps)
            last_msg = self._last_msg
        stats = self.decoder.stats
        return {"connected": self._connected, "msgs_per_s": n / RATE_WINDOW_S,
                "undecodable": stats["undecodable"],
                "connected_since": self._connected_since,
                "last_msg_age_s": None if last_msg is None else max(0.0, now - last_msg),
                "reconnects": max(0, self._connects - 1),
                "last_error": self._last_error, "last_error_at": self._last_error_at,
                "decoded": stats["ok"],
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
        for topic in self.cfg["topics"]:
            client.subscribe(topic, 0)

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
