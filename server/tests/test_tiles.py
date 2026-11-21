import gzip
import json
import math

from pmtiles.tile import Compression, TileType, zxy_to_tileid
from pmtiles.writer import Writer

from meshlens.tiles import TileStore
from test_api import client, logged, make_ctx
from test_maps import make_manager

ITALY = [6.6, 36.6, 18.6, 47.1]


def xy(z, lon, lat):
    n = 2 ** z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


def make_archive(path, tiles, maxzoom, gz=True):
    """tiles: {(z,x,y): bytes}. Crea un piccolo PMTiles reale con pmtiles.writer."""
    with open(path, "wb") as f:
        w = Writer(f)
        for (z, x, y), data in sorted(tiles.items(), key=lambda kv: zxy_to_tileid(*kv[0])):
            w.write_tile(zxy_to_tileid(z, x, y), data)
        w.finalize({"tile_type": TileType.MVT,
                    "tile_compression": Compression.GZIP if gz else Compression.NONE,
                    "min_zoom": 0, "max_zoom": maxzoom,
                    "min_lon_e7": -1800000000, "min_lat_e7": -850000000,
                    "max_lon_e7": 1800000000, "max_lat_e7": 850000000,
                    "center_zoom": 0, "center_lon_e7": 0, "center_lat_e7": 0}, {})


def entry(id_, kind, bbox, maxzoom, created=1.0):
    return {"id": id_, "name": id_, "kind": kind, "bbox": bbox, "maxzoom": maxzoom,
            "size_bytes": 1, "created": created, "source_date": None}


def setup(tmp_path, gz=True):
    d = tmp_path / "maps"
    d.mkdir(exist_ok=True)
    ix, iy = xy(5, 12.5, 42)
    ix10, iy10 = xy(10, 12.5, 42)
    make_archive(d / "world.pmtiles", {(5, ix, iy): b"WORLD", (0, 0, 0): b"W0"}, 6, gz)
    make_archive(d / "italy.pmtiles", {(5, ix, iy): b"ITALY", (10, ix10, iy10): b"IT10"}, 14, gz)
    (d / "maps.json").write_text(json.dumps({"maps": [
        entry("world", "world", None, 6), entry("italy", "italy", ITALY, 14)]}))
    return d, (ix, iy), (ix10, iy10)


def test_priority_italy_over_world_same_tile(tmp_path):
    d, (ix, iy), (jx, jy) = setup(tmp_path)
    s = TileStore(d)
    assert s.get(5, ix, iy) == (b"ITALY", "gzip")
    assert s.get(10, jx, jy)[0] == b"IT10"
    assert s.get(0, 0, 0)[0] == b"W0"  # fuori dalla bbox Italia: solo il mondo
    s.close()


def test_area_most_recent_first_and_bbox_skip(tmp_path):
    d, (ix, iy), _ = setup(tmp_path)
    make_archive(d / "area-1.pmtiles", {(5, ix, iy): b"A1"}, 14)
    make_archive(d / "area-2.pmtiles", {(5, ix, iy): b"A2"}, 14)
    items = json.loads((d / "maps.json").read_text())["maps"]
    items += [entry("area-1", "area", [12, 41, 13, 43], 14, 10.0),
              entry("area-2", "area", [12, 41, 13, 43], 14, 20.0)]
    (d / "maps.json").write_text(json.dumps({"maps": items}))
    s = TileStore(d)
    assert s.get(5, ix, iy)[0] == b"A2"
    # tessera z5 lontana dall'area: l'area si salta e si passa all'Italia
    ox, oy = xy(5, 7.0, 37.0)
    make_archive(d / "italy.pmtiles", {(5, ox, oy): b"ITALY2"}, 14)
    s.reload()
    assert s.get(5, ox, oy)[0] == b"ITALY2"
    s.close()


def test_missing_tile_and_above_maxzoom(tmp_path):
    d, _, (jx, jy) = setup(tmp_path)
    s = TileStore(d)
    assert s.get(5, 0, 0) is None
    assert s.get(15, 0, 0) is None
    ox, oy = xy(10, 2.35, 48.85)  # Parigi z10: nessuna area scaricata
    assert s.get(10, ox, oy) is None
    s.close()


def test_no_gzip_when_archive_uncompressed(tmp_path):
    d, (ix, iy), _ = setup(tmp_path, gz=False)
    s = TileStore(d)
    assert s.get(5, ix, iy) == (b"ITALY", None)
    s.close()


def test_reload_after_delete(tmp_path):
    d, (ix, iy), _ = setup(tmp_path)
    s = TileStore(d)
    assert s.get(5, ix, iy)[0] == b"ITALY"
    s.release()  # Windows: rilascio prima di cancellare
    (d / "italy.pmtiles").unlink()
    (d / "maps.json").write_text(json.dumps({"maps": [entry("world", "world", None, 6)]}))
    s.reload()
    assert s.get(5, ix, iy)[0] == b"WORLD"
    s.close()


def test_info(tmp_path):
    s = TileStore(tmp_path / "vuota")
    assert s.info() == {"has_offline": False, "maxzoom": 0, "bounds": None}
    d, _, _ = setup(tmp_path)
    s = TileStore(d)
    assert s.info() == {"has_offline": True, "maxzoom": 14, "bounds": [-180.0, -85.0, 180.0, 85.0]}
    s.close()


async def test_style_info_and_tile_routes(tmp_path):
    ctx = make_ctx()
    ctx.maps = make_manager(tmp_path)
    d, (ix, iy), _ = setup(tmp_path)  # tmp_path/maps e la maps_dir del manager
    make_archive(d / "italy.pmtiles", {(5, ix, iy): gzip.compress(b"ITALY")}, 14)
    ctx.maps.tiles.reload()
    async with logged(ctx) as c:
        si = (await c.get("/api/maps/style-info")).json()
        assert si["has_offline"] is True and si["maxzoom"] == 14
        r = await c.get(f"/tiles/5/{ix}/{iy}.mvt")
        assert r.status_code == 200 and r.content == b"ITALY"
        assert r.headers["content-type"] == "application/x-protobuf"
        assert r.headers["content-encoding"] == "gzip"
        assert (await c.get("/tiles/5/0/0.mvt")).status_code == 204
        assert (await c.get("/tiles/3/99/0.mvt")).status_code == 204
    ctx.maps.tiles.close()


async def test_gzip_header_when_archive_gzip(tmp_path):
    ctx = make_ctx()
    ctx.maps = make_manager(tmp_path)
    d, (ix, iy), _ = setup(tmp_path, gz=False)
    ctx.maps.tiles.reload()
    async with logged(ctx) as c:
        r = await c.get(f"/tiles/5/{ix}/{iy}.mvt")
        assert r.status_code == 200 and "content-encoding" not in r.headers
    ctx.maps.tiles.close()


async def test_tiles_require_auth(tmp_path):
    ctx = make_ctx()
    ctx.maps = make_manager(tmp_path)
    async with client(ctx) as c:
        assert (await c.get("/tiles/0/0/0.mvt")).status_code == 401
        assert (await c.get("/api/maps/style-info")).status_code == 401
