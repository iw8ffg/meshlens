"""API REST e WebSocket. Tutti gli handler sono async: la connessione sqlite e
condivisa e va usata solo dal thread dell'event loop."""
import asyncio
import ipaddress
import mimetypes
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Awaitable, Callable, Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response, WebSocket
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.websockets import WebSocketDisconnect

from .alerts import compute_alerts
from .auth import Auth, LockedError
from .bus import Bus
from .config_model import schema as config_schema
from .config_service import ConfigError
from .coverage import SessionActive, precision_m
from .geo import CountryLocator
from .live import LiveState
from .maps import MapsError
from .updater import UpdateError
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
    coverage: object | None = None  # CoverageRecorder
    data_dir: Path | None = None
    config: object | None = None  # ConfigService
    maps: object | None = None  # MapsManager
    updater: object | None = None  # Updater
    mqtt_channel_counts: Callable[[], dict] = lambda: {}  # canali MQTT visti nell'ultima ora
    exit_callback: Callable[[], None] | None = None  # impostata dal lanciatore
    _alerts: list = field(default_factory=list)

    def request_exit(self, delay_s: float = 0.0) -> None:
        """Chiede al lanciatore di uscire (anche l'aggiornamento la usa, senza HTTP)."""
        def fire() -> None:
            if self.exit_callback:
                self.exit_callback()
        if delay_s <= 0:
            threading.Thread(target=fire, daemon=True).start()
        else:
            t = threading.Timer(delay_s, fire)
            t.daemon = True
            t.start()

    def alerts(self) -> list[dict]:
        """Ricalcola gli avvisi; pubblica sul WS solo se key o value cambiano."""
        old = self._alerts
        new = compute_alerts(self.live.nodes.values(), load_settings(self.conn), time.time(),
                             {a["key"]: a for a in old})
        self._alerts = new
        if [(a["key"], a["value"]) for a in new] != [(a["key"], a["value"]) for a in old]:
            self.bus.publish({"type": "alerts", "alerts": new})
        return new


class MapsEstimateBody(BaseModel):
    kind: Literal["world", "italy", "area"]
    bbox: list[float] | None = None


class MapsDownloadBody(BaseModel):
    kind: Literal["tool", "world", "italy", "area"]
    bbox: list[float] | None = None
    name: str | None = Field(None, max_length=80)


class UpdateInstallBody(BaseModel):
    confirm: bool = False


class MineBody(BaseModel):
    mine: bool


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


class CoverageStartBody(BaseModel):
    name: str | None = None
    radio_id: str
    mobile_id: str
    mode: Literal["rangetest", "position"] = "rangetest"
    interval_s: int = Field(30, ge=10, le=600)
    base_lat: float | None = None
    base_lon: float | None = None
    accept_approx: bool = False


class CoveragePrepareBody(BaseModel):
    radio_id: str
    mobile_id: str
    interval_s: int = Field(30, ge=10, le=600)
    private_channel: bool = False


class CoveragePlanBody(BaseModel):
    plan_id: int


class CoveragePlanApplyBody(BaseModel):
    confirm_risky: bool = False


class CoveragePatchBody(BaseModel):
    name: str | None = None
    notes: str | None = None
    base_lat: float | None = None
    base_lon: float | None = None


class ConfigReadBody(BaseModel):
    radio_id: str | None = None
    sections: list[str] | None = None


class ConfigPreviewBody(BaseModel):
    changes: dict


class ConfigApplyBody(BaseModel):
    preview_id: str
    confirm_risky: bool = False


class ConfigRebootBody(BaseModel):
    radio_id: str | None = None
    confirm: bool = False


class ConfigFixedPositionBody(BaseModel):
    radio_id: str | None = None
    lat: float | None = None
    lon: float | None = None
    alt: int = 0
    remove: bool = False
    confirm: bool = False


GPS_MAX_AGE_S = 600
NO_GPS_MSG = ("Il nodo mobile non ha inviato una posizione negli ultimi 10 minuti: "
              "serve il GPS acceso e la posizione attiva.")


def _mobile_num(mobile_id: str) -> int:
    """'!hex' in qualunque maiuscola/minuscola -> num; 400 se non valido."""
    hexpart = mobile_id[1:] if mobile_id.startswith("!") else mobile_id
    if len(hexpart) != 8 or any(c not in "0123456789abcdefABCDEF" for c in hexpart):
        raise HTTPException(400, "Identificativo del nodo mobile non valido")
    return int(hexpart, 16)


def _check_latlon(lat: float | None, lon: float | None) -> None:
    if (lat is not None and not -90 <= lat <= 90) or (lon is not None and not -180 <= lon <= 180):
        raise HTTPException(400, "Coordinate della base non valide")


def _radius_text(radius: int) -> str:
    if radius < 1000:
        return f"{radius} m"
    return f"{radius / 1000:.1f}".replace(".", ",") + " km"


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
    if out.get("update_token"):
        out["update_token"] = MASK  # il token non esce mai
    return out

# Su Windows mimetypes legge il registro: forza i tipi JS per gli script ES module.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/javascript", ".mjs")


class _SpaStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            p = path.replace("\\", "/")  # su Windows get_path usa il separatore del sistema
            if (e.status_code == 404 and not p.startswith("api")
                    and not p.startswith(("map-assets/", "tiles/"))):
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

    # ---- istanza singola e chiusura ----
    @app.get("/api/ping")
    async def ping():
        # non autenticato e senza altri dati: serve solo a riconoscere MeshLens sulla porta
        from . import __version__
        return {"app": "meshlens", "version": __version__}

    # ---- auth ----
    @app.get("/api/version", dependencies=[Depends(require_auth)])
    async def version():
        from . import __version__
        from .paths import default_data_dir, is_frozen
        return {"version": __version__, "frozen": is_frozen(),
                "data_dir": str(ctx.data_dir or default_data_dir())}

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

    @app.get("/api/nodes/{node_id}/telemetry", dependencies=[Depends(require_auth)])
    async def node_telemetry(node_id: str, hours: float = 168):
        num = _num_from_id(node_id)
        if num not in ctx.live.nodes:
            raise HTTPException(404, "Nodo non trovato")
        keys = ("time", "battery", "voltage", "channel_util", "air_util_tx")
        return [{k: p[k] for k in keys}
                for p in ctx.store.telemetry(num, time.time() - hours * 3600)]

    @app.put("/api/nodes/{node_id}/mine",
             dependencies=[Depends(require_auth), Depends(require_json)])
    async def set_mine(node_id: str, body: MineBody):
        num = _num_from_id(node_id)
        node = ctx.live.nodes.get(num)
        if node is None:
            raise HTTPException(404, "Nodo non trovato")
        node["is_mine"] = body.mine
        ctx.store.upsert_node(node, is_mine=body.mine)  # inserisce se manca nel database
        ctx.store.commit()
        ctx.live.mark_changed(num)
        ctx.alerts()
        return _public(node)

    @app.get("/api/links", dependencies=[Depends(require_auth)])
    async def list_links(hours: float = 24):
        return ctx.store.links(time.time() - hours * 3600)

    @app.get("/api/alerts", dependencies=[Depends(require_auth)])
    async def list_alerts():
        return ctx.alerts()

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
        if changes.get("update_token") == MASK:
            del changes["update_token"]  # invariato
        try:
            saved = save_settings(ctx.conn, changes)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await ctx.on_settings_changed(saved)
        ctx.alerts()  # soglie cambiate: pubblica subito gli avvisi aggiornati
        return _mask_settings(saved)

    @app.get("/api/mqtt/channels", dependencies=[Depends(require_auth)])
    async def mqtt_channels():
        wanted = load_settings(ctx.conn)["mqtt_channels"]
        counts = ctx.mqtt_channel_counts()
        rows = [{"name": n, "count_1h": c, "enabled": not wanted or n in wanted}
                for n, c in counts.items()]
        rows.sort(key=lambda r: (-r["count_1h"], r["name"]))
        return rows

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

    # ---- configurazione dei nodi ----
    async def config_call(result):
        """Esegue (anche in await) una chiamata al servizio: ConfigError -> HTTP."""
        try:
            if asyncio.iscoroutine(result):
                return await result
            return result
        except ConfigError as e:
            raise HTTPException(e.status, e.message)

    def cfg(fn, *args, **kw):
        try:
            return fn(*args, **kw)
        except ConfigError as e:
            raise HTTPException(e.status, e.message)

    @app.get("/api/config/schema", dependencies=[Depends(require_auth)])
    async def config_schema_route():
        return config_schema()

    @app.get("/api/radios/{radio_id}/admin-key", dependencies=[Depends(require_auth)])
    async def radio_admin_key(radio_id: str):
        return await config_call(ctx.config.admin_key(radio_id))

    @app.get("/api/config/jobs/{job_id}", dependencies=[Depends(require_auth)])
    async def config_job(job_id: int):
        return cfg(ctx.config.job, job_id)

    @app.get("/api/config/backups/{backup_id}", dependencies=[Depends(require_auth)])
    async def config_backup(backup_id: int):
        return cfg(ctx.config.backup, backup_id)

    @app.post("/api/config/backups/{backup_id}/preview-restore",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def config_preview_restore(backup_id: int):
        return cfg(ctx.config.preview_restore, backup_id)

    @app.get("/api/config/{node_id}", dependencies=[Depends(require_auth)])
    async def config_last(node_id: str):
        return cfg(ctx.config.last_read, node_id)

    @app.post("/api/config/{node_id}/read", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def config_read(node_id: str, body: ConfigReadBody):
        return cfg(ctx.config.start_read, node_id, body.radio_id, body.sections)

    @app.post("/api/config/{node_id}/preview",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def config_preview(node_id: str, body: ConfigPreviewBody):
        return cfg(ctx.config.preview, node_id, body.changes)

    @app.post("/api/config/{node_id}/apply", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def config_apply(node_id: str, body: ConfigApplyBody):
        return cfg(ctx.config.apply, node_id, body.preview_id, body.confirm_risky)

    @app.post("/api/config/{node_id}/reboot", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def config_reboot(node_id: str, body: ConfigRebootBody):
        return cfg(ctx.config.reboot, node_id, body.radio_id, body.confirm)

    @app.post("/api/config/{node_id}/fixed-position", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def config_fixed_position(node_id: str, body: ConfigFixedPositionBody):
        return cfg(ctx.config.fixed_position, node_id, body.radio_id, body.confirm,
                   body.lat, body.lon, body.alt, body.remove)

    @app.get("/api/config/{node_id}/backups", dependencies=[Depends(require_auth)])
    async def config_backups(node_id: str):
        return cfg(ctx.config.backups, node_id)

    @app.post("/api/config/{node_id}/channels/{index}/reveal-psk",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def config_reveal_psk(node_id: str, index: int):
        return await config_call(ctx.config.reveal_psk(node_id, index))

    # ---- copertura ----
    def coverage_session(sid: int) -> dict:
        s = ctx.store.get_session(sid)
        if s is None:
            raise HTTPException(404, "Sessione non trovata")
        return s

    def radio_info(radio_id: str) -> dict | None:
        return next((r for r in ctx.radios.radios() if r["id"] == radio_id), None)

    def position_age(node: dict | None) -> float | None:
        # position_time e' l'istante di ricezione dell'ultima posizione (lo scrive l'ingestor
        # con rx_time), non un'ora del dispositivo: e' affidabile anche senza orologio sul nodo
        if not node or not node.get("position_time"):
            return None
        return max(0.0, time.time() - node["position_time"])

    def latest_position(num: int, node: dict | None) -> tuple[float | None, int | None]:
        """(eta, precision_bits) dell'ultima posizione ricevuta, non della migliore."""
        seen = ctx.coverage.position_seen(num)
        if seen is not None:
            return max(0.0, time.time() - seen[0]), seen[1]
        age = position_age(node)
        return age, (node.get("precision_bits") if node and age is not None else None)

    @app.get("/api/coverage/check", dependencies=[Depends(require_auth)])
    async def coverage_check(radio_id: str, mobile_id: str):
        num = _mobile_num(mobile_id)
        radio = radio_info(radio_id)
        connected = bool(radio and radio["state"] == "connected")
        node = ctx.live.nodes.get(num)
        age, bits = latest_position(num, node)
        base = None
        if radio and radio.get("my_node_id"):
            b = ctx.live.nodes.get(_num_from_id(radio["my_node_id"]))
            if b and b.get("lat") is not None and b.get("lon") is not None:
                base = {"lat": b["lat"], "lon": b["lon"]}
        return {"radio_connected": connected,
                "radio_channels": [{"index": ch["index"], "name": ch["name"]}
                                   for ch in (radio["channels"] if radio else [])],
                "mobile_known": node is not None, "position_age_s": age,
                "precision_bits": bits, "precision_m": precision_m(bits),
                "gps_ok": age is not None and age <= GPS_MAX_AGE_S,
                "rangetest_age_s": ctx.coverage.rangetest_age(radio_id, num),
                "base_position": base}

    @app.post("/api/coverage/prepare", dependencies=[Depends(require_auth), Depends(require_json)])
    async def coverage_prepare(body: CoveragePrepareBody):
        return await config_call(ctx.config.prepare(
            body.radio_id, body.mobile_id, body.interval_s, body.private_channel))

    @app.post("/api/coverage/restore", dependencies=[Depends(require_auth), Depends(require_json)])
    async def coverage_restore(body: CoveragePlanBody):
        return await config_call(ctx.config.restore_plan(body.plan_id))

    @app.get("/api/coverage/prepare/last", dependencies=[Depends(require_auth)])
    async def coverage_prepare_last():
        return ctx.config.last_plan()

    @app.post("/api/coverage/prepare/{plan_id}/apply", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def coverage_prepare_apply(plan_id: int, body: CoveragePlanApplyBody):
        return cfg(ctx.config.apply_plan, plan_id, body.confirm_risky)

    @app.get("/api/coverage/sessions", dependencies=[Depends(require_auth)])
    async def coverage_sessions():
        return [ctx.coverage.summary(s) for s in ctx.store.sessions()]

    @app.post("/api/coverage/sessions", status_code=201,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def coverage_start(body: CoverageStartBody):
        if (body.base_lat is None) != (body.base_lon is None):
            raise HTTPException(400, "base_lat e base_lon vanno indicate insieme")
        _check_latlon(body.base_lat, body.base_lon)
        num = _mobile_num(body.mobile_id)
        radio = radio_info(body.radio_id)
        if radio is None:
            raise HTTPException(404, "Radio non trovata")
        if ctx.store.active_session() is not None:
            raise HTTPException(409, "C'è già una sessione in corso")
        if radio["state"] != "connected":
            raise HTTPException(400, "La radio non è collegata")
        node = ctx.live.nodes.get(num)
        age, bits = latest_position(num, node)
        if age is None or age > GPS_MAX_AGE_S:
            raise HTTPException(400, NO_GPS_MSG)
        radius = precision_m(bits)
        if radius is not None and not body.accept_approx:
            return JSONResponse(status_code=400, content={
                "code": "approx_position",
                "detail": (f"Le posizioni del nodo mobile sono approssimate (circa ±{_radius_text(radius)}): "
                           "usa un canale privato con precisione piena oppure continua "
                           "sapendolo.")})
        try:
            return ctx.coverage.start_session(
                body.radio_id, num, body.mode, body.interval_s,
                (body.name or "").strip() or None, body.base_lat, body.base_lon)
        except SessionActive as e:
            raise HTTPException(409, str(e))

    @app.post("/api/coverage/sessions/{sid}/stop", dependencies=[Depends(require_auth)])
    async def coverage_stop(sid: int):
        s = coverage_session(sid)
        if s["ended"] is not None:
            raise HTTPException(409, "La sessione è già terminata")
        return ctx.coverage.stop_session()

    @app.patch("/api/coverage/sessions/{sid}",
               dependencies=[Depends(require_auth), Depends(require_json)])
    async def coverage_patch(sid: int, body: CoveragePatchBody):
        coverage_session(sid)
        if (body.base_lat is None) != (body.base_lon is None):
            raise HTTPException(400, "base_lat e base_lon vanno indicate insieme")
        _check_latlon(body.base_lat, body.base_lon)
        fields = body.model_dump(exclude_none=True)
        if "name" in fields:
            fields["name"] = fields["name"].strip()
            if not fields["name"]:
                raise HTTPException(400, "Il nome non può essere vuoto")
        summary = ctx.coverage.update_session(sid, **fields)
        ctx.bus.publish({"type": "coverage", "session": summary, "point": None})
        return summary

    @app.delete("/api/coverage/sessions/{sid}", dependencies=[Depends(require_auth)])
    async def coverage_delete(sid: int):
        s = coverage_session(sid)
        if s["ended"] is None:
            raise HTTPException(409, "Ferma la sessione prima di eliminarla")
        ctx.store.delete_session(sid)
        ctx.conn.commit()
        return {"ok": True}

    @app.get("/api/coverage/sessions/{sid}", dependencies=[Depends(require_auth)])
    async def coverage_detail(sid: int):
        coverage_session(sid)
        return ctx.coverage.detail(sid)

    # ---- aggiornamenti ----
    async def update_call(fn):
        if ctx.updater is None:
            raise HTTPException(503, "Aggiornamenti non disponibili")
        try:
            return await fn()
        except UpdateError as e:
            raise HTTPException(e.status, str(e))

    async def _update_status():
        return ctx.updater.status()

    @app.get("/api/update/status", dependencies=[Depends(require_auth)])
    async def update_status():
        return await update_call(_update_status)

    @app.post("/api/update/check", dependencies=[Depends(require_auth)])
    async def update_check():
        return await update_call(lambda: ctx.updater.check())

    @app.post("/api/update/download", status_code=202, dependencies=[Depends(require_auth)])
    async def update_download():
        return await update_call(lambda: ctx.updater.start_download())

    @app.post("/api/update/install", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def update_install(body: UpdateInstallBody):
        return await update_call(lambda: ctx.updater.install(body.confirm))

    # ---- mappe offline ----
    async def maps_call(fn):
        # fn e' una funzione: la coroutine nasce solo se il gestore esiste (niente "never awaited")
        if ctx.maps is None:
            raise HTTPException(503, "Mappe offline non disponibili")
        try:
            return await fn()
        except MapsError as e:
            raise HTTPException(e.status, str(e))

    async def _maps_status():
        return ctx.maps.status()

    @app.get("/api/maps", dependencies=[Depends(require_auth)])
    async def maps_status():
        return await maps_call(_maps_status)

    @app.post("/api/maps/estimate", dependencies=[Depends(require_auth), Depends(require_json)])
    async def maps_estimate(body: MapsEstimateBody):
        return await maps_call(lambda: ctx.maps.estimate(body.kind, body.bbox))

    @app.post("/api/maps/download", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def maps_download(body: MapsDownloadBody):
        return await maps_call(lambda: ctx.maps.start(body.kind, body.bbox, body.name))

    @app.post("/api/maps/jobs/{job_id}/cancel", dependencies=[Depends(require_auth)])
    async def maps_cancel(job_id: str):
        return await maps_call(lambda: ctx.maps.cancel(job_id))

    @app.delete("/api/maps/{map_id}", dependencies=[Depends(require_auth)])
    async def maps_delete(map_id: str):
        await maps_call(lambda: ctx.maps.delete(map_id))
        return {"ok": True}

    @app.get("/api/maps/style-info", dependencies=[Depends(require_auth)])
    async def maps_style_info():
        if ctx.maps is None:
            return {"has_offline": False, "maxzoom": 0, "bounds": None}
        return ctx.maps.tiles.info()

    # def sincrona: gira nel threadpool, la lettura dal disco non blocca l'event loop
    @app.get("/tiles/{z}/{x}/{y}.mvt", dependencies=[Depends(require_auth)])
    def tiles(z: int, x: int, y: int):
        if ctx.maps is None or not (0 <= z <= 22) or not (0 <= x < 2 ** z) or not (0 <= y < 2 ** z):
            return Response(status_code=204)
        found = ctx.maps.tiles.get(z, x, y)
        if found is None:
            return Response(status_code=204)
        data, enc = found
        headers = {"Cache-Control": "private, max-age=300"}
        if enc:
            headers["Content-Encoding"] = enc
        return Response(data, media_type="application/x-protobuf", headers=headers)

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
