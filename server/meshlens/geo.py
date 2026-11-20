"""Nazione (ISO alpha-2) a partire dalle coordinate, con confini Natural Earth."""
import json
import math
from pathlib import Path

import shapely
from shapely.geometry import Point, shape
from shapely.ops import nearest_points

DEFAULT_PATH = Path(__file__).parent / "data" / "countries.geojson"


class CountryLocator:
    def __init__(self, geojson_path: Path | None = None, tolerance_km: float = 25.0):
        data = json.loads((geojson_path or DEFAULT_PATH).read_text(encoding="utf-8"))
        self.tolerance_km = tolerance_km
        self.names: dict[str, str] = {}
        self._isos: list[str] = []
        geoms = []
        for feat in data["features"]:
            iso = feat["properties"]["iso"]
            self.names[iso] = feat["properties"]["name"]
            self._isos.append(iso)
            geoms.append(shape(feat["geometry"]))
        self._geoms = geoms
        self._tree = shapely.STRtree(geoms)

    def locate(self, lat: float | None, lon: float | None) -> str | None:
        if lat is None or lon is None or (lat == 0.0 and lon == 0.0):
            return None
        point = Point(lon, lat)
        hits = self._tree.query(point, predicate="within")
        if len(hits):
            return self._isos[int(hits[0])]
        idx = int(self._tree.nearest(point))
        near = nearest_points(point, self._geoms[idx])[1]
        dy = (near.y - lat) * 111.0
        dx = (near.x - lon) * 111.0 * math.cos(math.radians(lat))
        if math.hypot(dx, dy) <= self.tolerance_km:
            return self._isos[idx]
        return None
