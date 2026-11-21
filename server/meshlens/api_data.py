"""Rotte di lettura dei dati dei nodi (serie, metriche, SNR, percorso), fuori dal loop."""
import asyncio
import sqlite3
import time
from typing import Callable, TypeVar

from fastapi import Depends, FastAPI, HTTPException, Query

from . import queries

T = TypeVar("T")


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
