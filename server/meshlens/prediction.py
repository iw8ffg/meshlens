"""Copertura prevista: ITM punto-punto su radiali dal sito, raster Mercatore del margine.

I profili si campionano nel processo principale; i radiali si calcolano in processi
separati (`compute_radial` e' una funzione di modulo, serializzabile).
"""
from __future__ import annotations

import math
import os
import threading
from collections.abc import Callable
from concurrent.futures import Executor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass, fields

import numpy as np

from .elevation import Dem, bbox_around
from .itm import ItmError, itm_p2p_loss  # noqa: F401  (ItmError: parte dell'interfaccia)

PRESETS: dict[str, tuple[int, float]] = {
    "SHORT_TURBO": (7, 500),
    "SHORT_FAST": (7, 250),
    "SHORT_SLOW": (8, 250),
    "MEDIUM_FAST": (9, 250),
    "MEDIUM_SLOW": (10, 250),
    "LONG_FAST": (11, 250),
    "LONG_MODERATE": (11, 125),
    "LONG_SLOW": (12, 125),
}
SNR_LIMIT = {7: -7.5, 8: -10, 9: -12.5, 10: -15, 11: -17.5, 12: -20}
EU868_MAX_EIRP_DBM = 29.15
N_RADIALS = 360
MAX_SIDE = 400
NODATA = -128
_BLOCK = 8
_EARTH_R = 6_371_000.0


def sensitivity_dbm(preset: str) -> float:
    sf, bw_khz = PRESETS[preset]
    return round(-174 + 10 * math.log10(bw_khz * 1000) + 6 + SNR_LIMIT[sf], 1)


class PredictionError(Exception):
    def __init__(self, status: int, message: str, code: str | None = None):
        super().__init__(message)
        self.status = status
        self.code = code


_LIMITS: dict[str, tuple[float, float]] = {
    "lat": (-85, 85),
    "lon": (-180, 180),
    "height_m": (0.5, 200),
    "tx_power_dbm": (0, 30),
    "antenna_gain_dbi": (-5, 15),
    "cable_loss_db": (0, 20),
    "rx_height_m": (0.5, 30),
    "rx_gain_dbi": (-5, 15),
    "frequency_mhz": (863, 870),
    "radius_km": (1, 50),
}


def _fmt(v: float) -> str:
    return f"{v:g}".replace("-", "−").replace(".", ",")


@dataclass
class SiteParams:
    lat: float = 40.85
    lon: float = 14.27
    height_m: float = 10
    tx_power_dbm: float = 22
    antenna_gain_dbi: float = 2
    cable_loss_db: float = 0
    rx_height_m: float = 1.5
    rx_gain_dbi: float = 2
    frequency_mhz: float = 869.525
    preset: str = "LONG_FAST"
    radius_km: float = 15

    @property
    def eirp_dbm(self) -> float:
        return self.tx_power_dbm + self.antenna_gain_dbi - self.cable_loss_db

    @classmethod
    def from_dict(cls, d: dict) -> "SiteParams":
        if not isinstance(d, dict):
            raise PredictionError(400, "Parametri della previsione non validi")
        out: dict = {}
        for f in fields(cls):
            name = f.name
            if name not in d:
                if name in ("lat", "lon"):
                    raise PredictionError(400, f"{name}: valore mancante")
                continue
            v = d[name]
            if name == "preset":
                if v not in PRESETS:
                    raise PredictionError(400, "preset: valore non valido")
                out[name] = v
                continue
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise PredictionError(400, f"{name}: valore non valido")
            lo, hi = _LIMITS[name]
            if not (lo <= v <= hi):  # falso anche per NaN
                raise PredictionError(
                    400, f"{name}: valore fuori dall'intervallo {_fmt(lo)}..{_fmt(hi)}")
            out[name] = float(v)
        return cls(**out)


def step_m(radius_m: float) -> float:
    return min(250, max(30, radius_m / 200))


def _free_space_db(d_km: float, f_mhz: float) -> float:
    return 32.45 + 20 * math.log10(d_km) + 20 * math.log10(f_mhz)


def compute_radial(args: tuple[list[float], float, tuple]) -> list[float]:
    """RSSI previsto (dBm) per ogni passo del radiale; l'indice 0 (il sito) e' nan.

    `args` = (quote dal sito al bordo, passo in m, (eirp, rx_gain, h_tx, h_rx, f_mhz)).
    """
    elev, step, (eirp, rx_gain, h_tx, h_rx, f_mhz) = args
    out = [math.nan]
    for i in range(1, len(elev)):
        pfl = [i, step, *elev[:i + 1]]
        try:
            loss = itm_p2p_loss(h_tx, h_rx, pfl, f_mhz=f_mhz).loss_db
        except Exception:  # noqa: BLE001  ItmError o profilo malformato: spazio libero
            loss = math.nan
        if not math.isfinite(loss):
            loss = _free_space_db(i * step / 1000.0, f_mhz)
        out.append(eirp - loss + rx_gain)
    return out


def _compute_block(block: list[tuple]) -> list[list[float]]:
    return [compute_radial(a) for a in block]


@dataclass
class Grid:
    bbox: list[float]  # [w, s, e, n]
    width: int
    height: int
    values: np.ndarray  # int8, height x width, righe da nord a sud


def _merc_y(lat):
    return np.log(np.tan(np.pi / 4 + np.radians(lat) / 2))


def _destinations(lat: float, lon: float, az_deg: np.ndarray, d_m: np.ndarray):
    """Punti a distanza d e azimut az dal sito (sfera): griglia az x d."""
    p1, l1 = math.radians(lat), math.radians(lon)
    th = np.radians(az_deg)[:, None]
    dl = (np.asarray(d_m, dtype=np.float64) / _EARTH_R)[None, :]
    p2 = np.arcsin(np.sin(p1) * np.cos(dl) + np.cos(p1) * np.sin(dl) * np.cos(th))
    l2 = l1 + np.arctan2(np.sin(th) * np.sin(dl) * np.cos(p1), np.cos(dl) - np.sin(p1) * np.sin(p2))
    return np.degrees(p2), (np.degrees(l2) + 540.0) % 360.0 - 180.0


def rasterize(lat: float, lon: float, radials: np.ndarray, step: float, radius_m: float,
              sens: float) -> Grid:
    radials = np.array(radials, dtype=np.float64)
    nr, n = radials.shape
    # la cella del sito prende il valore del primo passo (l'indice 0 e' nan per definizione)
    radials[:, 0] = np.where(np.isnan(radials[:, 0]), radials[:, min(1, n - 1)], radials[:, 0])
    bbox = bbox_around(lat, lon, radius_m)
    w, s, e, nn = bbox
    side = int(min(MAX_SIDE, math.ceil(2 * radius_m / step)))
    xs = w + (np.arange(side) + 0.5) * (e - w) / side
    my0, my1 = _merc_y(nn), _merc_y(s)
    my = my0 + (np.arange(side) + 0.5) * (my1 - my0) / side
    lats = np.degrees(2 * np.arctan(np.exp(my)) - np.pi / 2)
    lon_g, lat_g = np.meshgrid(xs, lats)
    # distanza (haversine) e azimut iniziale dal sito
    p1, p2 = math.radians(lat), np.radians(lat_g)
    dlon = np.radians(lon_g - lon)
    a = np.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * np.cos(p2) * np.sin(dlon / 2) ** 2
    dist = 2 * _EARTH_R * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    az = np.degrees(np.arctan2(np.sin(dlon) * np.cos(p2),
                               math.cos(p1) * np.sin(p2) - math.sin(p1) * np.cos(p2) * np.cos(dlon)))
    az = az % 360.0
    # bilineare: due radiali vicini x due passi vicini
    fa = az / (360.0 / nr)
    k0 = np.floor(fa).astype(np.int64) % nr
    k1 = (k0 + 1) % nr
    wa = fa - np.floor(fa)
    t = np.clip(dist / step, 0.0, n - 1.0)
    i0 = np.minimum(np.floor(t).astype(np.int64), max(n - 2, 0))
    i1 = np.minimum(i0 + 1, n - 1)
    wt = t - i0
    v0 = radials[k0, i0] * (1 - wt) + radials[k0, i1] * wt
    v1 = radials[k1, i0] * (1 - wt) + radials[k1, i1] * wt
    rssi = v0 * (1 - wa) + v1 * wa
    bad = ~np.isfinite(rssi) | (dist > radius_m)
    # pre-arrotondamento a 1e-6: il rumore dell'interpolazione non sposta i casi a ,5
    margin = np.clip(np.round(np.round(np.where(bad, 0.0, rssi - sens), 6)), -127, 127)
    values = np.where(bad, NODATA, margin).astype(np.int8)
    return Grid(bbox=bbox, width=side, height=side, values=values)


def _sea_clamped(dem):
    """Quote negative (batimetria) a 0 prima dell'interpolazione, per la costa."""
    if isinstance(dem, Dem):
        a = dem.array
        if not (a >= 0).all():  # negativi o NaN: copia solo se serve
            arr = np.maximum(np.nan_to_num(a, nan=0.0), 0.0).astype(np.float32)
            return Dem(arr, dem.z, dem.x0, dem.y0)
    return dem


def predict(params: SiteParams, dem, executor_factory: Callable[[], Executor],
            progress: Callable[[int, int], None], cancel: threading.Event) -> Grid:
    radius_m = params.radius_km * 1000.0
    step = step_m(radius_m)
    n = int(math.ceil(radius_m / step)) + 1
    az = np.arange(N_RADIALS) * (360.0 / N_RADIALS)
    lats, lons = _destinations(params.lat, params.lon, az, np.arange(n) * step)
    elev = np.asarray(_sea_clamped(dem).sample(lats.ravel(), lons.ravel()), dtype=np.float64)
    elev = np.maximum(np.nan_to_num(elev, nan=0.0, posinf=0.0, neginf=0.0), 0.0).reshape(N_RADIALS, n)
    flat = (params.eirp_dbm, params.rx_gain_dbi, params.height_m, params.rx_height_m,
            params.frequency_mhz)
    args = [(elev[k].tolist(), step, flat) for k in range(N_RADIALS)]
    radials = np.full((N_RADIALS, n), np.nan)
    if cancel.is_set():
        raise PredictionError(409, "Calcolo annullato")
    ex = executor_factory()
    try:
        futs = {ex.submit(_compute_block, args[b:b + _BLOCK]): b
                for b in range(0, N_RADIALS, _BLOCK)}
        done = 0
        for fut in as_completed(futs):
            b = futs[fut]
            rows = fut.result()
            radials[b:b + len(rows)] = rows
            done += len(rows)
            progress(done, N_RADIALS)
            if cancel.is_set():
                ex.shutdown(wait=True, cancel_futures=True)
                raise PredictionError(409, "Calcolo annullato")
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
    return rasterize(params.lat, params.lon, radials, step, radius_m,
                     sensitivity_dbm(params.preset))


def default_executor() -> ProcessPoolExecutor:
    return ProcessPoolExecutor(max_workers=max(1, min(4, (os.cpu_count() or 2) - 1)))
