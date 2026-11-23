"""Webhook in uscita (E15): un POST JSON verso l'URL scelto dall'utente per gli eventi scelti.

- Eventi (webhook_events): message (solo messaggi di canale ricevuti dal vivo, mai i diretti),
  alert (solo avvisi nuovi), sensor, traceroute (esito finale, una volta per id), node_new.
- Consegna: un thread daemon per invio, timeout 5 s, nessun redirect seguito, un solo
  tentativo, al massimo WEBHOOK_MAX_PER_MIN al minuto e MAX_INFLIGHT in volo.
- L'URL e' un segreto: non compare mai nei log, negli esiti, negli errori, negli eventi; il
  corpo passa da sanitize() (difesa in profondita' contro chiavi e token).
"""
import json
import logging
import socket
import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import deque
from typing import Callable

log = logging.getLogger(__name__)

TIMEOUT_S = 5.0
WEBHOOK_MAX_PER_MIN = 30
MAX_INFLIGHT = 4
MAX_BODY_BYTES = 8192
MAX_RESPONSE_BYTES = 1024
MAX_STRING_CHARS = 1000
NEW_NODE_HEARD_S = 600
STARTUP_QUIET_S = 300
TRACE_IDS_MAX = 512
BROADCAST_ID = "!ffffffff"
SECRET_FIELDS = frozenset({"psk", "public_key", "token", "password", "pin", "secret", "url"})
NODE_FIELDS = ("id", "long_name", "short_name", "hw_model", "role", "last_heard")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **kw):
        return None  # un 3xx diventa HTTPError: classificato come "redirect"


def sanitize(data):
    """Toglie ricorsivamente le chiavi che possono contenere segreti."""
    if isinstance(data, dict):
        return {k: sanitize(v) for k, v in data.items()
                if not (isinstance(k, str) and k.lower() in SECRET_FIELDS)}
    if isinstance(data, list):
        return [sanitize(v) for v in data]
    return data


def _clip(data):
    if isinstance(data, dict):
        return {k: _clip(v) for k, v in data.items()}
    if isinstance(data, list):
        return [_clip(v) for v in data]
    if isinstance(data, str) and len(data) > MAX_STRING_CHARS:
        return data[:MAX_STRING_CHARS]
    return data


def classify_error(exc: BaseException) -> str:
    """Codice breve dell'errore (mai il testo originale, che puo' contenere l'URL)."""
    if isinstance(exc, urllib.error.HTTPError):
        return "redirect" if 300 <= exc.code < 400 else f"http_{exc.code}"
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return "timeout"
    if isinstance(reason, ConnectionRefusedError):
        return "connection_refused"
    if isinstance(reason, socket.gaierror):
        return "dns"
    if isinstance(reason, ssl.SSLError):
        return "tls"
    if isinstance(reason, ValueError):
        return "invalid_url"
    return "error"


def _valid_url(url: str) -> bool:
    try:
        p = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    return p.scheme in ("http", "https") and bool(p.hostname)


def _spawn_thread(fn: Callable[[], None]) -> None:
    threading.Thread(target=fn, name="meshlens-webhook", daemon=True).start()


class WebhookService:
    def __init__(self, get_settings: Callable[[], dict], clock: Callable[[], float] = time.time,
                 opener=None, spawn: Callable | None = None, version: str = "",
                 timeout: float = TIMEOUT_S, started: float | None = None):
        self.get_settings, self.clock, self.version = get_settings, clock, version
        self.opener = opener or urllib.request.build_opener(_NoRedirect)
        self.spawn = spawn or _spawn_thread
        self.timeout = timeout
        self.started = clock() if started is None else started
        self.last: dict | None = None
        self.dropped = 0
        self._lock = threading.Lock()
        self._inflight = 0
        self._sent: deque[float] = deque()
        self._known: set[int] = set()
        self._alert_keys: set[str] = set()
        self._trace_ids: deque[int] = deque(maxlen=TRACE_IDS_MAX)

    # ---- stato -------------------------------------------------------------------------
    def status(self) -> dict:
        s = self.get_settings()
        return {"enabled": bool(s.get("webhook_enabled")),
                "configured": bool(s.get("webhook_url")),
                "events": list(s.get("webhook_events") or []),
                "last": dict(self.last) if self.last else None}

    def seed(self, nodes) -> None:
        """Nodi gia' noti all'avvio: non sono "nuovi"."""
        for n in nodes:
            if n.get("num") is not None:
                self._known.add(n["num"])

    # ---- consegna ----------------------------------------------------------------------
    def _body(self, event: str, data: dict) -> bytes:
        doc = {"app": "MeshLens", "version": self.version, "event": event,
               "time": self.clock(), "data": _clip(sanitize(data))}
        body = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        if len(body) > MAX_BODY_BYTES:
            doc["data"] = {"truncated": True}
            body = json.dumps(doc, ensure_ascii=False).encode("utf-8")
        return body

    def deliver(self, event: str, data: dict, *, url: str | None = None) -> dict:
        """Un invio sincrono (dai thread o dalla prova); restituisce {"ok", "time", "code"}."""
        if url is None:
            url = self.get_settings().get("webhook_url") or ""
        code = "ok"
        if not _valid_url(url):
            code = "invalid_url"
        else:
            req = urllib.request.Request(
                url, data=self._body(event, data), method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "MeshLens"})
            try:
                with self.opener.open(req, timeout=self.timeout) as resp:
                    resp.read(MAX_RESPONSE_BYTES)
                    status = getattr(resp, "status", 200)
                    if not 200 <= status < 300:
                        code = "redirect" if 300 <= status < 400 else f"http_{status}"
            except Exception as e:  # noqa: BLE001 - qualunque errore diventa un codice
                code = classify_error(e)
        result = {"ok": code == "ok", "time": self.clock(), "code": code}
        self.last = result
        if code != "ok":
            log.warning("Webhook non riuscito: %s", code)
        return result

    def _enqueue(self, event: str, data: dict) -> None:
        s = self.get_settings()
        if (not s.get("webhook_enabled") or not s.get("webhook_url")
                or event not in (s.get("webhook_events") or [])):
            return
        now = self.clock()
        with self._lock:
            while self._sent and now - self._sent[0] >= 60:
                self._sent.popleft()
            if len(self._sent) >= WEBHOOK_MAX_PER_MIN or self._inflight >= MAX_INFLIGHT:
                self.dropped += 1
                return
            self._sent.append(now)
            self._inflight += 1

        def run() -> None:
            try:
                self.deliver(event, data)
            except Exception:  # noqa: BLE001 - deliver non solleva; difesa
                log.warning("Webhook non riuscito: %s", "error")
            finally:
                with self._lock:
                    self._inflight -= 1

        try:
            self.spawn(run)
        except Exception:  # noqa: BLE001 - thread non avviato
            with self._lock:
                self._inflight -= 1
            self.dropped += 1

    # ---- eventi ------------------------------------------------------------------------
    def on_message(self, msg: dict, meta) -> None:
        if not meta.live or msg.get("direction") != "in" or msg.get("to") != BROADCAST_ID:
            return
        self._enqueue("message", {k: msg.get(k) for k in
                                  ("from", "from_name", "channel", "source", "text", "time")})

    def on_bus(self, msg: dict) -> None:
        kind = msg.get("type")
        now = self.clock()
        quiet = now - self.started < STARTUP_QUIET_S
        if kind == "alerts":
            items = msg.get("alerts") or []
            keys = {a.get("key") for a in items}
            new = [a for a in items if a.get("key") not in self._alert_keys]
            self._alert_keys = keys
            if quiet:
                return
            for a in new:
                self._enqueue("alert", {k: a.get(k) for k in
                                        ("key", "kind", "node_id", "node_name", "value",
                                         "since", "detail", "rule_id") if k in a})
        elif kind == "sensor_event":
            self._enqueue("sensor", dict(msg.get("event") or {}))
        elif kind == "traceroute":
            r = msg.get("result") or {}
            if r.get("status") in (None, "pending") or r.get("id") in self._trace_ids:
                return
            self._trace_ids.append(r.get("id"))
            self._enqueue("traceroute", {k: r.get(k) for k in
                                         ("target_id", "status", "auto", "route")})
        elif kind == "nodes":
            for n in msg.get("nodes") or []:
                num = n.get("num")
                if num is None or num in self._known or "rf" not in (n.get("sources") or []):
                    continue
                self._known.add(num)
                if quiet or now - (n.get("last_heard") or 0) > NEW_NODE_HEARD_S:
                    continue
                self._enqueue("node_new", {k: n.get(k) for k in NODE_FIELDS})
