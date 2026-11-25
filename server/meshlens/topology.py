"""Topologia della rete (E8): grafo non orientato dalla tabella `links`, con analisi dei punti di
articolazione (nodi cerniera), hub e nodi isolati.

Algoritmo (tutto in `analyze`, O(V+E), iterativo, nessuna ricorsione):
  1. grafo semplice: adiacenza ordinata per numero del nodo, self-loop scartati, archi doppi fusi;
  2. per ogni radice non visitata (ordine crescente) DFS con pila esplicita; al primo ingresso
     `disc = low = timer++`, `sz = 1`;
  3. vicino gia' visitato (e non il padre): `low[v] = min(low[v], disc[w])`;
  4. al ritorno da un figlio `w`: `low[v] = min(low[v], low[w])`, `sz[v] += sz[w]`; se
     `low[w] >= disc[v]` il sotto-albero di `w` si stacca togliendo `v`: `sz[w]` e' un "pezzo";
  5. fine della componente: i pezzi di `v` sono quelli staccati piu' (se > 0) il resto
     `comp - 1 - sum(pezzi)` (la parte con la radice). `v` e' cerniera se i pezzi sono almeno 2;
     `impact = comp - 1 - max(pezzi)` = nodi che perdono il collegamento col pezzo piu' grande;
  6. componenti numerate per dimensione decrescente (a parita': nodo piu' piccolo);
  7. hub: grado >= max(4, percentile 90 per rango dei gradi positivi); isolati: grado 0.
Statistiche e cerniere valgono sempre per il grafo intero filtrato: solo l'uscita e' troncata.
"""
import sqlite3
from dataclasses import dataclass
from typing import Iterable

from .events import node_id

SOURCES: tuple[str, ...] = ("neighborinfo", "traceroute", "mqtt_gateway", "rf_direct")
HUB_MIN_DEGREE = 4
DEFAULT_LIMIT = 400
ISOLATED_LIMIT = 200


@dataclass(frozen=True)
class Analysis:
    degree: dict[int, int]
    component: dict[int, int]      # numero componente (0 = la piu' grande), solo nodi con grado > 0
    components: list[int]          # dimensioni per numero componente (decrescente)
    cut: dict[int, int]            # punto di articolazione -> impact
    hubs: frozenset[int]


def _adjacency(nodes: Iterable[int], edges: Iterable[tuple[int, int]]) -> dict[int, list[int]]:
    universe = set(nodes)
    adj: dict[int, set[int]] = {n: set() for n in universe}
    for u, v in edges:
        if u == v or u not in universe or v not in universe:
            continue
        adj[u].add(v)
        adj[v].add(u)
    return {n: sorted(s) for n, s in adj.items()}


def _tarjan(adj: dict[int, list[int]]) -> tuple[list[tuple[int, list[int]]], dict[int, int]]:
    """Componenti (radice, nodi) e punti di articolazione con impatto."""
    disc: dict[int, int] = {}
    low: dict[int, int] = {}
    size: dict[int, int] = {}
    parent: dict[int, int | None] = {}
    nxt: dict[int, int] = {}
    sep: dict[int, list[int]] = {}
    sep_sum: dict[int, int] = {}
    timer = 0
    comps: list[tuple[int, list[int]]] = []
    cut: dict[int, int] = {}
    for root in sorted(n for n, a in adj.items() if a):
        if root in disc:
            continue
        members = [root]
        disc[root] = low[root] = timer
        timer += 1
        size[root], parent[root], nxt[root] = 1, None, 0
        sep[root], sep_sum[root] = [], 0
        stack = [root]
        while stack:
            v = stack[-1]
            neigh = adj[v]
            if nxt[v] < len(neigh):
                w = neigh[nxt[v]]
                nxt[v] += 1
                if w == parent[v]:
                    continue
                if w in disc:
                    if disc[w] < low[v]:
                        low[v] = disc[w]
                else:
                    disc[w] = low[w] = timer
                    timer += 1
                    size[w], parent[w], nxt[w] = 1, v, 0
                    sep[w], sep_sum[w] = [], 0
                    members.append(w)
                    stack.append(w)
            else:
                stack.pop()
                p = parent[v]
                if p is not None:
                    if low[v] < low[p]:
                        low[p] = low[v]
                    size[p] += size[v]
                    if low[v] >= disc[p]:
                        sep[p].append(size[v])
                        sep_sum[p] += size[v]
        comp_size = size[root]
        for v in members:
            pieces = list(sep[v])
            rem = comp_size - 1 - sep_sum[v]
            if rem > 0:
                pieces.append(rem)
            if len(pieces) >= 2:
                cut[v] = comp_size - 1 - max(pieces)
        comps.append((root, members))
    return comps, cut


def _hubs(degree: dict[int, int]) -> frozenset[int]:
    d = sorted(x for x in degree.values() if x > 0)
    if not d:
        return frozenset()
    rank = -(-9 * len(d) // 10)  # ceil(0,9 * n) in aritmetica intera
    thr = max(HUB_MIN_DEGREE, d[rank - 1])
    return frozenset(n for n, x in degree.items() if x >= thr)


def analyze(nodes: Iterable[int], edges: Iterable[tuple[int, int]]) -> Analysis:
    adj = _adjacency(nodes, edges)
    degree = {n: len(a) for n, a in adj.items()}
    comps, cut = _tarjan(adj)
    comps.sort(key=lambda c: (-len(c[1]), min(c[1])))
    component = {n: i for i, (_, members) in enumerate(comps) for n in members}
    return Analysis(degree=degree, component=component,
                    components=[len(m) for _, m in comps], cut=cut, hubs=_hubs(degree))


# ---- costruzione dal database ----

def _country_ok(country: str | None, countries: set[str]) -> bool:
    if not countries:
        return True
    key = "none" if not country else str(country).upper()
    return key in countries


def _collect(conn: sqlite3.Connection, since: float, sources: tuple[str, ...],
             countries: set[str]):
    srcs = [s for s in sources if s in SOURCES]  # i nomi vengono solo dalla lista bianca
    rows = conn.execute(
        "SELECT from_num, to_num, source, snr, time FROM links WHERE time >= ? AND source IN ("
        + ",".join("?" * len(srcs)) + ")", (since, *srcs)).fetchall() if srcs else []
    info: dict[int, dict] = {}
    for r in conn.execute(
            "SELECT num, long_name, short_name, role, lat, lon, is_mine, last_heard, country, "
            "COALESCE(is_ignored, 0) FROM nodes"):
        info[r[0]] = {"name": r[1] or r[2] or node_id(r[0]), "role": r[3], "lat": r[4],
                      "lon": r[5], "is_mine": bool(r[6]), "last_heard": r[7], "country": r[8],
                      "ignored": bool(r[9])}

    def allowed(num: int) -> bool:
        n = info.get(num)
        if n is None:
            return _country_ok(None, countries)  # segnaposto: paese "none"
        return not n["ignored"] and (n["is_mine"] or _country_ok(n["country"], countries))

    merged: dict[tuple[int, int], dict] = {}
    for a, b, source, snr, t in rows:
        if a is None or b is None or a == b or not allowed(a) or not allowed(b):
            continue
        key = (a, b) if a < b else (b, a)
        e = merged.setdefault(key, {"sources": set(), "snr": None, "time": 0.0})
        e["sources"].add(source)
        if snr is not None and (e["snr"] is None or snr > e["snr"]):
            e["snr"] = snr
        if t is not None and t > e["time"]:
            e["time"] = t
    universe: dict[int, dict | None] = {}
    for num, n in info.items():
        if allowed(num) and n["last_heard"] is not None and n["last_heard"] >= since:
            universe[num] = n
    for a, b in merged:
        for x in (a, b):
            universe.setdefault(x, info.get(x))
    return universe, merged


def _node_out(num: int, n: dict | None, an: Analysis) -> dict:
    return {"id": node_id(num), "name": n["name"] if n else node_id(num),
            "role": n["role"] if n else None, "lat": n["lat"] if n else None,
            "lon": n["lon"] if n else None, "is_mine": bool(n and n["is_mine"]),
            "last_heard": n["last_heard"] if n else None, "degree": an.degree.get(num, 0),
            "component": an.component.get(num, -1), "cut": num in an.cut,
            "hub": num in an.hubs, "impact": an.cut.get(num, 0)}


def build_topology(conn: sqlite3.Connection, now: float, hours: int,
                   sources: tuple[str, ...] = SOURCES, countries: tuple[str, ...] = (),
                   limit: int = DEFAULT_LIMIT, main_only: bool = False) -> dict:
    since = now - hours * 3600
    wanted = {"none" if str(c).lower() == "none" else str(c).upper() for c in countries}
    universe, merged = _collect(conn, since, tuple(sources), wanted)
    an = analyze(universe.keys(), merged.keys())

    drawn = [n for n in universe if an.degree.get(n, 0) > 0]
    if main_only:  # solo il gruppo principale (componente 0): il limite si riempie da li'
        drawn = [n for n in drawn if an.component.get(n) == 0]
    # priorita' di uscita: cerniere per impatto decrescente, poi hub, poi grado, poi numero
    ranked = sorted(drawn, key=lambda n: (n not in an.cut, -an.cut.get(n, 0),
                                          n not in an.hubs, -an.degree[n], n))
    kept = set(ranked[:limit])
    truncated = len(kept) < len(drawn)
    out_nodes = sorted(kept, key=lambda n: (-an.degree[n], n))

    edges_out = []
    by_source = {s: 0 for s in SOURCES}
    for (a, b), e in sorted(merged.items()):
        srcs = [s for s in SOURCES if s in e["sources"]]
        for s in srcs:
            by_source[s] += 1
        if a in kept and b in kept:
            edges_out.append({"a": node_id(a), "b": node_id(b), "sources": srcs,
                              "snr": e["snr"], "time": e["time"]})

    isolated_all = sorted((n for n, info in universe.items()
                           if info is not None and an.degree.get(n, 0) == 0),
                          key=lambda n: (-(universe[n]["last_heard"] or 0), n))
    isolated = [{"id": node_id(n), "name": universe[n]["name"], "role": universe[n]["role"],
                 "last_heard": universe[n]["last_heard"], "is_mine": universe[n]["is_mine"]}
                for n in isolated_all[:ISOLATED_LIMIT]]
    return {
        "since": since, "hours": hours, "sources": [s for s in SOURCES if s in sources],
        "nodes": [_node_out(n, universe[n], an) for n in out_nodes],
        "edges": edges_out, "isolated": isolated,
        "components": [{"id": i, "size": s} for i, s in enumerate(an.components)],
        "stats": {"nodes": len(drawn), "edges": len(merged), "components": len(an.components),
                  "isolated": len(isolated_all), "cut": len(an.cut), "hubs": len(an.hubs),
                  "by_source": by_source},
        "truncated": truncated,
    }
