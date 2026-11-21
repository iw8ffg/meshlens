import asyncio
import base64
import json
import threading
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pytest

from meshlens.bus import Bus
from meshlens.elevation import ElevationError, bbox_around, tiles_for_bbox
from meshlens.prediction import NODATA, PredictionError, sensitivity_dbm
from meshlens.prediction_service import PredictionManager, compare_grid

# sito all'incrocio di quattro riquadri: con 3 km di raggio ne servono 4, con 15 km sono 36
LAT, LON = 41.3768, 14.2383
PARAMS = {"lat": LAT, "lon": LON, "radius_km": 3}
TILES = tiles_for_bbox(bbox_around(LAT, LON, 3000))
BIG = tiles_for_bbox(bbox_around(LAT, LON, 15000))


class FlatDem:
    def sample(self, lats, lons):
        return np.zeros(np.shape(lats))


class FakeCache:
    """ElevationCache finto: `present` e' l'insieme dei riquadri in cache; download li aggiunge."""

    def __init__(self, present=(), error=None):
        self.present, self.error, self.downloads = set(present), error, []

    def missing(self, tiles):
        return [t for t in tiles if t not in self.present]

    def download(self, tiles, progress, cancel, workers=4):
        tiles = list(tiles)
        self.downloads.append(tiles)
        if self.error:
            raise self.error
        for i, t in enumerate(tiles, 1):
            self.present.add(t)
            progress(i, len(tiles))

    def mosaic(self, bbox):
        return FlatDem()

    def cleanup_tmp(self):
        pass


def make(tmp_path, cache=None, **kw):
    bus = Bus()
    m = PredictionManager(tmp_path, bus, cache or FakeCache(TILES),
                          executor_factory=lambda: ThreadPoolExecutor(2), **kw)
    return m, bus


def drain(q):
    out = []
    while not q.empty():
        out.append(q.get_nowait())
    return out


def test_estimate_counts(tmp_path):
    assert len(BIG) == 36
    m, _ = make(tmp_path, FakeCache(BIG[:4]))
    e = m.estimate({**PARAMS, "radius_km": 15})
    assert e["tiles_total"] == 36
    assert e["tiles_missing"] == 36 - 4
    assert e["download_bytes"] == (36 - 4) * 90000
    assert e["bbox"] == bbox_around(LAT, LON, 15000)


def test_estimate_validates(tmp_path):
    m, _ = make(tmp_path)
    with pytest.raises(PredictionError) as ei:
        m.estimate({**PARAMS, "radius_km": 99})
    assert ei.value.status == 400 and "radius_km" in str(ei.value)


async def test_start_requires_download(tmp_path):
    m, _ = make(tmp_path, FakeCache(TILES[:1]))
    with pytest.raises(PredictionError) as ei:
        await m.start(PARAMS, None, False)
    n = len(TILES) - 1
    assert ei.value.status == 409 and ei.value.code == "elevation_missing"
    assert str(ei.value) == f"Mancano {n} riquadri di altitudine: scaricali per continuare"
    assert m.job is None


async def test_job_lifecycle(tmp_path):
    cache = FakeCache(TILES[:1])
    m, bus = make(tmp_path, cache, progress_interval=0)
    q = bus.subscribe()
    job = await m.start(PARAMS, "Tetto casa", True)
    assert job["status"] == "running" and job["step"] == "Download dei dati di altitudine"
    await m._task
    msgs = [x["job"] for x in drain(q) if x["type"] == "prediction_job"]
    steps = []
    for j in msgs:
        if not steps or steps[-1] != j["step"]:
            steps.append(j["step"])
    assert steps == ["Download dei dati di altitudine", "Calcolo", "Salvataggio"]
    assert msgs[0]["total"] == len(TILES) - 1
    final = m.job
    assert final["status"] == "done" and final["result_id"] and final["ended"] is not None
    assert msgs[-1]["status"] == "done"
    assert cache.downloads == [[t for t in TILES if t not in TILES[:1]]]
    rid = final["result_id"]
    assert (tmp_path / "predictions" / f"{rid}.json").is_file()
    assert not list((tmp_path / "predictions").glob("*.tmp"))
    assert m.list()[0]["id"] == rid and "values" not in m.list()[0]
    doc = m.get(rid)
    assert doc["name"] == "Tetto casa" and doc["sensitivity_dbm"] == sensitivity_dbm("LONG_FAST")
    assert doc["eirp_dbm"] == 24.0 and doc["covered_km2"] > 0
    assert len(base64.b64decode(doc["values"])) == doc["width"] * doc["height"]
    assert doc["nodata"] == NODATA
    m.delete(rid)
    with pytest.raises(PredictionError) as ei:
        m.get(rid)
    assert ei.value.status == 404


async def test_all_cached_skips_download(tmp_path):
    m, bus = make(tmp_path)
    q = bus.subscribe()
    await m.start(PARAMS, None, False)
    await m._task
    steps = {x["job"]["step"] for x in drain(q)}
    assert steps == {"Calcolo", "Salvataggio"} and m.job["status"] == "done"
    assert m.get(m.job["result_id"])["name"] == "Previsione"


async def test_single_job(tmp_path):
    m, _ = make(tmp_path)
    await m.start(PARAMS, None, False)
    with pytest.raises(PredictionError) as ei:
        await m.start(PARAMS, None, False)
    assert ei.value.status == 409 and str(ei.value) == "C'è già un calcolo in corso"
    await m._task
    await m.start(PARAMS, None, False)  # finito il primo, se ne puo' avviare un altro
    await m._task


async def test_download_failure_keeps_cache(tmp_path):
    cache = FakeCache(TILES[:1], error=ElevationError(
        "Download dei dati di altitudine non riuscito: HTTP 403"))
    m, _ = make(tmp_path, cache)
    await m.start(PARAMS, None, True)
    await m._task
    assert m.job["status"] == "failed"
    assert m.job["error"] == "Download dei dati di altitudine non riuscito: HTTP 403"
    assert cache.present == set(TILES[:1])
    assert list((tmp_path / "predictions").iterdir()) == []


async def test_cancel(tmp_path):
    started, release = threading.Event(), threading.Event()

    class Slow(FakeCache):
        def mosaic(self, bbox):
            started.set()
            release.wait(5)
            return FlatDem()

    m, _ = make(tmp_path, Slow(TILES))
    job = await m.start(PARAMS, None, False)
    await asyncio.to_thread(started.wait, 5)
    t = asyncio.create_task(m.cancel(job["id"]))
    await asyncio.sleep(0.05)
    release.set()
    res = await t
    assert res["status"] == "cancelled" and res["result_id"] is None
    assert list((tmp_path / "predictions").iterdir()) == []
    with pytest.raises(PredictionError) as ei:
        await m.cancel("zzz")
    assert ei.value.status == 404


async def test_shutdown_cancels_and_blocks_new(tmp_path):
    m, _ = make(tmp_path)
    await m.start(PARAMS, None, False)
    await m.shutdown()
    assert m.job["status"] in ("cancelled", "done")
    with pytest.raises(PredictionError):
        await m.start(PARAMS, None, False)


def test_unsafe_ids_are_404(tmp_path):
    m, _ = make(tmp_path)
    (tmp_path / "secret.json").write_text("{}")
    for bad in ("../secret", "..\\secret", "x"):
        with pytest.raises(PredictionError):
            m.get(bad)
        with pytest.raises(PredictionError):
            m.delete(bad)


def test_cleanup_tmp(tmp_path):
    m, _ = make(tmp_path)
    (tmp_path / "predictions" / "p1-abcdef.json.tmp").write_text("x")
    m.cleanup_tmp()
    assert list((tmp_path / "predictions").iterdir()) == []


def _meta():
    return {"bbox": [10.0, 40.0, 11.0, 41.0], "width": 10, "height": 10,
            "sensitivity_dbm": -131.5}


def _grid():
    g = np.full((10, 10), -5, dtype=np.int8)
    g[:, :5] = 5
    return g


def test_compare_grid():
    pts = [{"lat": 40.5, "lon": 10.2, "rssi": -120}, {"lat": 40.6, "lon": 10.3, "rssi": -120},
           {"lat": 40.5, "lon": 10.8, "rssi": None}]
    r = compare_grid(_meta(), _grid(), pts, [{"lat": 40.5, "lon": 10.9}])
    assert (r["received"], r["missing"]) == (3, 1)
    assert (r["received_covered"], r["received_uncovered"]) == (2, 1)
    assert (r["missing_covered"], r["missing_uncovered"], r["outside"]) == (0, 1, 0)
    assert r["agreement_pct"] == 75.0
    assert r["rssi_bias_db"] == -6.5 and r["rssi_rmse_db"] == 6.5
    assert r["points"][0] == {"lat": 40.5, "lon": 10.2, "received": True,
                              "measured_rssi": -120, "predicted_rssi": -126.5}
    assert r["points"][3]["received"] is False and r["points"][3]["predicted_rssi"] == -136.5


def test_compare_grid_outside_and_empty():
    g = _grid()
    g[0, 0] = NODATA
    pts = [{"lat": 45.0, "lon": 10.2, "rssi": -100},     # fuori dal bbox
           {"lat": 40.999, "lon": 10.01, "rssi": -100},  # cella senza dato
           {"lat": None, "lon": None, "rssi": -100}]     # senza posizione
    r = compare_grid(_meta(), g, pts, [])
    assert r["outside"] == 3 and r["points"] == []
    assert r["agreement_pct"] is None and r["rssi_bias_db"] is None and r["rssi_rmse_db"] is None


def test_compare_manager_roundtrip(tmp_path):
    m, _ = make(tmp_path)
    doc = {**_meta(), "id": "p1-abcdef", "values": base64.b64encode(_grid().tobytes()).decode()}
    (tmp_path / "predictions" / "p1-abcdef.json").write_text(json.dumps(doc))
    r = m.compare("p1-abcdef", [{"lat": 40.5, "lon": 10.2, "rssi": -120}], [])
    assert r["received_covered"] == 1 and r["rssi_bias_db"] == -6.5


def test_list_uses_sidecar_and_rebuilds(tmp_path):
    m, _ = make(tmp_path)
    d = tmp_path / "predictions"
    doc = {**_meta(), "id": "p1-abcdef", "created": 1.0, "name": "A", "nodata": -128,
           "values": base64.b64encode(_grid().tobytes()).decode()}
    (d / "p1-abcdef.json").write_text(json.dumps(doc))
    first = m.list()  # senza sidecar: ricostruito
    assert first[0]["id"] == "p1-abcdef" and "values" not in first[0]
    assert (d / "p1-abcdef.meta.json").is_file()
    (d / "p1-abcdef.json").write_text("{ rotto")  # ora l'elenco legge solo il sidecar
    assert m.list()[0]["name"] == "A"
    (d / "p1-abcdef.json").write_text(json.dumps(doc))
    m.delete("p1-abcdef")
    assert list(d.iterdir()) == [] and m.list() == []
