"""Scarica i confini Natural Earth (dominio pubblico) e genera countries.geojson."""
import json
import urllib.request
from pathlib import Path

URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/"
    "geojson/ne_50m_admin_0_countries.geojson"
)
OUT = Path(__file__).resolve().parent.parent / "server" / "meshlens" / "data" / "countries.geojson"


def _round(coords):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], 4), round(coords[1], 4)]
    return [_round(c) for c in coords]


def main() -> None:
    with urllib.request.urlopen(URL, timeout=120) as resp:
        src = json.load(resp)
    features = []
    for feat in src["features"]:
        props = feat["properties"]
        iso = props.get("ISO_A2_EH")
        if not iso or iso == "-99":
            continue
        geom = feat["geometry"]
        features.append({
            "type": "Feature",
            "properties": {"iso": iso, "name": props.get("NAME_IT") or props.get("NAME")},
            "geometry": {"type": geom["type"], "coordinates": _round(geom["coordinates"])},
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"type": "FeatureCollection", "features": features},
                   separators=(",", ":"), ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"{len(features)} nazioni -> {OUT} ({OUT.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
