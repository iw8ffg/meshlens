"""Webhook in uscita (E15): eventi scelti, nessun redirect, URL segreto mai nei log."""
import json
import logging
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from meshlens import webhook as webhook_mod
from meshlens.app import MessageMeta
from meshlens.events import MeshEvent, TextData
from meshlens.webhook import (MAX_BODY_BYTES, STARTUP_QUIET_S, WEBHOOK_MAX_PER_MIN,
                              WebhookService, classify_error, sanitize)

T0 = 1_800_000_000.0


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        length = int(self.headers.get("content-length") or 0)
        body = self.rfile.read(length)
        self.server.hits.append({"path": self.path, "headers": dict(self.headers),
                                 "body": body})
        if self.path.startswith("/redir"):
            self.send_response(302)
            self.send_header("Location", f"http://127.0.0.1:{self.server.server_port}/second")
            self.end_headers()
            return
        if self.path.startswith("/404"):
            self.send_response(404)
            self.end_headers()
            return
        if self.path.startswith("/slow"):
            time.sleep(1.0)
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        self.wfile.write(b"ok" * 2000)


@pytest.fixture
def server():
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    srv.hits = []
    th = threading.Thread(target=srv.serve_forever, daemon=True)
    th.start()
    yield srv
    srv.shutdown()
    srv.server_close()


class Clock:
    def __init__(self):
        self.t = T0 + STARTUP_QUIET_S + 1

    def __call__(self):
        return self.t


def make(url, events=("message", "alert", "sensor", "traceroute", "node_new"), enabled=True,
         **kw):
    settings = {"webhook_enabled": enabled, "webhook_url": url, "webhook_events": list(events)}
    clock = Clock()
    svc = WebhookService(lambda: settings, clock, spawn=lambda fn: fn(), version="1.6.0",
                         started=T0, **kw)
    svc.settings_ref = settings
    return svc, clock


def text_msg(text="ciao", to="!ffffffff", direction="in", outcome="new", sender="!000000aa"):
    m = {"key": f"{sender}:1", "from": sender, "from_name": "Nodo", "to": to, "channel": "0",
         "text": text, "time": int(T0), "source": "rf", "direction": direction,
         "radio_id": "r1", "channel_index": 0, "packet_id": 1, "broker": None}
    ev = MeshEvent(source="rf", from_node=int(sender[1:], 16), to_node=0xFFFFFFFF, packet_id=1,
                   channel="0", rx_time=T0, snr=1.0, rssi=-90, hops=1, gateway_id=None,
                   radio_id="r1", kind="text", payload=TextData(text))
    return m, MessageMeta(ev, outcome)


def url_of(server, path="/hook?t=SEGRETO1"):
    return f"http://127.0.0.1:{server.server_port}{path}"


def test_sends_json_body_to_local_server(server):
    svc, _ = make(url_of(server))
    svc.on_message(*text_msg())
    assert len(server.hits) == 1
    hit = server.hits[0]
    assert hit["headers"]["Content-Type"] == "application/json"
    assert hit["headers"]["User-Agent"] == "MeshLens"
    body = json.loads(hit["body"])
    assert body["app"] == "MeshLens" and body["version"] == "1.6.0"
    assert body["event"] == "message" and isinstance(body["time"], (int, float))
    assert body["data"] == {"from": "!000000aa", "from_name": "Nodo", "channel": "0",
                            "source": "rf", "text": "ciao", "time": int(T0)}
    assert svc.status()["last"]["ok"] is True and svc.status()["last"]["code"] == "ok"


def test_no_redirect_followed(server):
    svc, _ = make(url_of(server, "/redir"))
    res = svc.deliver("test", {})
    assert [h["path"] for h in server.hits] == ["/redir"]
    assert res["code"] == "redirect" and res["ok"] is False


def test_timeout_and_errors_classified(server):
    svc, _ = make(url_of(server, "/slow"), timeout=0.2)
    assert svc.deliver("test", {})["code"] == "timeout"
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    svc2, _ = make(f"http://127.0.0.1:{port}/x")
    assert svc2.deliver("test", {})["code"] == "connection_refused"
    svc3, _ = make(url_of(server, "/404"))
    assert svc3.deliver("test", {})["code"] == "http_404"
    for bad in ("nonunurl", "ftp://x/y", "http://"):
        svc4, _ = make(bad)
        assert svc4.deliver("test", {})["code"] == "invalid_url"


def test_classify_error_codes():
    import ssl
    import urllib.error
    assert classify_error(TimeoutError()) == "timeout"
    assert classify_error(urllib.error.URLError(socket.gaierror(11001, "x"))) == "dns"
    assert classify_error(urllib.error.URLError(ssl.SSLError("x"))) == "tls"
    assert classify_error(urllib.error.URLError(ConnectionRefusedError())) == "connection_refused"
    assert classify_error(urllib.error.URLError(socket.timeout())) == "timeout"
    assert classify_error(RuntimeError("x")) == "error"


def test_url_never_logged_or_returned(server, caplog):
    caplog.set_level(logging.DEBUG)
    svc, _ = make(url_of(server))
    ok = svc.deliver("test", {})
    bad = make(url_of(server, "/404?t=SEGRETO1"))[0].deliver("test", {})
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    refused = make(f"http://127.0.0.1:{port}/x?t=SEGRETO1")[0].deliver("test", {})
    host = f"127.0.0.1:{server.server_port}"
    for text in (caplog.text, str(svc.status()), str(ok), str(bad), str(refused),
                 str(port)):
        assert "SEGRETO1" not in text
    for text in (caplog.text, str(svc.status()), str(ok), str(bad), str(refused)):
        assert host not in text and str(port) not in text
    assert "Webhook non riuscito" in caplog.text


def test_event_filter(server):
    svc, _ = make(url_of(server), events=["alert"])
    svc.on_message(*text_msg())
    assert server.hits == []
    svc, _ = make(url_of(server), enabled=False)
    svc.on_message(*text_msg())
    svc, _ = make("")
    svc.on_message(*text_msg())
    assert server.hits == []


def test_message_event_rules(server):
    svc, _ = make(url_of(server))
    svc.on_message(*text_msg(to="!00000002"))  # diretto
    svc.on_message(*text_msg(outcome="dup"))
    svc.on_message(*text_msg(direction="out"))
    m, _ = text_msg()
    svc.on_message(m, MessageMeta(None, "local"))
    assert server.hits == []
    svc.on_message(*text_msg())
    assert len(server.hits) == 1


def alerts(*keys):
    return {"type": "alerts", "alerts": [{"key": k, "kind": "battery_low", "node_id": "!00000001",
                                          "node_name": "A", "value": 10, "since": T0}
                                         for k in keys]}


def test_alert_event_only_new_keys(server):
    svc, _ = make(url_of(server))
    svc.on_bus(alerts("battery:!1"))
    svc.on_bus(alerts("battery:!1"))
    assert len(server.hits) == 1
    body = json.loads(server.hits[0]["body"])
    assert body["event"] == "alert" and body["data"]["key"] == "battery:!1"
    svc.on_bus(alerts("battery:!1", "silent:!2"))
    assert len(server.hits) == 2
    assert json.loads(server.hits[1]["body"])["data"]["key"] == "silent:!2"


def test_alerts_seeded_during_startup_quiet(server):
    svc, clock = make(url_of(server))
    clock.t = T0 + 10
    svc.on_bus(alerts("battery:!1"))
    clock.t = T0 + STARTUP_QUIET_S + 1
    svc.on_bus(alerts("battery:!1"))
    assert server.hits == []


def test_traceroute_event_once_per_id_and_only_final(server):
    svc, _ = make(url_of(server))
    res = {"id": 5, "target_id": "!00000042", "status": "pending", "auto": True, "route": None,
           "radio_id": "r1", "forward": [], "back": []}
    svc.on_bus({"type": "traceroute", "result": res})
    assert server.hits == []
    svc.on_bus({"type": "traceroute", "result": {**res, "status": "ok", "route": "!aa"}})
    svc.on_bus({"type": "traceroute", "result": {**res, "status": "ok", "route": "!aa"}})
    assert len(server.hits) == 1
    assert json.loads(server.hits[0]["body"])["data"] == {
        "target_id": "!00000042", "status": "ok", "auto": True, "route": "!aa"}


def node(num, sources=("rf",), heard=None, **kw):
    return {"num": num, "id": f"!{num:08x}", "long_name": "N", "short_name": "n",
            "hw_model": "HELTEC_V3", "role": "CLIENT", "sources": list(sources),
            "last_heard": heard, "public_key": "SEGRETO", **kw}


def test_node_new_event(server):
    svc, clock = make(url_of(server))
    svc.seed([node(1)])
    now = clock.t
    svc.on_bus({"type": "nodes", "nodes": [node(1, heard=now), node(2, heard=now),
                                           node(3, sources=["mqtt"], heard=now)]})
    assert len(server.hits) == 1
    data = json.loads(server.hits[0]["body"])["data"]
    assert data["id"] == "!00000002" and "public_key" not in data
    svc.on_bus({"type": "nodes", "nodes": [node(2, heard=now)]})  # gia' visto
    svc.on_bus({"type": "nodes", "nodes": [node(4, heard=now - 700)]})  # sentito tempo fa
    assert len(server.hits) == 1
    clock.t = T0 + 10  # silenzio dopo l'avvio
    svc.on_bus({"type": "nodes", "nodes": [node(5, heard=clock.t)]})
    assert len(server.hits) == 1


def test_sensor_event_passthrough(server):
    svc, _ = make(url_of(server))
    ev = {"id": 1, "node_id": "!00000009", "time": T0, "kind": "detection", "text": "Porta",
          "value": 1, "source": "rf"}
    svc.on_bus({"type": "sensor_event", "event": ev})
    body = json.loads(server.hits[0]["body"])
    assert body["event"] == "sensor" and body["data"] == ev


def test_sanitize_strips_secret_keys():
    data = {"psk": "x", "public_key": "y", "token": "z", "a": 1,
            "nested": {"password": "p", "ok": [{"PIN": 1, "secret": 2, "url": "u", "v": 3}]}}
    assert sanitize(data) == {"a": 1, "nested": {"ok": [{"v": 3}]}}


def test_rate_and_inflight_limits():
    sent = []
    svc, clock = make("https://example.invalid/x", opener=None)
    svc.deliver = lambda event, data, url=None: sent.append(event) or {"ok": True}
    for _ in range(WEBHOOK_MAX_PER_MIN + 1):
        svc.on_bus({"type": "sensor_event", "event": {"id": 1}})
    assert len(sent) == WEBHOOK_MAX_PER_MIN and svc.dropped == 1
    clock.t += 61
    pending = []
    svc2, _ = make("https://example.invalid/x")
    svc2.spawn = pending.append  # non termina mai
    for _ in range(5):
        svc2.on_bus({"type": "sensor_event", "event": {"id": 1}})
    assert len(pending) == 4 and svc2.dropped == 1


def test_body_size_capped(server):
    svc, _ = make(url_of(server))
    svc.deliver("message", {"text": "x" * 50_000, "other": "y" * 50_000})
    assert len(server.hits[0]["body"]) <= MAX_BODY_BYTES
    json.loads(server.hits[0]["body"])


def test_installed_service():
    from test_trace_scheduler import Env as TEnv, make_installed
    rt, ctx = make_installed(TEnv())
    svc = ctx.ext["webhook"]
    assert isinstance(svc, WebhookService) and svc.on_message in rt.message_hooks


def test_no_send_shortcuts_in_source():
    src = Path(webhook_mod.__file__).read_text(encoding="utf-8")
    for bad in ("override_duty_cycle", "sendText", "sendData", "paho", "iface"):
        assert bad not in src
