"""API REST e WebSocket. Tutti gli handler sono async: la connessione sqlite e
condivisa e va usata solo dal thread dell'event loop."""
import asyncio
import ipaddress
import mimetypes
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.websockets import WebSocketDisconnect

from .auth import Auth, LockedError
from .bus import Bus
from .geo import CountryLocator
from .live import LiveState
from .radio_manager import NoRadioConnected, TracerouteThrottled
from .settings import load_settings, save_settings
from .store import Store

COOKIE = "meshlens_session"
COOKIE_MAX_AGE = 365 * 24 * 3600
MASK = "••••"
LOCAL_HOSTS = ("127.0.0.1", "::1", "localhost")
INTERNAL_KEYS = ()


@dataclass
class AppContext:
    live: LiveState
    store: Store
    auth: Auth
    bus: Bus
    locator: CountryLocator
    conn: sqlite3.Connection
    mqtt_status: Callable[[], dict]
    on_settings_changed: Callable[[dict], Awaitable[None]]
    static_dir: Path | None = None
    radios: object | None = None  # RadioManager


class PinBody(BaseModel):
    pin: str


class RadioBody(BaseModel):
    kind: str
    address: str
    name: str | None = None


class TracerouteBody(BaseModel):
    radio_id: str | None = None


class SendBody(BaseModel):
    text: str
    channel_index: int = 0
    to: str | None = None


def _public(node: dict) -> dict:
    return {k: v for k, v in node.items() if k not in INTERNAL_KEYS}


def _parse_countries(country: str | None) -> list[str] | None:
    if country is None or not country.strip():
        return None
    return [c.strip() for c in country.split(",") if c.strip()]


def _matches(country_value: str | None, wanted: list[str] | None) -> bool:
    if wanted is None:
        return True
    return ("none" if country_value is None else country_value) in wanted


def _host_allowed(host_header: str | None) -> bool:
    """Solo 'localhost' o un IP letterale (anti DNS rebinding)."""
    if not host_header:
        return False
    try:
        hostname = urlsplit("//" + host_header).hostname
    except ValueError:
        return False
    if not hostname:
        return False
    if hostname == "localhost":
        return True
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


NOT_BUILT_HTML = ("<!doctype html><html lang=\"it\"><meta charset=\"utf-8\"><title>MeshLens</title>"
                  "<body><p>Interfaccia non compilata: esegui start.bat oppure npm run build "
                  "nella cartella web</p></body></html>")


def _num_from_id(node_id: str) -> int:
    try:
        if not node_id.startswith("!"):
            raise ValueError
        return int(node_id[1:], 16)
    except ValueError:
        raise HTTPException(404, "Nodo non trovato")


def _mask_settings(s: dict) -> dict:
    out = {**s, "mqtt": dict(s["mqtt"])}
    if out["mqtt"].get("password"):
        out["mqtt"]["password"] = MASK
    return out

# Su Windows mimetypes legge il registro: forza i tipi JS per gli script ES module.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")


class _SpaStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404 and not path.startswith("api"):
                return await super().get_response("index.html", scope)
            raise


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="MeshLens")

    @app.middleware("http")
    async def check_host(request: Request, call_next):
        if not _host_allowed(request.headers.get("host")):
            return JSONResponse({"detail": "Host non consentito"}, status_code=400)
        return await call_next(request)

    def set_cookie(response: Response, token: str) -> None:
        response.set_cookie(COOKIE, token, max_age=COOKIE_MAX_AGE, httponly=True,
                            samesite="strict", secure=False, path="/")

    def is_local(request: Request) -> bool:
        return request.client is not None and request.client.host in LOCAL_HOSTS

    async def require_json(request: Request) -> None:
        ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise HTTPException(415, "Content-Type non supportato")

    async def require_auth(request: Request) -> None:
        if not ctx.auth.check(request.cookies.get(COOKIE)):
            raise HTTPException(401, "Accesso richiesto")

    # ---- auth ----
    @app.get("/api/auth/status")
    async def auth_status(request: Request):
        return {"pin_set": ctx.auth.pin_is_set(),
                "authenticated": ctx.auth.check(request.cookies.get(COOKIE)),
                "is_local": is_local(request)}

    @app.post("/api/auth/setup", dependencies=[Depends(require_json)])
    async def auth_setup(body: PinBody, request: Request, response: Response):
        if ctx.auth.pin_is_set() or not is_local(request):
            raise HTTPException(403, "Impostazione del PIN non consentita")
        try:
            ctx.auth.set_pin(body.pin)
        except ValueError as e:
            raise HTTPException(400, str(e))
        token = ctx.auth.login(body.pin, request.client.host, request.headers.get("user-agent"))
        set_cookie(response, token)
        return {"ok": True}

    @app.post("/api/auth/login", dependencies=[Depends(require_json)])
    async def auth_login(body: PinBody, request: Request, response: Response):
        ip = request.client.host if request.client else "unknown"
        try:
            token = ctx.auth.login(body.pin, ip, request.headers.get("user-agent"))
        except LockedError as e:
            return JSONResponse({"detail": "Troppi tentativi, riprova più tardi"},
                                status_code=429, headers={"Retry-After": str(e.retry_after)})
        except PermissionError:
            raise HTTPException(401, "PIN errato")
        set_cookie(response, token)
        return {"ok": True}

    @app.post("/api/auth/logout")
    async def auth_logout(request: Request, response: Response):
        token = request.cookies.get(COOKIE)
        if token:
            ctx.auth.logout(token)
        response.delete_cookie(COOKIE, path="/")
        return {"ok": True}

    # ---- nodi ----
    @app.get("/api/nodes", dependencies=[Depends(require_auth)])
    async def list_nodes(country: str | None = None, max_age_h: float | None = None):
        wanted = _parse_countries(country)
        cutoff = time.time() - max_age_h * 3600 if max_age_h is not None else None
        out = []
        for node in list(ctx.live.nodes.values()):
            if not _matches(node.get("country"), wanted):
                continue
            if cutoff is not None and (node.get("last_heard") or 0) < cutoff:
                continue
            out.append(_public(node))
        return out

    @app.get("/api/nodes/{node_id}", dependencies=[Depends(require_auth)])
    async def get_node(node_id: str):
        num = _num_from_id(node_id)
        node = ctx.live.nodes.get(num)
        if node is None:
            raise HTTPException(404, "Nodo non trovato")
        return {**_public(node), "telemetry": ctx.store.telemetry(num, time.time() - 24 * 3600)}

    @app.get("/api/nodes/{node_id}/positions", dependencies=[Depends(require_auth)])
    async def node_positions(node_id: str, hours: float = 24):
        num = _num_from_id(node_id)
        return ctx.store.positions(num, time.time() - hours * 3600)

    # ---- messaggi ----
    @app.get("/api/messages", dependencies=[Depends(require_auth)])
    async def live_messages(country: str | None = None,
                            limit: int = Query(200, ge=1, le=1000)):
        wanted = _parse_countries(country)
        out = []
        for msg in reversed(ctx.live.messages):
            if len(out) >= limit:
                break
            if _matches(msg.get("country"), wanted):
                out.append(msg)
        return out

    @app.get("/api/messages/history", dependencies=[Depends(require_auth)])
    async def message_history(country: str | None = None, before: float | None = None,
                              limit: int = Query(200, ge=1, le=1000)):
        wanted = _parse_countries(country)
        if wanted is not None:
            # lo storico contiene solo nazioni salvate: "none" non c'e mai
            wanted = [c for c in wanted if c != "none"]
            if not wanted:
                return []
        return ctx.store.messages(wanted, before, limit)

    @app.get("/api/messages/radio", dependencies=[Depends(require_auth)])
    async def radio_messages(before: float | None = None,
                             limit: int = Query(200, ge=1, le=1000)):
        return ctx.store.radio_messages(before, limit)

    @app.get("/api/countries", dependencies=[Depends(require_auth)])
    async def countries():
        counts: dict[str, int] = {}
        for node in ctx.live.nodes.values():
            key = node.get("country") or "none"
            counts[key] = counts.get(key, 0) + 1
        out = [{"code": c, "name": ctx.locator.names.get(c, c), "nodes": n}
               for c, n in counts.items() if c != "none"]
        out.sort(key=lambda x: (-x["nodes"], x["code"]))
        out.append({"code": "none", "name": "Sconosciuta", "nodes": counts.get("none", 0)})
        return out

    # ---- impostazioni e stato ----
    @app.get("/api/settings", dependencies=[Depends(require_auth)])
    async def get_settings():
        return _mask_settings(load_settings(ctx.conn))

    @app.put("/api/settings", dependencies=[Depends(require_auth)])
    async def put_settings(changes: dict):
        changes = dict(changes)
        mqtt = changes.get("mqtt")
        if isinstance(mqtt, dict) and mqtt.get("password") == MASK:
            changes["mqtt"] = {k: v for k, v in mqtt.items() if k != "password"}
        try:
            saved = save_settings(ctx.conn, changes)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await ctx.on_settings_changed(saved)
        return _mask_settings(saved)

    @app.get("/api/status", dependencies=[Depends(require_auth)])
    async def status():
        return ctx.mqtt_status()

    # ---- radio ----
    async def radio_call(coro):
        try:
            return await coro
        except ValueError as e:
            raise HTTPException(400, str(e))
        except KeyError:
            raise HTTPException(404, "Radio non trovata")

    @app.get("/api/radios", dependencies=[Depends(require_auth)])
    async def list_radios():
        return ctx.radios.radios()

    @app.post("/api/radios", dependencies=[Depends(require_auth), Depends(require_json)])
    async def add_radio(body: RadioBody):
        return await radio_call(ctx.radios.add(body.kind, body.address, body.name))

    @app.get("/api/radios/ports", dependencies=[Depends(require_auth)])
    async def radio_ports():
        return await radio_call(ctx.radios.ports())

    @app.post("/api/radios/ble-scan", dependencies=[Depends(require_auth)])
    async def radio_ble_scan():
        return await radio_call(ctx.radios.ble_scan())

    @app.delete("/api/radios/{radio_id}", dependencies=[Depends(require_auth)])
    async def delete_radio(radio_id: str):
        await radio_call(ctx.radios.remove(radio_id))
        return {"ok": True}

    @app.post("/api/radios/{radio_id}/connect", dependencies=[Depends(require_auth)])
    async def connect_radio(radio_id: str):
        await radio_call(ctx.radios.connect(radio_id))
        return {"ok": True}

    @app.post("/api/radios/{radio_id}/disconnect", dependencies=[Depends(require_auth)])
    async def disconnect_radio(radio_id: str):
        await radio_call(ctx.radios.disconnect(radio_id))
        return {"ok": True}

    @app.post("/api/radios/{radio_id}/send", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def send_radio(radio_id: str, body: SendBody):
        return await radio_call(
            ctx.radios.send(radio_id, body.text, body.channel_index, body.to))

    @app.post("/api/nodes/{node_id}/traceroute", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def start_traceroute(node_id: str, body: TracerouteBody):
        _num_from_id(node_id)
        try:
            return await ctx.radios.traceroute(node_id, body.radio_id)
        except NoRadioConnected as e:
            raise HTTPException(409, str(e))
        except TracerouteThrottled as e:
            raise HTTPException(429, str(e))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except KeyError:
            raise HTTPException(404, "Radio non trovata")

    @app.get("/api/nodes/{node_id}/traceroutes", dependencies=[Depends(require_auth)])
    async def node_traceroutes(node_id: str):
        return ctx.store.traceroutes(_num_from_id(node_id), 10)

    # ---- websocket ----
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket):
        await ws.accept()
        host = ws.headers.get("host")
        origin = ws.headers.get("origin")
        if not _host_allowed(host) or (
                origin is not None and urlsplit(origin).netloc.lower() != (host or "").lower()):
            await ws.close(code=4403)
            return
        if not ctx.auth.check(ws.cookies.get(COOKIE)):
            await ws.close(code=4401)
            return
        q = ctx.bus.subscribe()
        recv = asyncio.ensure_future(ws.receive())
        get = asyncio.ensure_future(q.get())
        try:
            while True:
                done, _ = await asyncio.wait({get, recv}, return_when=asyncio.FIRST_COMPLETED)
                if recv in done:
                    if recv.result()["type"] == "websocket.disconnect":
                        break
                    recv = asyncio.ensure_future(ws.receive())  # frame del client: ignorato
                if get in done:
                    await ws.send_json(get.result())
                    get = asyncio.ensure_future(q.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            recv.cancel()
            get.cancel()
            ctx.bus.unsubscribe(q)

    # ---- statici (ultimi: catch-all) ----
    if ctx.static_dir is not None and Path(ctx.static_dir).exists():
        app.mount("/", _SpaStaticFiles(directory=ctx.static_dir, html=True), name="static")
    else:
        @app.get("/", include_in_schema=False)
        async def not_built():
            return HTMLResponse(NOT_BUILT_HTML)

    return app
