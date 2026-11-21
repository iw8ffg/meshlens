"""Tessere offline: lettura degli archivi PMTiles scaricati (aree, Italia, mondo).

Ogni archivio si apre una sola volta e si legge con piccole seek (nessun mmap, cosi il file si
puo rilasciare con close() prima di sostituirlo/cancellarlo su Windows).
"""
import json
import logging
import math
import threading
from functools import lru_cache
from pathlib import Path

from pmtiles.tile import (Compression, deserialize_directory, deserialize_header, find_tile,
                          zxy_to_tileid)

log = logging.getLogger(__name__)
WORLD_BOUNDS = [-180.0, -85.0, 180.0, 85.0]
_PRIORITY = {"area": 0, "italy": 1, "world": 2}


def _tile_bounds(z: int, x: int, y: int) -> tuple[float, float, float, float]:
    """(minLon, minLat, maxLon, maxLat) della tessera XYZ (proiezione Web Mercator)."""
    n = 2 ** z

    def lat(yy: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))
    return (x / n * 360 - 180, lat(y + 1), (x + 1) / n * 360 - 180, lat(y))


class _Archive:
    def __init__(self, entry: dict, path: Path):
        self.entry = entry
        self.bbox = entry.get("bbox")
        self.maxzoom = int(entry.get("maxzoom", 0))
        self.lock = threading.Lock()
        self.f = open(path, "rb")
        try:
            self.header = deserialize_header(self._read(0, 127))
        except Exception:
            self.f.close()
            raise
        self.gzip = self.header["tile_compression"] == Compression.GZIP
        self._dir = lru_cache(maxsize=256)(self._load_dir)  # cache delle directory

    def _read(self, offset: int, length: int) -> bytes:
        with self.lock:
            self.f.seek(offset)
            return self.f.read(length)

    def _load_dir(self, offset: int, length: int):
        return deserialize_directory(self._read(offset, length))

    def get(self, z: int, x: int, y: int) -> bytes | None:
        tile_id = zxy_to_tileid(z, x, y)
        off, ln = self.header["root_offset"], self.header["root_length"]
        for _ in range(4):
            res = find_tile(self._dir(off, ln), tile_id)
            if not res:
                return None
            if res.run_length == 0:  # puntatore a una directory foglia
                off, ln = self.header["leaf_directory_offset"] + res.offset, res.length
            else:
                return self._read(self.header["tile_data_offset"] + res.offset, res.length)
        return None

    def covers(self, z: int, x: int, y: int) -> bool:
        if z > self.maxzoom:
            return False
        if not self.bbox:
            return True
        w, s, e, n = _tile_bounds(z, x, y)
        return not (e < self.bbox[0] or w > self.bbox[2] or n < self.bbox[1] or s > self.bbox[3])

    def close(self) -> None:
        with self.lock:
            self.f.close()


class TileStore:
    def __init__(self, maps_dir):
        self.maps_dir = Path(maps_dir)
        self._lock = threading.RLock()
        self._archives: list[_Archive] = []
        self.reload()

    def release(self) -> None:
        """Chiude i file aperti (da chiamare prima di sostituire/cancellare un archivio)."""
        with self._lock:
            for a in self._archives:
                a.close()
            self._archives = []

    close = release

    def reload(self) -> None:
        """Rilegge maps.json e riapre gli archivi; quelli illeggibili vengono ignorati."""
        try:
            items = json.loads((self.maps_dir / "maps.json").read_text("utf-8")).get("maps", [])
            if not isinstance(items, list):
                items = []
        except (OSError, ValueError, AttributeError):
            items = []
        items = [m for m in items if isinstance(m, dict) and isinstance(m.get("id"), str)]
        # aree dalla piu recente, poi Italia, poi mondo
        items.sort(key=lambda m: (_PRIORITY.get(m.get("kind"), 3), -float(m.get("created") or 0)))
        opened: list[_Archive] = []
        for m in items:
            try:
                opened.append(_Archive(m, self.maps_dir / f"{m['id']}.pmtiles"))
            except Exception as e:
                log.warning("Archivio %s ignorato: %s", m.get("id"), type(e).__name__)
                continue  # archivio mancante o corrotto: non si usa
        with self._lock:
            self.release()
            self._archives = opened

    def get(self, z: int, x: int, y: int) -> tuple[bytes, str | None] | None:
        with self._lock:
            for a in self._archives:
                if not a.covers(z, x, y):
                    continue
                try:
                    data = a.get(z, x, y)
                except (ValueError, OSError):
                    continue  # archivio chiuso o danneggiato
                if data is not None:
                    return data, ("gzip" if a.gzip else None)
        return None

    def info(self) -> dict:
        with self._lock:
            archives = list(self._archives)
        if not archives:
            return {"has_offline": False, "maxzoom": 0, "bounds": None}
        boxes = [a.bbox or WORLD_BOUNDS for a in archives]
        return {"has_offline": True, "maxzoom": max(a.maxzoom for a in archives),
                "bounds": [min(b[0] for b in boxes), min(b[1] for b in boxes),
                           max(b[2] for b in boxes), max(b[3] for b in boxes)]}
