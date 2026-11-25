"""Crea un database dimostrativo GRANDE per provare il grafo di topologia di MeshLens.

Uso:  python tools/topology_bigdemo.py CARTELLA_DATI
Poi:  meshlens run --data-dir CARTELLA_DATI      (vista Rete > Topologia)

Parte dal database di tools/demo_seed.py e aggiunge circa 460 nodi finti sparsi per l'Italia, con nomi
inventati e circa mille collegamenti finti dalla struttura realistica: alcuni gruppi regionali densi
uniti da pochi nodi cerniera, una ventina di piccoli gruppi separati e molti nodi isolati. Tutti i
dati sono inventati e riproducibili (seme fisso). Serve PYTHONPATH=server (o il pacchetto installato).
"""
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import demo_seed  # noqa: E402

from meshlens.db import connect  # noqa: E402
from meshlens.store import Store  # noqa: E402
from meshlens.topology import SOURCES, build_topology  # noqa: E402

SEED = 20241125
# (centro, dispersione in gradi): gruppi regionali densi
REGIONS = [
    ((45.46, 9.19), 0.30), ((45.07, 7.69), 0.25), ((45.44, 12.32), 0.25), ((44.49, 11.34), 0.28),
    ((43.77, 11.25), 0.30), ((41.90, 12.50), 0.35), ((40.85, 14.27), 0.30),
]
CLUSTER_SIZE = 36
HINGES_PER_LINK = 1          # nodi cerniera tra due gruppi vicini nella catena
SMALL_GROUPS = 20
ISOLATED = 119
TOTAL_NEW = 460
PRE = ["Torre", "Colle", "Ponte", "Rifugio", "Faro", "Borgo", "Villa", "Cascina", "Pieve", "Monte", "Lago", "Piazza", "Porto", "Tetto", "Casa", "Campanile"]
POST = ["Alto", "Basso", "Nord", "Sud", "Verde", "Rosso", "Vecchio", "Nuovo", "Sereno", "Bello", "Antico", "Piccolo", "Grande", "Mimosa", "Ulivi", "Pini"]
HW = ["HELTEC_V3", "TBEAM", "TLORA_T3_S3", "T_DECK", "RAK4631", "STATION_G2"]
ROLES = ["CLIENT", "CLIENT", "CLIENT", "ROUTER", "CLIENT_MUTE", "REPEATER"]
SRC_W = [("neighborinfo", 5), ("traceroute", 3), ("rf_direct", 3), ("mqtt_gateway", 2)]


def _pick_source(rng: random.Random) -> str:
    return rng.choices([s for s, _ in SRC_W], [w for _, w in SRC_W])[0]


def build(out_dir: Path | str, now: float | None = None) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    now = time.time() if now is None else now
    info = demo_seed.build(out_dir, now)
    rng = random.Random(SEED)
    conn = connect(out_dir / "meshlens.db")
    store = Store(conn)
    nums: list[int] = []
    pos: dict[int, tuple[float, float] | None] = {}
    used_names: set[str] = set()

    def new_node(lat: float, lon: float, hinge: bool = False) -> int:
        i = len(nums)
        num = 0xE0000000 + i * 0x37
        nums.append(num)
        has_pos = rng.random() > 0.15
        for _ in range(30):
            name = f"{rng.choice(PRE)} {rng.choice(POST)} {rng.randint(1, 99)}"
            if name not in used_names:
                used_names.add(name)
                break
        heard = now - rng.uniform(120, 40 * 3600)
        store.upsert_node({
            "num": num, "long_name": name, "short_name": f"F{i:03d}"[:4],
            "hw_model": rng.choice(HW), "role": "ROUTER" if hinge else rng.choice(ROLES),
            "firmware": "2.7.11", "lat": lat if has_pos else None, "lon": lon if has_pos else None,
            "precision_bits": 32 if has_pos else None, "position_source": "mqtt" if has_pos else None,
            "position_time": heard if has_pos else None, "country": "IT", "last_heard": heard,
            "sources": ["mqtt"], "battery": rng.randint(15, 100),
            "voltage": round(rng.uniform(3.5, 4.15), 2), "mqtt_gateways": rng.randint(1, 3),
            "last_snr": round(rng.uniform(-15, 9), 1), "hops": rng.randint(0, 3),
        }, is_mine=False)
        pos[num] = (lat, lon) if has_pos else None
        return num

    def link(a: int, b: int) -> None:
        if a == b:
            return
        store.upsert_link(a, b, _pick_source(rng), round(rng.uniform(-14, 9), 1),
                          now - rng.uniform(300, 5 * 86400))

    edges: set[tuple[int, int]] = set()

    def add_edge(a: int, b: int) -> bool:
        key = (a, b) if a < b else (b, a)
        if a == b or key in edges:
            return False
        edges.add(key)
        link(a, b)
        return True

    # gruppi regionali: albero con attacco preferenziale + collegamenti verso i nodi geograficamente vicini
    clusters: list[list[int]] = []
    for (clat, clon), spread in REGIONS:
        members: list[int] = []
        for _ in range(CLUSTER_SIZE):
            members.append(new_node(clat + rng.gauss(0, spread), clon + rng.gauss(0, spread * 1.3)))
        deg = {m: 0 for m in members}
        for k in range(1, len(members)):
            cand = members[:k]
            tgt = rng.choices(cand, [1 + deg[c] ** 1.5 for c in cand])[0]
            if add_edge(members[k], tgt):
                deg[members[k]] += 1
                deg[tgt] += 1
        extra = int(len(members) * 2.5)
        for _ in range(extra * 3):
            if extra <= 0:
                break
            a = rng.choice(members)
            near = sorted(members, key=lambda m: (abs(m - a) % 7, rng.random()))[:6]
            if add_edge(a, rng.choice(near)):
                extra -= 1
        clusters.append(members)

    # cerniere tra gruppi: una catena con qualche scorciatoia, ogni ponte passa da un nodo cerniera
    chain = [(i, i + 1) for i in range(len(clusters) - 1)] + [(0, 3), (3, 5)]
    for ia, ib in chain:
        for _ in range(HINGES_PER_LINK):
            (la, lo), _s = REGIONS[ia]
            (lb, lob), _s2 = REGIONS[ib]
            h = new_node((la + lb) / 2 + rng.gauss(0, 0.1), (lo + lob) / 2 + rng.gauss(0, 0.1), hinge=True)
            add_edge(h, rng.choice(clusters[ia]))
            add_edge(h, rng.choice(clusters[ib]))

    # piccoli gruppi separati (2-6 nodi) sparsi per l'Italia
    for _ in range(SMALL_GROUPS):
        lat = rng.uniform(37.5, 46.5)
        lon = rng.uniform(7.5, 15.5)
        size = rng.choice([2, 2, 3, 3, 4, 5, 6])
        grp = [new_node(lat + rng.gauss(0, 0.05), lon + rng.gauss(0, 0.06)) for _ in range(size)]
        for k in range(1, size):
            add_edge(grp[k], grp[rng.randrange(k)])
        if size >= 4:
            add_edge(grp[0], grp[-1])

    # nodi isolati: sentiti di recente ma senza collegamenti noti
    while len(nums) < TOTAL_NEW:
        new_node(rng.uniform(36.8, 46.8), rng.uniform(7.0, 18.0))

    store.commit()
    stats = build_topology(conn, now, 168, SOURCES, (), 1000)["stats"]
    conn.close()
    return {"nodes_added": len(nums), "links_added": len(edges), "topology": stats, **info}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Uso: python tools/topology_bigdemo.py CARTELLA_DATI")
        return 2
    r = build(argv[0])
    t = r["topology"]
    print(f"Creato in {argv[0]}: {r['nodes_added']} nodi e {r['links_added']} collegamenti finti aggiunti")
    print(f"Topologia: {t['nodes']} nodi disegnati, {t['edges']} archi, {t['components']} gruppi, "
          f"{t['cut']} cerniere, {t['hubs']} hub, {t['isolated']} isolati")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
