"""Servizio della copertura prevista: un lavoro alla volta, risultati su file, confronto con le prove.

I risultati stanno in `data_dir/predictions/<id>.json` (meta + `values` in base64), senza
tabelle nel database. Il lavoro gira in thread (`asyncio.to_thread`); i radiali, in processi
separati scelti da `executor_factory`.
"""
from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import math
import os
import re
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

import numpy as np

from .elevation import (TILE_BYTES_ESTIMATE, ElevationCache, ElevationError, bbox_around,
                        tiles_for_bbox)
from .prediction import (_EARTH_R, N_RADIALS, NODATA, PredictionError, SiteParams,
                         default_executor, predict, sensitivity_dbm)

STEP_DOWNLOAD = "Download dei dati di altitudine"
STEP_COMPUTE = "Calcolo"
STEP_SAVE = "Salvataggio"
MSG_BUSY = "C'è già un calcolo in corso"
MSG_CANCELLED = "Calcolo annullato"
MSG_JOB_NOT_FOUND = "Lavoro non trovato"
MSG_NOT_FOUND = "Previsione non trovata"
MSG_SHUTTING_DOWN = "Server in chiusura"
DEFAULT_NAME = "Previsione"
_ID_RE = re.compile(r"p\d+-[0-9a-f]{6}")


def _merc_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def compare_grid(meta: dict, values: np.ndarray, points: list[dict], missing: list[dict]) -> dict:
    """Confronta la griglia prevista con i punti ricevuti e mancanti di una prova.

    Un punto senza posizione, fuori dal bbox o su una cella senza dato conta in `outside`.
    "Coperto" significa margine >= 0; `predicted_rssi` = margine + sensibilita'.
    """
    w, s, e, n = meta["bbox"]
    width, height = meta["width"], meta["height"]
    sens = meta["sensitivity_dbm"]
    my0, my1 = _merc_y(n), _merc_y(s)
    grid = np.asarray(values).reshape(height, width)

    def margin_at(p: dict) -> int | None:
        lat, lon = p.get("lat"), p.get("lon")
        if lat is None or lon is None or not (-85.0 < lat < 85.0):
            return None
        fx = (lon - w) / (e - w)
        fy = (my0 - _merc_y(lat)) / (my0 - my1)
        if not (0.0 <= fx <= 1.0 and 0.0 <= fy <= 1.0):
            return None
        v = int(grid[min(int(fy * height), height - 1), min(int(fx * width), width - 1)])
        return None if v == NODATA else v

    out = {"received": len(points), "missing": len(missing), "received_covered": 0,
           "received_uncovered": 0, "missing_covered": 0, "missing_uncovered": 0, "outside": 0}
    pts: list[dict] = []
    diffs: list[float] = []
    for p, received in [(p, True) for p in points] + [(p, False) for p in missing]:
        m = margin_at(p)
        if m is None:
            out["outside"] += 1
            continue
        covered = m >= 0
        out[("received" if received else "missing") + ("_covered" if covered else "_uncovered")] += 1
        predicted = round(m + sens, 1)
        measured = p.get("rssi") if received else None
        pts.append({"lat": p["lat"], "lon": p["lon"], "received": received,
                    "measured_rssi": measured, "predicted_rssi": predicted})
        if received and measured is not None:
            diffs.append(predicted - measured)
    den = out["received"] + out["missing"] - out["outside"]
    out["agreement_pct"] = (round(100.0 * (out["received_covered"] + out["missing_uncovered"]) / den, 1)
                            if den > 0 else None)
    out["rssi_bias_db"] = round(sum(diffs) / len(diffs), 1) if diffs else None
    out["rssi_rmse_db"] = (round(math.sqrt(sum(d * d for d in diffs) / len(diffs)), 1)
                           if diffs else None)
    out["points"] = pts
    return out


class PredictionManager:
    def __init__(self, data_dir, bus, cache: ElevationCache, executor_factory=default_executor,
                 clock=time.time, progress_interval: float = 0.5):
        self.dir = Path(data_dir) / "predictions"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.bus, self.cache = bus, cache
        self.executor_factory, self.clock = executor_factory, clock
        self.progress_interval = progress_interval
        self.job: dict | None = None
        self._task: asyncio.Task | None = None
        self._cancel = threading.Event()
        self._closing = False
        self._last_pub = 0.0

    # ---- stima ----
    def _tiles(self, sp: SiteParams) -> list[tuple]:
        return tiles_for_bbox(bbox_around(sp.lat, sp.lon, sp.radius_km * 1000.0))

    def estimate(self, params: dict) -> dict:
        sp = SiteParams.from_dict(params)
        tiles = self._tiles(sp)
        missing = self.cache.missing(tiles)
        return {"tiles_total": len(tiles), "tiles_missing": len(missing),
                "download_bytes": len(missing) * TILE_BYTES_ESTIMATE,
                "bbox": bbox_around(sp.lat, sp.lon, sp.radius_km * 1000.0)}

    # ---- lavoro ----
    def _running(self) -> bool:
        return self.job is not None and self.job["status"] == "running"

    def _publish(self) -> None:
        if self.job:
            self._last_pub = time.monotonic()
            self.bus.publish({"type": "prediction_job", "job": dict(self.job)})

    def _set(self, **kw) -> None:
        self.job.update(kw)
        self._publish()

    def _progress(self, done: int, total: int) -> None:
        """Nel ciclo eventi: aggiorna sempre, pubblica al massimo ogni `progress_interval`."""
        if not self._running():
            return
        self.job.update(done=done, total=total)
        if done >= total or time.monotonic() - self._last_pub >= self.progress_interval:
            self._publish()

    async def start(self, params: dict, name: str | None, download: bool) -> dict:
        # nessun await prima di `self.job = ...`: il posto e' preso nello stesso passo del controllo
        if self._closing:
            raise PredictionError(409, MSG_SHUTTING_DOWN)
        if self._running():
            raise PredictionError(409, MSG_BUSY)
        sp = SiteParams.from_dict(params)
        missing = self.cache.missing(self._tiles(sp))
        if missing and not download:
            raise PredictionError(
                409, f"Mancano {len(missing)} riquadri di altitudine: scaricali per continuare",
                "elevation_missing")
        self._cancel = threading.Event()
        self.job = {"id": uuid.uuid4().hex[:12], "status": "running",
                    "step": STEP_DOWNLOAD if missing else STEP_COMPUTE,
                    "done": 0, "total": len(missing) if missing else N_RADIALS,
                    "error": None, "result_id": None, "started": self.clock(), "ended": None}
        self._task = asyncio.create_task(self._run(sp, (name or "").strip() or DEFAULT_NAME,
                                                   missing, self._cancel))
        self._publish()
        return dict(self.job)

    async def _run(self, sp: SiteParams, name: str, missing: list, cancel: threading.Event) -> None:
        loop = asyncio.get_running_loop()

        def progress(done: int, total: int) -> None:  # chiamata dai thread
            loop.call_soon_threadsafe(self._progress, done, total)

        try:
            if missing:
                await asyncio.to_thread(self.cache.download, missing, progress, cancel)
                if cancel.is_set():
                    raise PredictionError(409, MSG_CANCELLED)
            self._set(step=STEP_COMPUTE, done=0, total=N_RADIALS)

            def compute():
                dem = self.cache.mosaic(bbox_around(sp.lat, sp.lon, sp.radius_km * 1000.0))
                return predict(sp, dem, self.executor_factory, progress, cancel)

            grid = await asyncio.to_thread(compute)
            if cancel.is_set():
                raise PredictionError(409, MSG_CANCELLED)
            self._set(step=STEP_SAVE)
            pid = await asyncio.to_thread(self._save, sp, name, grid)
            self._set(status="done", result_id=pid, ended=self.clock())
        except PredictionError as e:
            if cancel.is_set():
                self._set(status="cancelled", ended=self.clock())
            else:
                self._set(status="failed", error=str(e), ended=self.clock())
        except ElevationError as e:
            self._set(status="failed", error=str(e), ended=self.clock())
        except Exception as e:  # noqa: BLE001
            self._set(status="failed", error=f"Errore imprevisto: {e}", ended=self.clock())

    def _save(self, sp: SiteParams, name: str, grid) -> str:
        pid = f"p{int(self.clock())}-{uuid.uuid4().hex[:6]}"
        w, _s, e, _n = grid.bbox
        cell_m = math.radians((e - w) / grid.width) * _EARTH_R * math.cos(math.radians(sp.lat))
        covered = int(np.count_nonzero((grid.values != NODATA) & (grid.values >= 0)))
        meta = {"id": pid, "name": name, "created": self.clock(), "params": asdict(sp),
                "sensitivity_dbm": sensitivity_dbm(sp.preset), "eirp_dbm": sp.eirp_dbm,
                "bbox": grid.bbox, "width": grid.width, "height": grid.height,
                "covered_km2": round(covered * cell_m * cell_m / 1e6, 1)}
        doc = {**meta, "values": base64.b64encode(grid.values.astype(np.int8).tobytes()).decode("ascii"),
               "nodata": NODATA}
        path = self.dir / f"{pid}.json"
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(json.dumps(doc), encoding="utf-8")
            os.replace(tmp, path)
        finally:
            with contextlib.suppress(OSError):
                tmp.unlink()
        return pid

    async def _stop_running(self) -> None:
        if self._running() and self._task is not None:
            self._cancel.set()
            await asyncio.wait({self._task})

    async def cancel(self, job_id: str) -> dict:
        if not self.job or self.job["id"] != job_id:
            raise PredictionError(404, MSG_JOB_NOT_FOUND)
        await self._stop_running()
        return dict(self.job)

    async def shutdown(self) -> None:
        """Chiusura: annulla e attende il thread di calcolo (e con lui l'esecutore dei processi)."""
        self._closing = True
        await self._stop_running()
        self.cleanup_tmp()

    # ---- risultati ----
    def _read(self, pid: str) -> dict:
        if not _ID_RE.fullmatch(pid):
            raise PredictionError(404, MSG_NOT_FOUND)
        try:
            return json.loads((self.dir / f"{pid}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            raise PredictionError(404, MSG_NOT_FOUND) from e

    def list(self) -> list[dict]:
        out = []
        for p in self.dir.glob("p*.json"):
            try:
                doc = json.loads(p.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            doc.pop("values", None)
            doc.pop("nodata", None)
            out.append(doc)
        out.sort(key=lambda m: (m.get("created", 0), m.get("id", "")), reverse=True)
        return out

    def get(self, pid: str) -> dict:
        return self._read(pid)

    def delete(self, pid: str) -> None:
        if not _ID_RE.fullmatch(pid):
            raise PredictionError(404, MSG_NOT_FOUND)
        try:
            (self.dir / f"{pid}.json").unlink()
        except FileNotFoundError as e:
            raise PredictionError(404, MSG_NOT_FOUND) from e

    def compare(self, pid: str, points: list[dict], missing: list[dict]) -> dict:
        doc = self._read(pid)
        values = np.frombuffer(base64.b64decode(doc["values"]), dtype=np.int8)
        return compare_grid(doc, values, points, missing)

    def cleanup_tmp(self) -> None:
        for p in self.dir.glob("*.tmp"):
            with contextlib.suppress(OSError):
                p.unlink()
        with contextlib.suppress(OSError):
            self.cache.cleanup_tmp()
