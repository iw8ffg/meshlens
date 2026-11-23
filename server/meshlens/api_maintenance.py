"""Rotte di WP5b (manutenzione): note di versione («Novità»), anteprima della conservazione
per broker, diagnosi del collegamento radio. Registrate da api_automation.register."""
import time

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

from . import release_notes
from .api_data import run_read
from .radio_diag import DiagBusy, RadioDiagnoser
from .settings import load_settings, save_settings

RADIO_NOT_FOUND_MSG = "Radio non trovata"
RADIOS_UNAVAILABLE_MSG = "Radio non disponibili"
DAY_S = 86400

# percorsi GET leggibili dall'ospite: nessuno
GUEST_GET_PATHS: tuple[str, ...] = ()


def _current_version() -> str:
    from . import __version__  # letto a ogni chiamata (i test lo sostituiscono)
    return __version__


def retention_preview(conn, settings: dict, now: float) -> dict:
    """Quanti messaggi per broker la prossima pulizia eliminerebbe in piu' rispetto alla
    regola generale (vale il minore tra i giorni del broker e quelli generali). Sola lettura."""
    general = int(settings.get("retention_messages_days") or 90)
    per_broker = settings.get("retention_broker_days") or {}
    brokers = []
    for b in settings.get("mqtt_brokers") or []:
        bid = b["id"]
        row = conn.execute("SELECT COUNT(*), MIN(time) FROM messages "
                           "WHERE source='mqtt' AND broker=?", (bid,)).fetchone()
        days = per_broker.get(bid)
        would = 0
        if days is not None and days < general:
            would = conn.execute(
                "SELECT COUNT(*) FROM messages WHERE source='mqtt' AND broker=? "
                "AND time < ? AND time >= ?",
                (bid, now - days * DAY_S, now - general * DAY_S)).fetchone()[0]
        brokers.append({"id": bid, "name": b.get("name") or bid, "messages": row[0],
                        "oldest": row[1], "days": days, "would_delete": would})
    tr_days = int(settings.get("retention_traceroutes_days") or 365)
    tr_rows = conn.execute("SELECT COUNT(*) FROM traceroutes").fetchone()[0]
    tr_old = conn.execute("SELECT COUNT(*) FROM traceroutes WHERE time < ?",
                          (now - tr_days * DAY_S,)).fetchone()[0]
    return {"brokers": brokers, "messages_days": general,
            "traceroutes": {"rows": tr_rows, "would_delete": tr_old, "days": tr_days}}


class DiagnoseBody(BaseModel):
    kind: str = Field(max_length=8)
    address: str = Field(max_length=300)


def register(app, ctx, require_auth, require_json) -> None:
    auth = [Depends(require_auth)]
    write = [Depends(require_auth), Depends(require_json)]

    # ---- «Novità» ----------------------------------------------------------------------
    @app.get("/api/update/notes", dependencies=auth)
    async def update_notes(force: int = Query(0, ge=0, le=1)):
        s = load_settings(ctx.conn)
        return release_notes.payload(_current_version(), s.get("last_seen_version") or "",
                                     s.get("onboarding_done") is True,
                                     release_notes.load_releases(), force=bool(force))

    @app.post("/api/update/seen", dependencies=write)
    async def update_seen():
        version = _current_version()  # mai il corpo: conta solo la versione in esecuzione
        try:
            saved = save_settings(ctx.conn, {"last_seen_version": version})
        except ValueError as e:
            raise HTTPException(400, str(e))
        await ctx.on_settings_changed(saved)
        return {"last_seen_version": version}

    # ---- conservazione -----------------------------------------------------------------
    @app.get("/api/retention", dependencies=auth)
    async def retention():
        settings = load_settings(ctx.conn)
        now = time.time()
        return await run_read(ctx, lambda conn: retention_preview(conn, settings, now))

    # ---- diagnosi radio ----------------------------------------------------------------
    def diagnoser() -> RadioDiagnoser:
        d = ctx.ext.get("radio_diag")
        if d is None:
            if ctx.radios is None:
                raise HTTPException(503, RADIOS_UNAVAILABLE_MSG)
            d = ctx.ext["radio_diag"] = RadioDiagnoser(ctx.radios)
        return d

    async def run_diag(**kw):
        try:
            return await diagnoser().diagnose(**kw)
        except DiagBusy as e:
            raise HTTPException(409, str(e))
        except KeyError:
            raise HTTPException(404, RADIO_NOT_FOUND_MSG)
        except ValueError as e:
            raise HTTPException(400, str(e))

    @app.post("/api/radios/diagnose", dependencies=write)
    async def diagnose_address(body: DiagnoseBody):
        return await run_diag(kind=body.kind, address=body.address)

    @app.post("/api/radios/{radio_id}/diagnose", dependencies=write)
    async def diagnose_radio(radio_id: str):
        return await run_diag(radio_id=radio_id)
