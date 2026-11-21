"""Rotte di lettura dei dati dei nodi (serie, metriche, SNR, percorso), fuori dal loop."""
import asyncio
import sqlite3
import time
from typing import Callable, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Query

from . import queries

T = TypeVar("T")
STATS_TTL_S = 60


async def run_read(ctx, fn: Callable[[sqlite3.Connection], T]) -> T:
    """Con `ctx.db_path` la lettura gira in un thread su una connessione a sola lettura
    propria; senza (database in memoria dei test) gira sulla connessione principale."""
    if ctx.db_path is None:
        return fn(ctx.conn)

    def job() -> T:
        conn = queries.ro_connect(ctx.db_path)
        try:
            return fn(conn)
        finally:
            conn.close()
    return await asyncio.to_thread(job)


def register_data_routes(app: FastAPI, ctx, require_auth) -> None:
    from .api import _num_from_id

    @app.get("/api/nodes/{node_id}/positions", dependencies=[Depends(require_auth)])
    async def node_positions(node_id: str, hours: float = Query(24, gt=0, le=8784),
                             max_points: int = Query(5000, ge=2, le=20000)):
        num = _num_from_id(node_id)
        since = time.time() - hours * 3600
        return await run_read(ctx, lambda c: queries.track(c, num, since, max_points))

    @app.get("/api/nodes/{node_id}/telemetry", dependencies=[Depends(require_auth)])
    async def node_telemetry(node_id: str, hours: float = Query(168, gt=0, le=8784),
                             max_points: int = Query(800, ge=2, le=20000)):
        num = _num_from_id(node_id)
        if num not in ctx.live.nodes:
            raise HTTPException(404, "Nodo non trovato")
        since = time.time() - hours * 3600
        return await run_read(ctx, lambda c: queries.telemetry_series(c, num, since, max_points))

    @app.get("/api/nodes/{node_id}/metrics", dependencies=[Depends(require_auth)])
    async def node_metrics(node_id: str, hours: float = Query(168, gt=0, le=8784)):
        num = _num_from_id(node_id)
        since = time.time() - hours * 3600
        return await run_read(ctx, lambda c: queries.metric_series(c, num, since))

    @app.get("/api/nodes/{node_id}/snr", dependencies=[Depends(require_auth)])
    async def node_snr(node_id: str, hours: float = Query(168, gt=0, le=8784)):
        num = _num_from_id(node_id)
        since = time.time() - hours * 3600
        return await run_read(ctx, lambda c: queries.snr_series(c, num, since))

    stats_cache: dict[int, tuple[float, dict]] = {}
    stats_lock = asyncio.Lock()

    @app.get("/api/stats", dependencies=[Depends(require_auth)])
    async def stats(hours: int = Query(24, ge=1, le=2160)):
        async with stats_lock:
            now = time.time()
            hit = stats_cache.get(hours)
            if hit and now - hit[0] < STATS_TTL_S:
                return hit[1]
            result = await run_read(ctx, lambda c: queries.network_stats(c, now, hours))
            stats_cache[hours] = (now, result)
            return result

    @app.get("/api/packets", dependencies=[Depends(require_auth)])
    async def packets(node: str | None = Query(None, max_length=16),
                      kind: str | None = Query(None, max_length=32),
                      source: str | None = Query(None, pattern="^(rf|mqtt)$"),
                      status: str | None = Query(
                          None, pattern="^(ok|encrypted|unsupported|undecodable|empty)$"),
                      min_snr: float | None = None, since: float | None = None,
                      until: float | None = None, before_id: int | None = Query(None, ge=0),
                      limit: int = Query(100, ge=1)):
        num = None
        if node:
            try:
                num = _num_from_id(node)
            except HTTPException:
                raise HTTPException(422, "Nodo non valido")
        f = queries.PacketFilter(num, kind, source, status, min_snr, since, until)
        limit = min(limit, queries.PACKET_LIMIT_MAX)
        return await run_read(ctx, lambda c: queries.packet_list(c, f, limit, before_id))

    @app.get("/api/packets/{pid}", dependencies=[Depends(require_auth)])
    async def packet(pid: int):
        row = await run_read(ctx, lambda c: queries.packet_detail(c, pid))
        if row is None:
            raise HTTPException(404, "Pacchetto non trovato")
        return row
