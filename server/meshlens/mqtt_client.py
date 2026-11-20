"""Connettore MQTT: solo sottoscrizione (MeshLens non pubblica mai sui broker).
I callback di paho girano in un thread dedicato: qui si decodifica soltanto, poi
gli eventi passano al loop asyncio con call_soon_threadsafe."""
import asyncio
import collections
import secrets
import threading
import time
from typing import Callable

import paho.mqtt.client as mqtt

from .events import MeshEvent
from .mqtt_decode import EnvelopeDecoder

RATE_WINDOW_S = 5.0


def _default_factory(client_id: str):
    return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)


class MqttConnector:
    def __init__(self, cfg: dict, decoder: EnvelopeDecoder, loop: asyncio.AbstractEventLoop,
                 on_event: Callable[[MeshEvent], None], client_factory=None):
        self.cfg = cfg
        self.decoder = decoder
        self.loop = loop
        self.on_event = on_event
        self._factory = client_factory or _default_factory
        self._client = None
        self._connected = False
        self._stamps: collections.deque = collections.deque()
        self._lock = threading.Lock()

    def start(self) -> None:
        client = self._factory(f"meshlens-{secrets.token_hex(4)}")
        self._client = client
        client.username_pw_set(self.cfg.get("username") or None, self.cfg.get("password") or None)
        client.reconnect_delay_set(1, 60)
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        try:
            client.connect_async(self.cfg["host"], int(self.cfg["port"]), keepalive=60)
            client.loop_start()
        except OSError:
            self._connected = False

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

    def status(self) -> dict:
        now = time.time()
        with self._lock:
            while self._stamps and now - self._stamps[0] > RATE_WINDOW_S:
                self._stamps.popleft()
            n = len(self._stamps)
        return {"connected": self._connected, "msgs_per_s": n / RATE_WINDOW_S,
                "undecodable": self.decoder.stats["undecodable"]}

    # ---- callback (thread paho); firme tolleranti a paho v1 e v2 ----
    def _on_connect(self, client, userdata, *args):
        rc = args[1] if len(args) > 1 else 0
        failed = rc.is_failure if hasattr(rc, "is_failure") else bool(rc)
        if failed:
            self._connected = False
            return
        self._connected = True
        for topic in self.cfg["topics"]:
            client.subscribe(topic, 0)

    def _on_disconnect(self, client, userdata, *args):
        self._connected = False

    def _on_message(self, client, userdata, msg):
        now = time.time()
        with self._lock:
            self._stamps.append(now)
        ev = self.decoder.decode(msg.topic, msg.payload, now)
        if ev is not None:
            try:
                self.loop.call_soon_threadsafe(self.on_event, ev)
            except RuntimeError:  # loop chiuso durante lo spegnimento
                pass
