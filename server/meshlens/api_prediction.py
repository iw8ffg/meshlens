"""Rotte della copertura prevista: stima, lavoro di calcolo, risultati e confronto con le prove."""
import asyncio

from fastapi import Body, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from .coverage import missing_points
from .elevation import ElevationError
from .prediction import PredictionError

MSG_UNAVAILABLE = "Previsione di copertura non disponibile"
MSG_NO_SESSION = "Sessione non trovata"


class JobBody(BaseModel):
    params: dict
    name: str | None = Field(None, max_length=80)
    download: bool = False


def register(app, ctx, require_auth, require_json) -> None:
    def service():
        if ctx.prediction is None:
            raise HTTPException(503, MSG_UNAVAILABLE)
        return ctx.prediction

    def error_response(e: Exception) -> JSONResponse:
        if isinstance(e, PredictionError):
            return JSONResponse({"detail": str(e), "code": e.code}, status_code=e.status)
        return JSONResponse({"detail": str(e), "code": "elevation_error"}, status_code=502)

    @app.post("/api/prediction/estimate", dependencies=[Depends(require_auth), Depends(require_json)])
    async def prediction_estimate(params: dict = Body(...)):
        try:
            return await asyncio.to_thread(service().estimate, params)
        except (PredictionError, ElevationError) as e:
            return error_response(e)

    @app.post("/api/prediction/jobs", status_code=202,
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def prediction_start(body: JobBody):
        try:
            return await service().start(body.params, body.name, body.download)
        except (PredictionError, ElevationError) as e:
            return error_response(e)

    @app.post("/api/prediction/jobs/{job_id}/cancel",
              dependencies=[Depends(require_auth), Depends(require_json)])
    async def prediction_cancel(job_id: str):
        try:
            return await service().cancel(job_id)
        except PredictionError as e:
            return error_response(e)

    @app.get("/api/predictions", dependencies=[Depends(require_auth)])
    async def predictions_list():
        return await asyncio.to_thread(service().list)

    @app.get("/api/predictions/{pid}", dependencies=[Depends(require_auth)])
    async def predictions_get(pid: str):
        try:
            return await asyncio.to_thread(service().get, pid)
        except PredictionError as e:
            return error_response(e)

    @app.delete("/api/predictions/{pid}", status_code=204,
                dependencies=[Depends(require_auth), Depends(require_json)])
    async def predictions_delete(pid: str):
        try:
            service().delete(pid)
        except PredictionError as e:
            return error_response(e)
        return Response(status_code=204)

    @app.get("/api/predictions/{pid}/compare", dependencies=[Depends(require_auth)])
    async def predictions_compare(pid: str, session_id: int):
        s = ctx.store.get_session(session_id)
        if s is None:
            raise HTTPException(404, MSG_NO_SESSION)
        points = ctx.store.points(session_id)
        missing = (missing_points(points, s["interval_s"], ctx.store.track(session_id))
                   if s["mode"] == "rangetest" else [])
        try:
            return await asyncio.to_thread(service().compare, pid, points, missing)
        except PredictionError as e:
            return error_response(e)
