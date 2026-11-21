import ast
import math
import threading
import warnings
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import pytest

from meshlens import prediction as pr
from meshlens.elevation import TILE_SIZE, Dem, _tile_xy
from meshlens.prediction import (N_RADIALS, PredictionError, SiteParams, predict, rasterize,
                                 sensitivity_dbm)

LAT, LON = 40.85, 14.27
M_PER_DEG = 111_320.0


class FakeDem:
    """Dem finto: quota calcolata da una funzione (lats, lons) -> array."""

    def __init__(self, fn):
        self.fn = fn

    def sample(self, lats, lons):
        return self.fn(np.asarray(lats, dtype=np.float64), np.asarray(lons, dtype=np.float64))


def _params(**kw) -> SiteParams:
    d = {"lat": LAT, "lon": LON, "radius_km": 5}
    d.update(kw)
    return SiteParams.from_dict(d)


def _run(params, dem, progress=None, cancel=None):
    return predict(params, dem, lambda: ThreadPoolExecutor(2),
                   progress or (lambda done, total: None), cancel or threading.Event())


def _cell_geometry(grid):
    """Distanza (m) e azimut (gradi) dal sito per ogni cella, righe da nord a sud."""
    w, s, e, n = grid.bbox

    def merc(lat):
        return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))

    xs = w + (np.arange(grid.width) + 0.5) * (e - w) / grid.width
    my = merc(n) + (np.arange(grid.height) + 0.5) * (merc(s) - merc(n)) / grid.height
    lats = np.degrees(2 * np.arctan(np.exp(my)) - math.pi / 2)
    lon, lat = np.meshgrid(xs, lats)
    dx = (lon - LON) * M_PER_DEG * math.cos(math.radians(LAT))
    dy = (lat - LAT) * M_PER_DEG
    return np.hypot(dx, dy), np.degrees(np.arctan2(dx, dy)) % 360


def _sector_mean(grid, d, az, r0, r1, az0, az1):
    sel = (d >= r0) & (d <= r1) & (az >= az0) & (az <= az1)
    vals = grid.values[sel].astype(float)
    assert vals.size > 0 and (vals > -128).all()
    return vals.mean()


def test_sensitivity():
    assert sensitivity_dbm("LONG_FAST") == -131.5
    # il brief indica -117.0, ma la formula con SF7/500 kHz da' -174 + 56,99 + 6 - 7,5 = -118,5
    assert sensitivity_dbm("SHORT_TURBO") == -118.5
    assert sensitivity_dbm("LONG_SLOW") == -137.0
    assert pr.PRESETS["LONG_MODERATE"] == (11, 125)
    assert pr.EU868_MAX_EIRP_DBM == 29.15


def test_params_validation():
    with pytest.raises(PredictionError) as ei:
        _params(radius_km=80)
    assert ei.value.status == 400
    assert "radius_km" in str(ei.value)
    with pytest.raises(PredictionError) as ei:
        _params(preset="BOH")
    assert ei.value.status == 400 and "preset" in str(ei.value)
    with pytest.raises(PredictionError) as ei:
        _params(lat="abc")
    assert ei.value.status == 400 and "lat" in str(ei.value)
    p = _params()
    assert p.eirp_dbm == 24
    assert p.frequency_mhz == 869.525 and p.preset == "LONG_FAST"


def test_step():
    assert pr.step_m(1000) == 30
    assert pr.step_m(15_000) == 75
    assert pr.step_m(50_000) == 250


def test_rasterize_uniform():
    radius = 5000.0
    step = pr.step_m(radius)
    n = math.ceil(radius / step) + 1
    radials = np.full((N_RADIALS, n), -100.0)
    radials[:, 0] = np.nan
    g = rasterize(LAT, LON, radials, step, radius, -131.5)
    assert g.width == g.height <= 400
    assert g.values.dtype == np.int8 and g.values.shape == (g.height, g.width)
    d, _ = _cell_geometry(g)
    inside = d < radius - 2 * (2 * radius / g.width)
    assert inside.sum() > 0
    assert (g.values[inside] == 32).all()
    for r, c in [(0, 0), (0, -1), (-1, 0), (-1, -1)]:
        assert g.values[r, c] == -128


def test_flat_terrain_decreasing():
    g = _run(_params(), FakeDem(lambda la, lo: np.full_like(la, 100.0)))
    d, az = _cell_geometry(g)
    near = _sector_mean(g, d, az, 1000, 2000, 0, 360)
    far = _sector_mean(g, d, az, 4000, 4800, 0, 360)
    assert near > far
    north = np.concatenate([g.values[(d >= 2000) & (d <= 3000) & ((az <= 20) | (az >= 340))]])
    east = g.values[(d >= 2000) & (d <= 3000) & (az >= 70) & (az <= 110)]
    assert abs(north.astype(float).mean() - east.astype(float).mean()) <= 1


def test_ridge_shadow():
    lon_ridge = LON + 3000 / (M_PER_DEG * math.cos(math.radians(LAT)))
    band = 150 / (M_PER_DEG * math.cos(math.radians(LAT)))

    def fn(la, lo):
        h = np.full_like(la, 100.0)
        h[np.abs(lo - lon_ridge) <= band] = 600.0
        return h

    g = _run(_params(), FakeDem(fn))
    d, az = _cell_geometry(g)
    east = _sector_mean(g, d, az, 4000, 4800, 70, 110)
    west = _sector_mean(g, d, az, 4000, 4800, 250, 290)
    assert east <= west - 10


def test_sea_clamp():
    # Dem vero: mare profondo a ovest del sito, costa a 300 m a est.
    z = 12
    tx, ty = _tile_xy(LAT, LON, z)
    arr = np.full((3 * TILE_SIZE, 3 * TILE_SIZE), -800.0, dtype=np.float32)
    dem = Dem(arr, z, tx - 1, ty - 1)
    gx = (LON + 180.0) / 360.0 * (2 ** z) * TILE_SIZE - (tx - 1) * TILE_SIZE
    arr[:, int(gx) + 12:] = 40.0  # ~12 pixel di 29 m a est
    g = _run(_params(radius_km=2), dem)
    d, _ = _cell_geometry(g)
    inside = d < 2000 - 2 * (4000 / g.width)
    assert (g.values[inside] > -128).all()


def test_rasterize_nan_is_nodata():
    radius = 2000.0
    step = pr.step_m(radius)
    n = math.ceil(radius / step) + 1
    radials = np.full((N_RADIALS, n), -100.0)
    radials[:, 0] = np.nan
    radials[:, 10:] = np.nan
    g = rasterize(LAT, LON, radials, step, radius, -131.5)
    d, _ = _cell_geometry(g)
    assert (g.values[d > 12 * step] == -128).all()
    assert (g.values[d < 5 * step] == 32).all()


def test_cancel():
    cancel = threading.Event()
    calls = []

    def progress(done, total):
        calls.append((done, total))
        cancel.set()

    with pytest.raises(PredictionError) as ei:
        _run(_params(radius_km=1), FakeDem(lambda la, lo: np.full_like(la, 50.0)),
             progress, cancel)
    assert ei.value.status == 409
    assert calls and calls[0][1] == N_RADIALS and calls[-1][0] < N_RADIALS


def test_compute_radial_fallback_free_space(monkeypatch):
    def boom(*a, **k):
        raise pr.ItmError(1000)

    monkeypatch.setattr(pr, "itm_p2p_loss", boom)
    out = pr.compute_radial(([100.0] * 5, 100.0, (24.0, 2.0, 10.0, 1.5, 869.525)))
    assert math.isnan(out[0])
    fs = 32.45 + 20 * math.log10(0.2) + 20 * math.log10(869.525)
    assert out[2] == pytest.approx(24.0 - fs + 2.0)


def test_launcher_freeze_support():
    src = Path(__file__).resolve().parents[2] / "packaging" / "launcher.py"
    with warnings.catch_warnings():  # docstring preesistente con "\M"
        warnings.simplefilter("ignore", SyntaxWarning)
        tree = ast.parse(src.read_text(encoding="utf-8"))
    blocks = [n for n in tree.body if isinstance(n, ast.If)
              and isinstance(n.test, ast.Compare)
              and isinstance(n.test.left, ast.Name) and n.test.left.id == "__name__"]
    assert len(blocks) == 1
    first = blocks[0].body[0]
    assert isinstance(first, ast.Expr) and isinstance(first.value, ast.Call)
    fn = first.value.func
    assert isinstance(fn, ast.Attribute) and fn.attr == "freeze_support"
    assert isinstance(fn.value, ast.Name) and fn.value.id == "multiprocessing"
