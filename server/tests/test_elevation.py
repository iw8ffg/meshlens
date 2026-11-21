import struct
import threading
import zlib

import numpy as np
import pytest

from meshlens import elevation as el
from meshlens.elevation import (Dem, ElevationCache, ElevationError, bbox_around,
                                decode_terrarium_png, tiles_for_bbox)


def _chunk(t: bytes, d: bytes) -> bytes:
    return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d))


def _png(rgb: np.ndarray, filters: list[int], depth: int = 8, interlace: int = 0,
         ctype: int = 2) -> bytes:
    h, w, bpp = rgb.shape
    rows = []
    prev = np.zeros(w * bpp, dtype=np.int64)
    for y in range(h):
        line = rgb[y].reshape(-1).astype(np.int64)
        f = filters[y % len(filters)]
        a = np.concatenate([np.zeros(bpp, dtype=np.int64), line[:-bpp]])
        c = np.concatenate([np.zeros(bpp, dtype=np.int64), prev[:-bpp]])
        if f == 0:
            enc = line
        elif f == 1:
            enc = line - a
        elif f == 2:
            enc = line - prev
        elif f == 3:
            enc = line - ((a + prev) >> 1)
        else:
            p = a + prev - c
            pa, pb, pc = abs(p - a), abs(p - prev), abs(p - c)
            pred = np.where((pa <= pb) & (pa <= pc), a, np.where(pb <= pc, prev, c))
            enc = line - pred
        rows.append(bytes([f]) + (enc & 0xFF).astype(np.uint8).tobytes())
        prev = line
    ihdr = struct.pack(">IIBBBBB", w, h, depth, ctype, 0, 0, interlace)
    return (b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr)
            + _chunk(b"IDAT", zlib.compress(b"".join(rows))) + _chunk(b"IEND", b""))


def _flat(r, g, b):
    a = np.zeros((256, 256, 3), dtype=np.uint8)
    a[...] = (r, g, b)
    return a


def test_decode_filters():
    rng = np.random.default_rng(1)
    rgb = rng.integers(0, 256, (256, 256, 3), dtype=np.uint8)
    out = decode_terrarium_png(_png(rgb, [0, 1, 2, 3, 4]))
    expect = (rgb[..., 0].astype(np.float32) * 256 + rgb[..., 1] + rgb[..., 2] / 256.0 - 32768.0)
    assert out.dtype == np.float32 and out.shape == (256, 256)
    np.testing.assert_allclose(out, expect, atol=1e-3)


def test_decode_rgba():
    rgba = np.zeros((256, 256, 4), dtype=np.uint8)
    rgba[..., 0] = 128
    rgba[..., 3] = 255
    out = decode_terrarium_png(_png(rgba, [4], ctype=6))
    assert np.all(out == 0.0)


def test_decode_values():
    assert np.all(decode_terrarium_png(_png(_flat(128, 0, 0), [0])) == 0.0)
    assert np.allclose(decode_terrarium_png(_png(_flat(128, 100, 128), [0])), 100.5)
    assert np.allclose(decode_terrarium_png(_png(_flat(127, 0, 0), [0])), -256.0)


def test_decode_rejects():
    good = _png(_flat(128, 0, 0), [0])
    with pytest.raises(ElevationError):
        decode_terrarium_png(_png(_flat(128, 0, 0), [0], depth=16))
    with pytest.raises(ElevationError):
        decode_terrarium_png(_png(_flat(128, 0, 0), [0], interlace=1))
    with pytest.raises(ElevationError):
        decode_terrarium_png(good[:len(good) // 2])
    with pytest.raises(ElevationError):
        decode_terrarium_png(b"non un png")


def test_tiles_for_bbox():
    tiles = tiles_for_bbox(bbox_around(40.85, 14.27, 15000))
    assert 9 <= len(tiles) <= 30
    assert len(set(tiles)) == len(tiles)
    assert tiles == sorted(tiles, key=lambda t: (t[2], t[1]))
    xs = sorted({t[1] for t in tiles})
    ys = sorted({t[2] for t in tiles})
    assert xs == list(range(xs[0], xs[-1] + 1)) and ys == list(range(ys[0], ys[-1] + 1))
    assert len(tiles) == len(xs) * len(ys)


def _ll(gx, gy, z=12):
    """Pixel Mercatore globali -> (lat, lon)."""
    n = 2 ** z * 256
    lon = gx / n * 360 - 180
    lat = float(np.degrees(np.arctan(np.sinh(np.pi * (1 - 2 * gy / n)))))
    return lat, lon


def test_sample_bilinear_and_clamp():
    a = np.zeros((512, 512), dtype=np.float32)
    a[:, :] = np.arange(512)[None, :] * 10.0  # rampa in x
    dem = Dem(a, 12, 100, 200)
    gx0, gy0 = 100 * 256, 200 * 256
    # centro del pixel (5, 7): valore esatto
    lat, lon = _ll(gx0 + 5.5, gy0 + 7.5)
    assert dem.sample(np.array([lat]), np.array([lon]))[0] == pytest.approx(50.0, abs=1e-2)
    # meta' tra i pixel 5 e 6: media
    lat, lon = _ll(gx0 + 6.0, gy0 + 7.5)
    assert dem.sample(np.array([lat]), np.array([lon]))[0] == pytest.approx(55.0, abs=1e-2)
    # quote negative -> 0
    neg = Dem(np.full((512, 512), -40.0, dtype=np.float32), 12, 100, 200)
    assert neg.sample(np.array([lat]), np.array([lon]))[0] == 0.0


def _tile_png(seed):
    return _png(_flat(128, seed, 0), [0])


def _url_tile(url):
    z, x, y = url.rsplit("/", 3)[-3:]
    return int(z), int(x), int(y.removesuffix(".png"))


def test_download_atomic(tmp_path):
    tiles = [(12, 1, 1), (12, 2, 1), (12, 3, 1), (12, 4, 1)]

    def fetch(url):
        if _url_tile(url) == (12, 4, 1):
            raise ElevationError("Riquadro di altitudine non disponibile: 12/4/1")
        return _tile_png(1)

    c = ElevationCache(tmp_path, fetch=fetch)
    with pytest.raises(ElevationError, match="non disponibile"):
        c.download(tiles, lambda d, t: None, threading.Event(), workers=1)
    assert len(list((tmp_path / "terrarium").rglob("*.png"))) == 3
    assert not list(tmp_path.rglob("*.tmp"))
    assert c.missing(tiles) == [(12, 4, 1)]

    # PNG troncato: non salvato
    c2 = ElevationCache(tmp_path / "b", fetch=lambda u: _tile_png(1)[:50])
    with pytest.raises(ElevationError):
        c2.download([(12, 1, 1)], lambda d, t: None, threading.Event(), workers=1)
    assert c2.missing([(12, 1, 1)]) == [(12, 1, 1)]
    assert not list((tmp_path / "b").rglob("*.png")) and not list((tmp_path / "b").rglob("*.tmp"))

    # un nuovo tentativo scarica solo il mancante
    calls = []
    c3 = ElevationCache(tmp_path, fetch=lambda u: calls.append(u) or _tile_png(1))
    c3.download(c3.missing(tiles), lambda d, t: None, threading.Event(), workers=1)
    assert len(calls) == 1 and c3.missing(tiles) == []


def test_download_cancel(tmp_path):
    cancel = threading.Event()
    seen = []

    def progress(d, t):
        seen.append(d)
        cancel.set()

    c = ElevationCache(tmp_path, fetch=lambda u: _tile_png(1))
    tiles = [(12, x, 1) for x in range(1, 6)]
    c.download(tiles, progress, cancel, workers=1)
    assert seen == [1]
    assert len(c.missing(tiles)) == 4


def test_mosaic(tmp_path):
    c = ElevationCache(tmp_path, fetch=lambda u: _tile_png(_url_tile(u)[1] % 256))
    bbox = bbox_around(40.85, 14.27, 3000)
    tiles = tiles_for_bbox(bbox)
    c.download(tiles, lambda d, t: None, threading.Event())
    dem = c.mosaic(bbox)
    assert dem.array.shape[0] % 256 == 0 and dem.z == 12
    assert dem.x0 == min(t[1] for t in tiles) and dem.y0 == min(t[2] for t in tiles)
    v = dem.sample(np.array([40.85]), np.array([14.27]))
    assert v.shape == (1,) and v[0] >= 0


def test_mosaic_missing(tmp_path):
    c = ElevationCache(tmp_path, fetch=lambda u: _tile_png(1))
    with pytest.raises(ElevationError, match="Dati di altitudine mancanti per l'area"):
        c.mosaic(bbox_around(40.85, 14.27, 3000))


def test_cleanup_tmp(tmp_path):
    p = tmp_path / "terrarium" / "12" / "1"
    p.mkdir(parents=True)
    (p / "1.png.tmp").write_bytes(b"x")
    ElevationCache(tmp_path).cleanup_tmp()
    assert not list(tmp_path.rglob("*.tmp"))


def test_fetch_https_only():
    with pytest.raises(ElevationError, match="solo download https"):
        el.default_fetch("http://example.com/a.png")


def test_mosaic_corrupt_tile_removed(tmp_path):
    c = ElevationCache(tmp_path, fetch=lambda u: _tile_png(1))
    bbox = bbox_around(40.85, 14.27, 3000)
    tiles = tiles_for_bbox(bbox)
    c.download(tiles, lambda d, t: None, threading.Event())
    bad = c._path(tiles[0])
    bad.write_bytes(b"non e' un png")
    with pytest.raises(ElevationError, match="danneggiato e rimosso: ricalcola"):
        c.mosaic(bbox)
    assert not bad.exists() and c.missing(tiles) == [tiles[0]]


def test_fetch_rejects_oversize(monkeypatch):
    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, n=-1):
            return b"x" * n

    monkeypatch.setattr(el.urllib.request, "urlopen", lambda *a, **k: Resp())
    with pytest.raises(ElevationError, match="troppo grande"):
        el.default_fetch("https://example.com/a.png")
