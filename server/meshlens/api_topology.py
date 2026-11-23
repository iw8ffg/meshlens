"""Rotte di WP3 (mappa e topologia): contatti ATAK e grafo della rete.

Prefissi riservati (contratto §5.3):
    /api/topology, /api/tak
Le rotte leggono direttamente il database (letture in thread con run_read): non dipendono da
ctx.ext["tak"] e funzionano anche senza l'estensione installata.
"""
import time

from fastapi import Depends, HTTPException, Query

from .api_data import run_read
from .tak import _COLS, contact_dict

# percorsi GET (esattamente come registrati) leggibili dall'ospite: solo mappa, nodi, statistiche
GUEST_GET_PATHS: tuple[str, ...] = ("/api/tak/contacts", "/api/tak/summary", "/api/topology")

MSG_HOURS = "Periodo non valido: da 1 a 720 ore"
TAK_LIMIT = 500


def _parse_hours(value: str, default: int = 24) -> int:
    """Ore intere da 1 a 720; 400 con messaggio italiano altrimenti."""
    if value is None or value == "":
        return default
    try:
        h = int(value)
    except (TypeError, ValueError):
        raise HTTPException(400, MSG_HOURS) from None
    if not 1 <= h <= 720:
        raise HTTPException(400, MSG_HOURS)
    return h


_VISIBLE = "LEFT JOIN nodes n ON n.num = c.node_num WHERE c.time >= ? AND COALESCE(n.is_ignored, 0) = 0"


def tak_contacts_query(conn, since: float) -> list[dict]:
    cols = ", ".join(f"c.{c.strip()}" for c in _COLS.split(","))
    rows = conn.execute(
        f"SELECT {cols} FROM tak_contacts c {_VISIBLE} ORDER BY c.time DESC LIMIT ?",
        (since, TAK_LIMIT)).fetchall()
    return [contact_dict(r) for r in rows]


def tak_summary_query(conn, since: float) -> dict:
    row = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(c.compressed = 1 AND c.callsign IS NULL), 0) "
        f"FROM tak_contacts c {_VISIBLE}", (since,)).fetchone()
    try:
        # packets.portnum e' il nome dell'enum (TEXT): ATAK_PLUGIN_V2 = 78
        v2 = conn.execute("SELECT COUNT(*) FROM packets WHERE portnum IN ('ATAK_PLUGIN_V2', '78') "
                          "AND time >= ?", (since,)).fetchone()[0]
    except Exception:
        v2 = 0
    return {"contacts": int(row[0]), "compressed": int(row[1]), "unsupported_v2": int(v2)}


def register(app, ctx, require_auth, require_json) -> None:
    """Registra le rotte del modulo (chiamata in coda a create_app, prima dei file statici)."""

    @app.get("/api/tak/contacts", dependencies=[Depends(require_auth)])
    async def tak_contacts(hours: str = Query("24")):
        since = time.time() - _parse_hours(hours) * 3600
        return await run_read(ctx, lambda c: tak_contacts_query(c, since))

    @app.get("/api/tak/summary", dependencies=[Depends(require_auth)])
    async def tak_summary(hours: str = Query("24")):
        since = time.time() - _parse_hours(hours) * 3600
        return await run_read(ctx, lambda c: tak_summary_query(c, since))
