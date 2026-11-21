"""Dati di altitudine (riquadri Terrarium): download, cache su disco e decodifica.

I riquadri sono PNG RGB a 256 x 256: quota in metri = R*256 + G + B/256 - 32768.
Il decodificatore PNG e' minimale (solo numpy + zlib) per non aggiungere dipendenze.
"""
from __future__ import annotations

import math
import os
import struct
import threading
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit

import numpy as np

from .maps import user_agent

TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"
DEM_ZOOM = 12
TILE_SIZE = 256
TILE_BYTES_ESTIMATE = 90_000

_PNG_SIG = b"\x89PNG\r\n\x1a\n"
_MAX_LAT = 85.05112878


class ElevationError(Exception):
    pass


# --- geometria dei riquadri -------------------------------------------------

def _merc_xy(lat, lon, z: int):
    """Coordinate pixel Mercatore globali (frazionarie) a zoom z."""
    n = (2 ** z) * TILE_SIZE
    lat = np.clip(np.asarray(lat, dtype=np.float64), -_MAX_LAT, _MAX_LAT)
    lon = np.asarray(lon, dtype=np.float64)
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - np.log(np.tan(np.radians(lat)) + 1.0 / np.cos(np.radians(lat))) / math.pi) / 2.0 * n
    return x, y


def _tile_xy(lat: float, lon: float, z: int) -> tuple[int, int]:
    x, y = _merc_xy(lat, lon, z)
    last = 2 ** z - 1
    return (min(max(int(x // TILE_SIZE), 0), last), min(max(int(y // TILE_SIZE), 0), last))


def tiles_for_bbox(bbox: list[float], z: int = DEM_ZOOM) -> list[tuple[int, int, int]]:
    """Riquadri (z, x, y) che coprono [w, s, e, n], per riga e poi per colonna."""
    w, s, e, n = bbox
    x0, y0 = _tile_xy(n, w, z)
    x1, y1 = _tile_xy(s, e, z)
    return [(z, x, y) for y in range(y0, y1 + 1) for x in range(x0, x1 + 1)]


def bbox_around(lat: float, lon: float, radius_m: float) -> list[float]:
    dlat = radius_m / 111_320.0
    dlon = radius_m / (111_320.0 * max(math.cos(math.radians(lat)), 0.01))
    return [lon - dlon, lat - dlat, lon + dlon, lat + dlat]


# --- decodifica PNG ---------------------------------------------------------

def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c


def _unfilter(raw: bytes, h: int, stride: int, bpp: int) -> np.ndarray:
    out = np.zeros((h, stride), dtype=np.uint8)
    prev = np.zeros(stride, dtype=np.uint8)
    pos = 0
    for y in range(h):
        ft = raw[pos]
        line = np.frombuffer(raw, dtype=np.uint8, count=stride, offset=pos + 1)
        pos += stride + 1
        if ft == 0:
            cur = line.copy()
        elif ft == 1:  # Sub: somma cumulata per canale
            cur = (np.cumsum(line.reshape(-1, bpp).astype(np.uint32), axis=0) & 0xFF) \
                .astype(np.uint8).reshape(-1)
        elif ft == 2:  # Up
            cur = line + prev
        elif ft in (3, 4):  # Average / Paeth: dipendono dal pixel precedente
            lst, up = line.tolist(), prev.tolist()
            res = [0] * stride
            for i in range(stride):
                a = res[i - bpp] if i >= bpp else 0
                b = up[i]
                if ft == 3:
                    res[i] = (lst[i] + ((a + b) >> 1)) & 0xFF
                else:
                    c = up[i - bpp] if i >= bpp else 0
                    res[i] = (lst[i] + _paeth(a, b, c)) & 0xFF
            cur = np.array(res, dtype=np.uint8)
        else:
            raise ElevationError("PNG di altitudine non valido: filtro sconosciuto")
        out[y] = cur
        prev = cur
    return out


def decode_terrarium_png(data: bytes) -> np.ndarray:
    """PNG Terrarium -> float32 256 x 256 in metri."""
    if not data.startswith(_PNG_SIG):
        raise ElevationError("PNG di altitudine non valido")
    pos = len(_PNG_SIG)
    ihdr = None
    idat = bytearray()
    ended = False
    try:
        while pos + 8 <= len(data):
            length, ctype = struct.unpack(">I4s", data[pos:pos + 8])
            body = data[pos + 8:pos + 8 + length]
            if len(body) != length or pos + 12 + length > len(data):
                raise ElevationError("PNG di altitudine troncato")
            if ctype == b"IHDR":
                ihdr = struct.unpack(">IIBBBBB", body)
            elif ctype == b"IDAT":
                idat += body
            elif ctype == b"IEND":
                ended = True
                break
            pos += 12 + length
    except struct.error as e:
        raise ElevationError("PNG di altitudine non valido") from e
    if ihdr is None or not ended:
        raise ElevationError("PNG di altitudine troncato")
    w, h, depth, color, _comp, _filt, interlace = ihdr
    if depth != 8 or color not in (2, 6) or interlace != 0:
        raise ElevationError("PNG di altitudine non supportato (servono 8 bit, RGB/RGBA, non interlacciato)")
    if w != TILE_SIZE or h != TILE_SIZE:
        raise ElevationError("PNG di altitudine con dimensioni inattese")
    bpp = 3 if color == 2 else 4
    stride = w * bpp
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error as e:
        raise ElevationError("PNG di altitudine corrotto") from e
    if len(raw) != h * (stride + 1):
        raise ElevationError("PNG di altitudine troncato")
    px = _unfilter(raw, h, stride, bpp).reshape(h, w, bpp).astype(np.float32)
    return (px[..., 0] * 256.0 + px[..., 1] + px[..., 2] / 256.0 - 32768.0).astype(np.float32)


# --- modello digitale del terreno ------------------------------------------

class Dem:
    """Mosaico di riquadri; (x0, y0) e' il riquadro in alto a sinistra."""

    def __init__(self, array: np.ndarray, z: int, x0: int, y0: int):
        self.array = array
        self.z = z
        self.x0 = x0
        self.y0 = y0

    def sample(self, lats: np.ndarray, lons: np.ndarray) -> np.ndarray:
        """Quota bilineare (m, minimo 0) nei punti dati. Fuori dal mosaico: valore del bordo."""
        gx, gy = _merc_xy(lats, lons, self.z)
        # il centro del pixel i cade a i + 0.5
        px = gx - self.x0 * TILE_SIZE - 0.5
        py = gy - self.y0 * TILE_SIZE - 0.5
        hh, ww = self.array.shape
        px = np.clip(px, 0.0, ww - 1.0)
        py = np.clip(py, 0.0, hh - 1.0)
        ix = np.minimum(np.floor(px).astype(np.int64), max(ww - 2, 0))
        iy = np.minimum(np.floor(py).astype(np.int64), max(hh - 2, 0))
        fx, fy = px - ix, py - iy
        ix1 = np.minimum(ix + 1, ww - 1)
        iy1 = np.minimum(iy + 1, hh - 1)
        a = self.array
        top = a[iy, ix] * (1 - fx) + a[iy, ix1] * fx
        bot = a[iy1, ix] * (1 - fx) + a[iy1, ix1] * fx
        return np.maximum(top * (1 - fy) + bot * fy, 0.0)


# --- download e cache -------------------------------------------------------

def default_fetch(url: str) -> bytes:
    if urlsplit(url).scheme != "https":
        raise ElevationError("Sono ammessi solo download https")
    req = urllib.request.Request(url, headers={"User-Agent": user_agent()})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            zxy = "/".join(url.rsplit("/", 3)[-3:]).removesuffix(".png")
            raise ElevationError(f"Riquadro di altitudine non disponibile: {zxy}") from e
        raise ElevationError(f"Download dei dati di altitudine non riuscito: HTTP {e.code}") from e
    except (urllib.error.URLError, OSError) as e:
        raise ElevationError(f"Download dei dati di altitudine non riuscito: {e}") from e


class ElevationCache:
    def __init__(self, root: Path, fetch: Callable[[str], bytes] = default_fetch):
        self.root = Path(root)
        self.fetch = fetch

    def _path(self, t: tuple[int, int, int]) -> Path:
        z, x, y = t
        return self.root / "terrarium" / str(z) / str(x) / f"{y}.png"

    def missing(self, tiles) -> list[tuple]:
        return [t for t in tiles if not self._path(t).is_file()]

    def download(self, tiles, progress: Callable[[int, int], None],
                 cancel: threading.Event, workers: int = 4) -> None:
        tiles = list(tiles)
        total = len(tiles)
        lock = threading.Lock()
        state: dict = {"done": 0, "error": None}

        def one(t):
            if cancel.is_set() or state["error"] is not None:
                return
            z, x, y = t
            try:
                data = self.fetch(TERRARIUM_URL.format(z=z, x=x, y=y))
                decode_terrarium_png(data)  # verifica prima di salvare
                path = self._path(t)
                path.parent.mkdir(parents=True, exist_ok=True)
                tmp = path.with_name(path.name + ".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, path)
            except Exception as e:  # noqa: BLE001
                with lock:
                    if state["error"] is None:
                        state["error"] = e
                return
            with lock:
                state["done"] += 1
                progress(state["done"], total)

        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            list(pool.map(one, tiles))
        err = state["error"]
        if err is not None:
            if isinstance(err, ElevationError):
                raise err
            raise ElevationError(f"Download dei dati di altitudine non riuscito: {err}") from err

    def mosaic(self, bbox: list[float]) -> Dem:
        tiles = tiles_for_bbox(bbox)
        if self.missing(tiles):
            raise ElevationError("Dati di altitudine mancanti per l'area")
        xs = sorted({x for _, x, _ in tiles})
        ys = sorted({y for _, _, y in tiles})
        z = tiles[0][0]
        arr = np.zeros((len(ys) * TILE_SIZE, len(xs) * TILE_SIZE), dtype=np.float32)
        for (_, x, y) in tiles:
            try:
                tile = decode_terrarium_png(self._path((z, x, y)).read_bytes())
            except OSError as e:
                raise ElevationError("Dati di altitudine mancanti per l'area") from e
            r, c = (y - ys[0]) * TILE_SIZE, (x - xs[0]) * TILE_SIZE
            arr[r:r + TILE_SIZE, c:c + TILE_SIZE] = tile
        return Dem(arr, z, xs[0], ys[0])

    def cleanup_tmp(self) -> None:
        base = self.root / "terrarium"
        if base.is_dir():
            for p in base.rglob("*.tmp"):
                try:
                    p.unlink()
                except OSError:
                    pass
