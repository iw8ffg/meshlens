"""API REST e WebSocket. Tutti gli handler sono async: la connessione sqlite e
condivisa e va usata solo dal thread dell'event loop."""
import logging
import asyncio
import copy
import contextlib
import ipaddress
import math
import mimetypes
import re
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

from . import api_prediction, api_storeforward
from .api_data import register_data_routes
from .alerts import CHUTIL_MIN_SAMPLES, CHUTIL_WINDOW_S, compute_alerts, sort_key
from .auth import LOOPBACK, MIN_PIN, MIN_PIN_LAN, Auth, LockedError
from .bus import Bus
from .channel_link import parse_channel_url
from .ingest import revive_node
from .config_model import schema as config_schema
from .conversations import summaries, waypoint_json
from .config_service import ConfigError
from .coverage import SessionActive, precision_m
from .geo import CountryLocator
from .live import LiveState
from .diagnostics import build_bundle
from .maintenance import compact, read_db_stats
from .maps import MapsError
from . import notify
from .notify import TELEGRAM_NO_CHAT, TOAST_UNAVAILABLE, Notifier, NotifyError
from .updater import UpdateError
from .mqtt_publish import MqttSendError, pick_broker
from .radio import RadioBusy
from .radio_manager import NoRadioConnected, TracerouteThrottled
from .backup import NAME_RE, BackupUnusable, PendingRestore
from .secretbox import SECRET_KEYS
from .settings import (DEFAULT_BROKER_ID, MASK, export_settings, find_broker, load_settings,
                       mask_secrets, merge_channels, prepare_import, resolve_broker_secrets,
                       resolve_extra_keys, save_settings)
from .serving import tls_status
from .store import Store

COOKIE = "meshlens_session"
# su HTTPS un nome diverso: un cookie Secure dello stesso nome messo da https://IP:8687
# impedirebbe al browser di salvare quello di http://IP:8686 (stesso host, porta ignorata)
COOKIE_HTTPS = "meshlens_session_s"
COOKIE_MAX_AGE = 365 * 24 * 3600
LOCAL_HOSTS = (*LOOPBACK, "localhost")
INTERNAL_KEYS = ()
# interruttori che si accendono solo dalle rotte dedicate (bot, webhook: WP5; ospite: WP6):
# PUT /api/settings e l'importazione possono solo spegnerli
DEDICATED_SWITCHES = ("bot_enabled", "webhook_enabled", "guest_enabled")
DEDICATED_SWITCH_MSG = "Questa funzione si attiva dalla sua pagina in Impostazioni"


WS_SEND_TIMEOUT_S = 10
WS_RECHECK_S = 30  # ricontrollo della sessione dei WebSocket aperti (scadenza)


async def send_with_timeout(ws, msg: dict, timeout: float = WS_SEND_TIMEOUT_S) -> bool:
    """Invia al client; False se non accetta i dati entro `timeout` (client bloccato)."""
    try:
        await asyncio.wait_for(ws.send_json(msg), timeout)
        return True
    except asyncio.TimeoutError:
        return False


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
    storeforward: object | None = None  # StoreForwardService
    prediction: object | None = None  # PredictionManager
    data_dir: Path | None = None
    config: object | None = None  # ConfigService
    maps: object | None = None  # MapsManager
    updater: object | None = None  # Updater
    # canali MQTT visti nell'ultima ora (broker=id per uno solo) e broker che li hanno visti
    mqtt_channel_counts: Callable[..., dict] = lambda **_: {}
    mqtt_channel_brokers: Callable[[], dict] = lambda: {}
    mqtt_sender: object | None = None  # MqttSender
    db_path: Path | None = None
    last_purge: Callable[[], dict | None] = lambda: None
    backups: object | None = None  # BackupManager
    db_health: Callable[[], str] = lambda: "non controllata"
    log_dir: Path | None = None
    started_at: float = field(default_factory=time.time)
    exit_callback: Callable[[], None] | None = None  # impostata dal lanciatore
    # stato dell'HTTPS per la rete (impostato da chi avvia il server) ed errori degli ascolti
    tls: dict = field(default_factory=tls_status)
    tls_errors: list[str] = field(default_factory=list)
    # notifiche di Windows: impostata dal lanciatore con l'icona (None senza icona)
    toast: Callable[[str, str], None] | None = None
    notifier: Notifier | None = None  # se manca se ne crea uno sulle impostazioni del database
    # 1.6: servizi delle estensioni (ctx.ext["<nome>"]) e sorgenti di avvisi aggiuntive:
    # (now, impostazioni, avvisi precedenti per chiave) -> avvisi nel formato di compute_alerts
    ext: dict[str, object] = field(default_factory=dict)
    alert_sources: list[Callable[[float, dict, dict[str, dict]], list[dict]]] = field(
        default_factory=list)
    _alerts: list = field(default_factory=list)
    _alerts_ready: bool = False

    def __post_init__(self) -> None:
        if self.notifier is None:
            self.notifier = Notifier(
                lambda: load_settings(self.conn), lambda: self.toast,
                lambda: self.radios.radios() if self.radios is not None else [], time.time,
                get_mqtt_connected=lambda: bool(self.mqtt_status()["connected"]))

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
        now = time.time()
        mine = [n for n in self.live.nodes.values() if n.get("is_mine")]
        stats = self.store.channel_util_stats([n["num"] for n in mine], now - CHUTIL_WINDOW_S)
        chutil = {n["id"]: stats[n["num"]][0] for n in mine
                  if n["num"] in stats and stats[n["num"]][1] >= CHUTIL_MIN_SAMPLES}
        settings = load_settings(self.conn)
        prev = {a["key"]: a for a in old}
        new = compute_alerts(self.live.nodes.values(), settings, now, prev, chutil)
        for src in list(self.alert_sources):
            try:
                new.extend(src(now, settings, prev))
            except Exception:  # noqa: BLE001 - una sorgente rotta non ferma gli altri avvisi
                logging.getLogger(__name__).exception("Sorgente di avvisi %s fallita",
                                                      getattr(src, "__qualname__", src))
        new.sort(key=sort_key)
        self._alerts = new
        if [(a["key"], a["value"]) for a in new] != [(a["key"], a["value"]) for a in old]:
            self.bus.publish({"type": "alerts", "alerts": new})
        if self._alerts_ready:
            try:
                self.notifier.on_alerts(old, new)
            except Exception:  # noqa: BLE001 - le notifiche non fermano gli avvisi
                logging.getLogger(__name__).exception("Notifiche degli avvisi non riuscite")
        # il primo calcolo (avvio) non notifica: un nodo muto da giorni non avvisa a ogni avvio
        self._alerts_ready = True
        return new


class MapsEstimateBody(BaseModel):
    kind: Literal["world", "italy", "area"]
    bbox: list[float] | None = None


class MapsDownloadBody(BaseModel):
    kind: Literal["tool", "world", "italy", "area"]
    bbox: list[float] | None = None
    name: str | None = Field(None, max_length=80)


class MqttSendBody(BaseModel):
    text: str
    channel: str = "LongFast"
    to: str | None = None
    confirm_public: bool = False
    broker: str | None = Field(None, max_length=24)  # None = primo broker attivo
    reply_id: int | None = Field(None, ge=1, le=4294967295)
    emoji: bool = False


class ImportLinkBody(BaseModel):
    url: str = Field(max_length=4096)


class ImportRadioBody(BaseModel):
    radio_id: str = Field(max_length=64)


class UpdateInstallBody(BaseModel):
    confirm: bool = False


class CompactBody(BaseModel):
    confirm: bool = False


class RestoreBody(BaseModel):
    confirm: bool = False


class CleanupBody(BaseModel):
    days: int


class MineBody(BaseModel):
    mine: bool


class FavoriteBody(BaseModel):
    favorite: bool


class PinBody(BaseModel):
    pin: str


class ChangePinBody(BaseModel):
    current_pin: str
    new_pin: str


class RadioBody(BaseModel):
    kind: str
    address: str
    name: str | None = None


class TracerouteBody(BaseModel):
    radio_id: str | None = None


class WaypointBody(BaseModel):
    name: str
    description: str = ""
    icon: str = "📍"
    lat: float
    lon: float
    expire_h: int | None = None
    channel_index: int = 0


class ReadBody(BaseModel):
    key: str = Field(max_length=64)
    time: float


CONV_KEY_RE = re.compile(r"^(ch|dm):r[0-9a-f]{8}:(\d|!?[0-9a-f]{8})$")
WAYPOINT_ONLY_MINE = "Puoi eliminare solo i tuoi waypoint"
WAYPOINT_UNKNOWN = "Waypoint non trovato"
CONV_KEY_INVALID = "Conversazione non valida"
CONV_TIME_INVALID = "Orario non valido"
TELEGRAM_NOT_CONFIGURED = notify.TELEGRAM_NOT_CONFIGURED
TELEGRAM_NO_TOKEN = "Inserisci prima il token del bot"


class NotifyTestBody(BaseModel):
    channel: Literal["toast", "telegram"]


class SendBody(BaseModel):
    text: str
    channel_index: int = 0
    to: str | None = None
    reply_id: int | None = Field(None, ge=1, le=4294967295)
    emoji: bool = False


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


_mask_settings = mask_secrets

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


def _is_https(scheme: str) -> bool:
    return scheme in ("https", "wss")


def cookie_name(scheme: str) -> str:
    """Nome del cookie di sessione per lo schema della richiesta (anche ws/wss)."""
    return COOKIE_HTTPS if _is_https(scheme) else COOKIE


def session_token(conn: Request | WebSocket) -> str | None:
    return conn.cookies.get(cookie_name(conn.url.scheme))


def create_app(ctx: AppContext) -> FastAPI:
    app = FastAPI(title="MeshLens")

    @app.middleware("http")
    async def check_host(request: Request, call_next):
        if not _host_allowed(request.headers.get("host")):
            return JSONResponse({"detail": "Host non consentito"}, status_code=400)
        return await call_next(request)

    def set_cookie(request: Request, response: Response, token: str) -> None:
        # Secure solo su HTTPS e mai per il loopback (che resta in HTTP su 127.0.0.1)
        https = _is_https(request.url.scheme)
        response.set_cookie(cookie_name(request.url.scheme), token, max_age=COOKIE_MAX_AGE,
                            httponly=True, samesite="strict",
                            secure=https and not is_loopback(request), path="/")

    def is_loopback(request: Request) -> bool:
        return request.client is not None and request.client.host in LOOPBACK

    def is_local(request: Request) -> bool:
        return request.client is not None and request.client.host in LOCAL_HOSTS

    async def require_json(request: Request) -> None:
        ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
        if ctype != "application/json":
            raise HTTPException(415, "Content-Type non supportato")

    async def require_auth(request: Request) -> None:
        if not ctx.auth.check(session_token(request)):
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

    def client_ip(request: Request) -> str:
        return request.client.host if request.client else "unknown"

    def min_pin_len() -> int:
        return MIN_PIN_LAN if load_settings(ctx.conn)["lan_access"] else MIN_PIN

    def locked_response(e: LockedError) -> JSONResponse:
        return JSONResponse({"detail": "Troppi tentativi, riprova più tardi"},
                            status_code=429, headers={"Retry-After": str(e.retry_after)})

    @app.get("/api/auth/status")
    async def auth_status(request: Request):
        # PIN corto per l'accesso dalla rete; null finché la lunghezza non è nota
        # (PIN di una versione precedente: si impara al prossimo login riuscito)
        length = ctx.auth.pin_length()
        lan = load_settings(ctx.conn)["lan_access"]
        authenticated = ctx.auth.check(session_token(request))
        out = {"pin_set": ctx.auth.pin_is_set(),
               "authenticated": authenticated,
               "is_local": is_local(request)}
        if authenticated or is_local(request):
            # chi non e' autenticato e viene dalla rete non deve sapere se il PIN e' corto
            out["pin_short"] = None if length is None else bool(lan and length < MIN_PIN_LAN)
            # cifre minime per un PIN nuovo (primo PIN o cambio)
            out["pin_min"] = MIN_PIN_LAN if lan else MIN_PIN
        return out

    setup_lock = asyncio.Lock()

    @app.post("/api/auth/setup", dependencies=[Depends(require_json)])
    async def auth_setup(body: PinBody, request: Request, response: Response):
        if ctx.auth.pin_is_set() or not is_local(request):
            raise HTTPException(403, "Impostazione del PIN non consentita")
        async with setup_lock:  # due setup in parallelo non si sovrascrivono
            if ctx.auth.pin_is_set():  # l'hash e' fuori dal loop: ricontrolla
                raise HTTPException(403, "Impostazione del PIN non consentita")
            try:
                await ctx.auth.aset_pin(body.pin, min_pin_len())
            except ValueError as e:
                raise HTTPException(400, str(e))
        try:
            token = await ctx.auth.alogin(body.pin, client_ip(request),
                                          request.headers.get("user-agent"))
        except LockedError as e:
            return locked_response(e)
        set_cookie(request, response, token)
        return {"ok": True}

    @app.post("/api/auth/login", dependencies=[Depends(require_json)])
    async def auth_login(body: PinBody, request: Request, response: Response):
        try:
            token = await ctx.auth.alogin(body.pin, client_ip(request),
                                          request.headers.get("user-agent"))
        except LockedError as e:
            return locked_response(e)
        except PermissionError:
            raise HTTPException(401, "PIN errato")
        set_cookie(request, response, token)
        return {"ok": True}

    @app.post("/api/auth/pin", dependencies=[Depends(require_auth), Depends(require_json)])
    async def auth_change_pin(body: ChangePinBody, request: Request):
        try:
            await ctx.auth.change_pin(session_token(request), body.current_pin,
                                      body.new_pin, min_pin_len(), client_ip(request))
        except ValueError as e:
            raise HTTPException(400, str(e))
        except LockedError as e:
            return locked_response(e)
        except PermissionError:
            # 403, non 401: il client tratta il 401 come sessione scaduta
            raise HTTPException(403, "PIN attuale errato")
        return {"ok": True}

    @app.get("/api/auth/sessions", dependencies=[Depends(require_auth)])
    async def auth_sessions(request: Request):
        return ctx.auth.sessions(session_token(request))

    @app.delete("/api/auth/sessions/{session_id}", dependencies=[Depends(require_auth), Depends(require_json)])
    async def auth_revoke(session_id: str):
        if not ctx.auth.revoke(session_id):
            raise HTTPException(404, "Sessione non trovata")
        return {"ok": True}

    @app.post("/api/auth/sessions/revoke-others", dependencies=[Depends(require_auth), Depends(require_json)])
    async def auth_revoke_others(request: Request):
        return {"ok": True, "revoked": ctx.auth.revoke_others(session_token(request))}

    @app.post("/api/auth/logout", dependencies=[Depends(require_json)])
    async def auth_logout(request: Request, response: Response):
        token = session_token(request)
        if token:
            ctx.auth.logout(token)
        response.delete_cookie(cookie_name(request.url.scheme), path="/")
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

    def _live_or_revive(num: int) -> dict:
        """Nodo in memoria; se il limite dei nodi lo ha tolto ma e' archiviato (i client lo
        mostrano ancora) lo rimette in memoria dalla riga del database."""
        node = ctx.live.nodes.get(num)
        if node is None:
            if ctx.store.get_node(num) is None:
                raise HTTPException(404, "Nodo non trovato")
            node = ctx.live.nodes[num] = revive_node(ctx.store, num)
        return node

    @app.put("/api/nodes/{node_id}/mine",
             dependencies=[Depends(require_auth), Depends(require_json)])
    async def set_mine(node_id: str, body: MineBody):
        num = _num_from_id(node_id)
        node = _live_or_revive(num)
        node["is_mine"] = body.mine
        ctx.store.upsert_node(node, is_mine=body.mine)  # inserisce se manca nel database
        ctx.store.commit()
        ctx.live.mark_changed(num)
        ctx.alerts()
        return _public(node)

    @app.put("/api/nodes/{node_id}/favorite",
             dependencies=[Depends(require_auth), Depends(require_json)])
    async def set_favorite(node_id: str, body: FavoriteBody):
        num = _num_from_id(node_id)
        node = _live_or_revive(num)
        node["is_favorite"] = body.favorite
        ctx.store.upsert_node(node, is_favorite=body.favorite)  # inserisce se manca nel database
        ctx.store.commit()
        ctx.live.mark_changed(num)  # pubblicato ai client dal ciclo _publish_changed
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
                            limit: int = Query(200, ge=1, le=1000),
                            broker: str | None = Query(None, max_length=24)):
        wanted = _parse_countries(country)
        out = []
        for msg in reversed(ctx.live.messages):
            if len(out) >= limit:
                break
            if broker is not None and msg.get("broker") != broker:
                continue
            if _matches(msg.get("country"), wanted):
                out.append(msg)
        return out

    @app.get("/api/messages/history", dependencies=[Depends(require_auth)])
    async def message_history(country: str | None = None, before: float | None = None,
                              limit: int = Query(200, ge=1, le=1000),
                              broker: str | None = Query(None, max_length=24)):
        wanted = _parse_countries(country)
        if wanted is not None:
            # lo storico contiene solo nazioni salvate: "none" non c'e mai
            wanted = [c for c in wanted if c != "none"]
            if not wanted:
                return []
        return ctx.store.messages(wanted, before, limit, broker=broker)

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

    def check_lan_pin(changes: dict) -> None:
        """L'accesso dalla rete non si attiva con un PIN piu' corto del minimo per la LAN."""
        if changes.get("lan_access") is not True:
            return
        length = ctx.auth.pin_length()
        if length is not None and length < MIN_PIN_LAN:
            raise HTTPException(
                400, "Per attivare l'accesso dalla rete serve un PIN di almeno 6 cifre: cambia prima il PIN")

    def check_dedicated_switches(changes: dict) -> None:
        """bot, webhook e accesso ospite non si accendono da qui (spegnerli resta possibile)."""
        if any(changes.get(k) is True for k in DEDICATED_SWITCHES):
            raise HTTPException(400, DEDICATED_SWITCH_MSG)

    @app.put("/api/settings", dependencies=[Depends(require_auth), Depends(require_json)])
    async def put_settings(changes: dict):
        changes = dict(changes)
        check_lan_pin(changes)
        check_dedicated_switches(changes)
        if "mqtt_brokers" in changes:
            changes.pop("mqtt", None)  # vista di compatibilita': vale la lista dei broker
            try:
                changes["mqtt_brokers"] = resolve_broker_secrets(
                    changes["mqtt_brokers"], load_settings(ctx.conn)["mqtt_brokers"])
            except ValueError as e:
                raise HTTPException(400, str(e))
        mqtt = changes.get("mqtt")
        if isinstance(mqtt, dict) and mqtt.get("password") == MASK:
            changes["mqtt"] = {k: v for k, v in mqtt.items() if k != "password"}
        mqtt = changes.get("mqtt")
        if isinstance(mqtt, dict) and "extra_keys" in mqtt:
            try:
                changes["mqtt"] = {**mqtt, "extra_keys": resolve_extra_keys(
                    mqtt["extra_keys"], load_settings(ctx.conn)["mqtt"]["extra_keys"])}
            except ValueError as e:
                raise HTTPException(400, str(e))
        for key in SECRET_KEYS:
            if changes.get(key) == MASK:
                del changes[key]  # invariato
        try:
            saved = save_settings(ctx.conn, changes)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await ctx.on_settings_changed(saved)
        ctx.alerts()  # soglie cambiate: pubblica subito gli avvisi aggiornati
        return _mask_settings(saved)

    @app.get("/api/settings/export", dependencies=[Depends(require_auth)])
    async def export_settings_file(request: Request, secrets: int = Query(0, ge=0, le=1)):
        if secrets and not is_local(request):
            raise HTTPException(403, "I segreti si esportano solo da questo PC")
        doc = export_settings(load_settings(ctx.conn), bool(secrets))
        fname = f"meshlens-impostazioni-{time.strftime('%Y%m%d')}.json"
        return JSONResponse(doc, headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    @app.post("/api/settings/import", dependencies=[Depends(require_auth), Depends(require_json)])
    async def import_settings(body: dict):
        try:
            changes, skipped = prepare_import(body, load_settings(ctx.conn))
            check_lan_pin(changes)
            check_dedicated_switches(changes)
            saved = save_settings(ctx.conn, changes)
        except ValueError as e:
            raise HTTPException(400, str(e))
        await ctx.on_settings_changed(saved)
        ctx.alerts()
        return {"settings": mask_secrets(saved), "skipped": skipped}

    @app.post("/api/mqtt/send", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def mqtt_send(body: MqttSendBody):
        if ctx.mqtt_sender is None:
            raise HTTPException(503, "Invio MQTT non disponibile")
        try:
            message = ctx.mqtt_sender.send(body.text, body.channel, body.to, body.confirm_public,
                                           broker=body.broker, reply_id=body.reply_id,
                                           emoji=body.emoji)
        except MqttSendError as e:
            return JSONResponse(status_code=e.status, content={"detail": e.message, "code": e.code})
        if body.confirm_public:
            # la conferma si ricorda per quel broker: la prossima volta non viene richiesta
            try:
                current = load_settings(ctx.conn)
                bid = pick_broker(current, body.broker)["id"]
                confirmed = current.get("mqtt_send_confirmed_brokers") or []
                changes: dict = {}
                if bid not in confirmed:
                    changes["mqtt_send_confirmed_brokers"] = [*confirmed, bid]
                if bid == DEFAULT_BROKER_ID and not current.get("mqtt_send_confirmed"):
                    changes["mqtt_send_confirmed"] = True
                if changes:
                    await ctx.on_settings_changed(save_settings(ctx.conn, changes))
            except Exception:  # il messaggio e' gia' partito: non si risponde con un errore
                logging.getLogger(__name__).exception("Salvataggio della conferma MQTT fallito")
        return {"message": message}

    async def import_channels(broker_id: str, entries_fn):
        """Importa i canali nel broker salvato; le PSK escono solo mascherate."""
        if find_broker(load_settings(ctx.conn), broker_id) is None:
            raise HTTPException(404, "Broker non trovato")
        try:
            entries = await entries_fn()
        except ValueError as e:
            raise HTTPException(400, str(e))
        current = load_settings(ctx.conn)  # dopo l'attesa: nessuna modifica concorrente persa
        if find_broker(current, broker_id) is None:
            raise HTTPException(404, "Broker non trovato")
        brokers = copy.deepcopy(current["mqtt_brokers"])
        added, skipped = merge_channels(find_broker({"mqtt_brokers": brokers}, broker_id), entries)
        saved = current
        if added:
            try:
                saved = save_settings(ctx.conn, {"mqtt_brokers": brokers})
            except ValueError as e:
                raise HTTPException(400, str(e))
            await ctx.on_settings_changed(saved)
        return {"settings": _mask_settings(saved), "added": added, "skipped": skipped}

    @app.post("/api/mqtt/brokers/{broker_id}/channels/import-link",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def mqtt_import_link(broker_id: str, body: ImportLinkBody):
        async def entries():
            return parse_channel_url(body.url)
        return await import_channels(broker_id, entries)

    @app.post("/api/mqtt/brokers/{broker_id}/channels/import-radio",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def mqtt_import_radio(broker_id: str, body: ImportRadioBody):
        if ctx.config is None:
            raise HTTPException(503, "Configurazione dei nodi non disponibile")

        async def entries():
            return await config_call(ctx.config.channel_secrets(body.radio_id))
        return await import_channels(broker_id, entries)

    @app.post("/api/mqtt/brokers/{broker_id}/channels/{index}/reveal",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def mqtt_reveal_channel_psk(broker_id: str, index: int, request: Request):
        if not is_loopback(request):
            raise HTTPException(403, "Le chiavi si mostrano solo da questo PC")
        broker = find_broker(load_settings(ctx.conn), broker_id)
        if broker is None:
            raise HTTPException(404, "Broker non trovato")
        if not 0 <= index < len(broker["channels"]):
            raise HTTPException(404, "Canale non trovato")
        return {"psk": broker["channels"][index]["psk"]}

    @app.get("/api/mqtt/channels", dependencies=[Depends(require_auth)])
    async def mqtt_channels(broker: str | None = Query(None, max_length=24)):
        settings = load_settings(ctx.conn)
        if broker is not None and find_broker(settings, broker) is None:
            raise HTTPException(404, "Broker non trovato")
        wanted = settings["mqtt_channels"]
        counts = ctx.mqtt_channel_counts(broker=broker) if broker else ctx.mqtt_channel_counts()
        custom_on: dict[str, list[str]] = {}  # canale personalizzato -> broker che lo hanno
        custom: set[str] = set()  # personalizzati del broker scelto (o di tutti)
        for b in settings["mqtt_brokers"]:
            for ch in b.get("channels", []):
                custom_on.setdefault(ch["name"], []).append(b["id"])
                if broker is None or b["id"] == broker:
                    custom.add(ch["name"])
        seen_on = ctx.mqtt_channel_brokers()
        rows = []
        for n in {*counts, *custom}:
            brokers = list(seen_on.get(n, []))
            brokers += [b for b in custom_on.get(n, []) if b not in brokers]
            rows.append({"name": n, "count_1h": counts.get(n, 0),
                         "enabled": not wanted or n in wanted, "custom": n in custom,
                         "brokers": brokers})
        rows.sort(key=lambda r: (-r["count_1h"], r["name"]))
        return rows

    @app.get("/api/status", dependencies=[Depends(require_auth)])
    async def status():
        return ctx.mqtt_status()

    @app.get("/api/mqtt/status", dependencies=[Depends(require_auth)])
    async def mqtt_status_route():
        return ctx.mqtt_status()

    # ---- HTTPS per la rete ----
    @app.get("/api/tls", dependencies=[Depends(require_auth)])
    async def tls_info():
        info = {**tls_status(), **ctx.tls}
        errors = [e for e in (info["error"], *ctx.tls_errors) if e]
        info["error"] = " ".join(errors) or None
        return info

    # ---- database ----
    @app.get("/api/db", dependencies=[Depends(require_auth)])
    async def db_info():
        if ctx.db_path is None:
            raise HTTPException(503, "Database non disponibile")
        stats = await asyncio.to_thread(read_db_stats, ctx.db_path)
        return {**stats, "integrity": ctx.db_health(), "last_purge": ctx.last_purge()}

    @app.post("/api/db/compact", dependencies=[Depends(require_auth), Depends(require_json)])
    async def db_compact(body: CompactBody):
        if body.confirm is not True:
            raise HTTPException(400, "Conferma richiesta")
        # VACUUM e' bloccante: gira sul loop (la connessione e' solo sua), su richiesta esplicita
        try:
            before, after = compact(ctx.conn)
        except sqlite3.OperationalError:
            # es. un backup o una lettura in corso tengono il database: si riprova dopo
            logging.getLogger(__name__).warning("Compattazione del database non riuscita",
                                                exc_info=True)
            raise HTTPException(409, "Database occupato (backup o lettura in corso): "
                                     "riprova tra qualche minuto")
        return {"before_bytes": before, "after_bytes": after}

    # ---- notifiche esterne ----
    @app.get("/api/notify/status", dependencies=[Depends(require_auth)])
    async def notify_status():
        return ctx.notifier.status()

    @app.post("/api/notify/test", dependencies=[Depends(require_auth), Depends(require_json)])
    async def notify_test(body: NotifyTestBody):
        try:
            if body.channel == "toast":
                if ctx.toast is None:
                    raise HTTPException(400, TOAST_UNAVAILABLE)
                ctx.notifier.test("toast")
            else:
                s = load_settings(ctx.conn)
                if not (s["telegram_token"] and s["telegram_chat_id"]):
                    raise HTTPException(400, TELEGRAM_NOT_CONFIGURED)
                await asyncio.to_thread(ctx.notifier.test, "telegram")
        except NotifyError as e:  # messaggio gia' senza token
            raise HTTPException(502, str(e))
        return {"ok": True}

    @app.post("/api/notify/telegram/chat", dependencies=[Depends(require_auth), Depends(require_json)])
    async def notify_telegram_chat():
        token = load_settings(ctx.conn)["telegram_token"]
        if not token:
            raise HTTPException(400, TELEGRAM_NO_TOKEN)
        try:
            chat_id, title = await asyncio.to_thread(notify.telegram_find_chat, token)
        except NotifyError as e:
            raise HTTPException(404 if str(e) == TELEGRAM_NO_CHAT else 502, str(e))
        return {"chat_id": chat_id, "title": title}

    # ---- diagnostica ----
    @app.get("/api/diagnostics/bundle", dependencies=[Depends(require_auth)])
    async def diagnostics_bundle():
        import platform
        import sys
        from . import __version__
        from .paths import is_frozen
        now = time.time()
        info = {
            "version": __version__, "frozen": is_frozen(), "platform": sys.platform,
            "python": platform.python_version(), "generated_at": now,
            "uptime_s": round(now - ctx.started_at),
            "mqtt": ctx.mqtt_status(),
            "radios": [{"id": r["id"], "kind": r["kind"], "state": r["state"], "error": r["error"]}
                       for r in (ctx.radios.radios() if ctx.radios is not None else [])],
            "db_health": ctx.db_health(), "last_purge": ctx.last_purge(),
        }
        resyncs = getattr(ctx.bus, "resyncs", None)
        if resyncs is not None:
            info["resyncs"] = resyncs
        settings = load_settings(ctx.conn)

        def collect() -> bytes:  # file e database: fuori dal loop, con connessione propria
            info["backups"] = ctx.backups.list() if ctx.backups is not None else []
            if ctx.db_path is not None:
                info["db"] = read_db_stats(ctx.db_path)
            return build_bundle(info, settings, ctx.log_dir)

        data = await asyncio.to_thread(collect)
        fname = f"meshlens-diagnostica-{time.strftime('%Y%m%d-%H%M')}.zip"
        return Response(data, media_type="application/zip",
                        headers={"Content-Disposition": f'attachment; filename="{fname}"'})

    # ---- backup ----
    def backup_mgr():
        if ctx.backups is None:
            raise HTTPException(503, "Backup non disponibili")
        return ctx.backups

    @app.get("/api/backups", dependencies=[Depends(require_auth)])
    async def list_backups():
        return await asyncio.to_thread(backup_mgr().list)

    @app.post("/api/backups", dependencies=[Depends(require_auth), Depends(require_json)])
    async def create_backup():
        try:
            return await backup_mgr().create("manuale")
        except (OSError, sqlite3.Error) as e:
            raise HTTPException(500, f"Backup non riuscito: {e}")

    @app.post("/api/backups/{name}/restore",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def restore_backup(name: str, body: RestoreBody):
        if not NAME_RE.fullmatch(name):
            raise HTTPException(404, "Backup non trovato")
        if body.confirm is not True:
            raise HTTPException(400, "Conferma richiesta")
        try:
            await asyncio.to_thread(backup_mgr().schedule_restore, name)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, "Backup non trovato")
        except BackupUnusable as e:
            raise HTTPException(409, f"Ripristino rifiutato: {e}")
        return {"ok": True, "restart_required": True}

    @app.delete("/api/backups/{name}",
                dependencies=[Depends(require_auth), Depends(require_json)])
    async def delete_backup(name: str):
        try:
            await asyncio.to_thread(backup_mgr().delete, name)
        except (ValueError, FileNotFoundError):
            raise HTTPException(404, "Backup non trovato")
        except PendingRestore:
            raise HTTPException(409, "Backup in attesa di ripristino: non si può eliminare")
        except OSError:
            raise HTTPException(500, "Backup non eliminabile")
        return {"ok": True}

    @app.post("/api/backups/cleanup",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def cleanup_backups(body: CleanupBody):
        if not 1 <= body.days <= 3650:
            raise HTTPException(400, "Giorni non validi: da 1 a 3650")
        deleted = await asyncio.to_thread(backup_mgr().delete_older_than, body.days)
        return {"deleted": deleted}

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

    @app.post("/api/radios/ble-scan", dependencies=[Depends(require_auth), Depends(require_json)])
    async def radio_ble_scan():
        return await radio_call(ctx.radios.ble_scan())

    @app.delete("/api/radios/{radio_id}", dependencies=[Depends(require_auth), Depends(require_json)])
    async def delete_radio(radio_id: str):
        await radio_call(ctx.radios.remove(radio_id))
        return {"ok": True}

    @app.post("/api/radios/{radio_id}/connect", dependencies=[Depends(require_auth), Depends(require_json)])
    async def connect_radio(radio_id: str):
        await radio_call(ctx.radios.connect(radio_id))
        return {"ok": True}

    @app.post("/api/radios/{radio_id}/disconnect", dependencies=[Depends(require_auth), Depends(require_json)])
    async def disconnect_radio(radio_id: str):
        await radio_call(ctx.radios.disconnect(radio_id))
        return {"ok": True}

    @app.post("/api/radios/{radio_id}/send", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def send_radio(radio_id: str, body: SendBody):
        return await radio_call(
            ctx.radios.send(radio_id, body.text, body.channel_index, body.to,
                            reply_id=body.reply_id, emoji=body.emoji))

    # ---- waypoint e conversazioni ----
    def local_nodes() -> tuple[set[str], set[int]]:
        ids = {n["id"] for n in ctx.live.nodes.values() if n.get("is_local_radio")}
        if ctx.radios is not None:
            ids |= ctx.radios.local_ids()
        return ids, {int(i[1:], 16) for i in ids}

    @app.get("/api/waypoints", dependencies=[Depends(require_auth)])
    async def list_waypoints():
        _, nums = local_nodes()
        return [waypoint_json(r, ctx.live.nodes, nums)
                for r in ctx.store.active_waypoints(time.time(), 500)]

    @app.post("/api/radios/{radio_id}/waypoint", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def send_waypoint(radio_id: str, body: WaypointBody):
        try:
            return await radio_call(ctx.radios.send_waypoint(
                radio_id, body.name, body.description, body.icon, body.lat, body.lon,
                body.expire_h, body.channel_index))
        except RadioBusy as e:
            raise HTTPException(409, str(e))
        except RuntimeError as e:
            raise HTTPException(502, str(e))

    @app.delete("/api/waypoints/{wid}", dependencies=[Depends(require_auth), Depends(require_json)])
    async def delete_waypoint(wid: int):
        try:
            await ctx.radios.delete_waypoint(wid)
        except KeyError:
            raise HTTPException(404, WAYPOINT_UNKNOWN)
        except PermissionError:
            raise HTTPException(403, WAYPOINT_ONLY_MINE)
        except (ValueError, RadioBusy) as e:
            raise HTTPException(409, str(e))
        except RuntimeError as e:
            raise HTTPException(502, str(e))
        return {"ok": True}

    @app.get("/api/conversations", dependencies=[Depends(require_auth)])
    async def list_conversations():
        ids, _ = local_nodes()
        return summaries(ctx.store.recent_radio_messages(), ids, ctx.store.read_times(),
                         ctx.store.read_baseline())

    @app.post("/api/conversations/read", dependencies=[Depends(require_auth), Depends(require_json)])
    async def mark_conversation_read(body: ReadBody):
        if not CONV_KEY_RE.fullmatch(body.key):
            raise HTTPException(400, CONV_KEY_INVALID)
        if not math.isfinite(body.time) or body.time > time.time() + 60:
            raise HTTPException(400, CONV_TIME_INVALID)
        read_time = ctx.store.mark_read(body.key, body.time)
        ctx.store.commit()
        ctx.bus.publish({"type": "conv_read", "key": body.key, "time": read_time})
        return {"key": body.key, "read_time": read_time}

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
        except RadioBusy as e:
            raise HTTPException(409, str(e))
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
    async def config_reveal_psk(node_id: str, index: int, request: Request):
        if not is_loopback(request):
            raise HTTPException(403, "Le chiavi si mostrano solo da questo PC")
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

    @app.post("/api/coverage/sessions/{sid}/stop", dependencies=[Depends(require_auth), Depends(require_json)])
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

    @app.delete("/api/coverage/sessions/{sid}", dependencies=[Depends(require_auth), Depends(require_json)])
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

    @app.post("/api/update/check", dependencies=[Depends(require_auth), Depends(require_json)])
    async def update_check():
        return await update_call(lambda: ctx.updater.check())

    @app.post("/api/update/download", status_code=202, dependencies=[Depends(require_auth), Depends(require_json)])
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

    @app.post("/api/maps/jobs/{job_id}/cancel", dependencies=[Depends(require_auth), Depends(require_json)])
    async def maps_cancel(job_id: str):
        return await maps_call(lambda: ctx.maps.cancel(job_id))

    @app.delete("/api/maps/{map_id}", dependencies=[Depends(require_auth), Depends(require_json)])
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
        token = session_token(ws)
        if not ctx.auth.check(token):
            await ws.close(code=4401)
            return
        # sessione revocata (logout, "Esci", cambio PIN) o scaduta: chiusura con 4401
        token_hash, revoked_event = ctx.auth.watch(token)
        q = ctx.bus.subscribe()
        recv = asyncio.ensure_future(ws.receive())
        get = asyncio.ensure_future(q.get())
        revoked = asyncio.ensure_future(revoked_event.wait())
        try:
            while True:
                done, _ = await asyncio.wait({get, recv, revoked}, timeout=WS_RECHECK_S,
                                             return_when=asyncio.FIRST_COMPLETED)
                if revoked in done or (not done and not ctx.auth.check(token)):
                    with contextlib.suppress(Exception):
                        await asyncio.wait_for(ws.close(code=4401), 2)
                    break
                if recv in done:
                    if recv.result()["type"] == "websocket.disconnect":
                        break
                    recv = asyncio.ensure_future(ws.receive())  # frame del client: ignorato
                if get in done:
                    if not await send_with_timeout(ws, get.result()):
                        # client troppo lento: si ricollega (dopo 3 s) e ricarica
                        with contextlib.suppress(Exception):
                            await asyncio.wait_for(ws.close(code=1013), 2)
                        break
                    get = asyncio.ensure_future(q.get())
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            recv.cancel()
            get.cancel()
            revoked.cancel()
            ctx.bus.unsubscribe(q)
            ctx.auth.unwatch(token_hash, revoked_event)

    api_storeforward.register(app, ctx, require_auth, require_json)
    api_prediction.register(app, ctx, require_auth, require_json)
    register_data_routes(app, ctx, require_auth)

    # ---- statici (ultimi: catch-all) ----
    if ctx.static_dir is not None and Path(ctx.static_dir).exists():
        app.mount("/", _SpaStaticFiles(directory=ctx.static_dir, html=True), name="static")
    else:
        @app.get("/", include_in_schema=False)
        async def not_built():
            return HTMLResponse(NOT_BUILT_HTML)

    return app
