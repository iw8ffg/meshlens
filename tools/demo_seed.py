"""Crea un database dimostrativo di MeshLens con dati interamente inventati.

Uso:  python tools/demo_seed.py CARTELLA_DATI
Poi:  meshlens run --data-dir CARTELLA_DATI

Nodi, nomi e posizioni sono finti (citta' italiane con scostamenti casuali ma
riproducibili). MQTT punta a 127.0.0.1:1, quindi resta sempre disconnesso.
Comprende anche conversazioni (risposte, reazioni, PKI, non letti), waypoint, metriche,
pacchetti e statistiche orarie, e una copertura prevista calcolata su un terreno sintetico.
"""
import base64
import json
import math
import random
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from meshlens.db import connect
from meshlens.events import TelemetryData
from meshlens.prediction import SiteParams, predict, sensitivity_dbm
from meshlens.settings import save_settings
from meshlens.store import Store

CITIES = {
    "Milano": (45.4642, 9.1900), "Torino": (45.0703, 7.6869), "Genova": (44.4056, 8.9463),
    "Bologna": (44.4949, 11.3426), "Firenze": (43.7696, 11.2558), "Roma": (41.9028, 12.4964),
    "Napoli": (40.8518, 14.2681), "Bari": (41.1171, 16.8719), "Palermo": (38.1157, 13.3615),
    "Cagliari": (39.2238, 9.1217), "Venezia": (45.4408, 12.3155), "Trieste": (45.6495, 13.7768),
}
# nomi inventati: l'unico elenco ammesso nel database dimostrativo
NAMES = [
    "Base Colli", "Nodo Duomo", "Ripetitore Torre", "Tetto Rosso", "Casa Ulivi", "Passo Alto",
    "Faro Nord", "Mulino Verde", "Colle Sereno", "Ponte Vecchio Rx", "Orto Botanico",
    "Rifugio Pino", "Campanile Est", "Piazza Mercato", "Lungomare 1", "Cascina Blu",
    "Torre Civica", "Vetta Piccola", "Porto Antico", "Stazione Meteo", "Giardino Pensile",
    "Cima Bella", "Argine Sud", "Borgo Antico", "Villa Mimosa", "Serra Alta", "Molo Lungo",
    "Collina Dolce", "Castello Rx", "Fienile Radio", "Pieve Nord", "Altopiano 7",
    "Belvedere", "Chiostro", "Ostello Alpino", "Sentiero 12", "Torrione", "Palazzo Rosa",
    "Vigna Bassa", "Capanna Sole",
]
HW = ["HELTEC_V3", "TBEAM", "TLORA_T3_S3", "T_DECK", "RAK4631", "STATION_G2"]
ROLES = ["CLIENT", "CLIENT", "ROUTER", "CLIENT_MUTE", "REPEATER"]
CHAT = [
    "Buongiorno rete, prova radio", "Ricevuto 5/9", "Qui tutto ok, batteria al 90%",
    "Qualcuno in ascolto dalla zona nord?", "Sentito forte e chiaro", "Test di copertura tra poco",
    "Ripetitore acceso, controllate il segnale", "Grazie, ricevuto",
]
DEMO_SEED = 20261121
# conversazioni dimostrative: radio finta "demo", canali 0 (LongFast) e 1 (Escursioni)
RADIO = "demo"
PKI_NODE = 16   # indice in NAMES del nodo con cui c'e' un diretto cifrato (PKI) non letto
DM_NODE = 20    # secondo diretto, gia' letto
WAYPOINTS = [   # (id, indice nodo, nome, descrizione, icona, lat, lon)
    (7001, 3, "Punto di ritrovo", "Ci vediamo qui sabato alle 9, portate le antenne.",
     0x1F4CD, 43.7790, 11.2410),
    (7002, 8, "Rifugio del Pino", "Aperto fino a ottobre, ripetitore sul tetto.",
     0x26FA, 43.7520, 11.2850),
    (7003, 5, "Ripetitore nuovo", "Installato ieri: provate il segnale da sud.",
     0x1F4E1, 43.8015, 11.2105),
]
PRED_SITE = (41.95, 12.50)  # come la prova di copertura: a nord di Roma
# (tipo, portnum, peso nel traffico)
KINDS = [("telemetry", "TELEMETRY_APP", 30), ("position", "POSITION_APP", 22),
         ("nodeinfo", "NODEINFO_APP", 12), ("text", "TEXT_MESSAGE_APP", 10),
         ("neighbors", "NEIGHBORINFO_APP", 8), ("mapreport", "MAP_REPORT_APP", 8),
         ("traceroute", "TRACEROUTE_APP", 4), ("rangetest", "RANGE_TEST_APP", 3)]


class _HillyDem:
    """Terreno sintetico (colline dolci) al posto del download delle altitudini."""

    def sample(self, lats, lons):
        return (150 + 60 * np.sin(lats * 55) * np.cos(lons * 50)
                + 30 * np.sin((lats + lons) * 105) + 15 * np.cos((lats - lons) * 170))


def _msg(store, key, frm, text, ago_min, now, *, to="!ffffffff", ch=0, packet_id=None,
         reply_id=None, emoji=False, pki=False, out=False):
    store.add_message({
        "key": key, "from": f"!{frm:08x}", "to": to,
        "channel": "LongFast" if ch == 0 else "Escursioni", "text": text,
        "time": now - ago_min * 60, "country": "IT", "source": "rf",
        "direction": "out" if out else "in", "radio_id": RADIO, "channel_index": ch,
        "packet_id": packet_id, "reply_id": reply_id, "emoji": emoji, "pki": pki,
        "status": "acked" if out else None})


def _seed_chat(store, nums, now) -> int:
    me = nums[0]
    n = nums.__getitem__
    # canale LongFast: una risposta, reazioni sotto un messaggio, due messaggi non letti
    _msg(store, "c0:1", n(10), "Buongiorno rete, qualcuno in ascolto dalla zona nord?", 190, now,
         packet_id=5001)
    _msg(store, "c0:2", n(11), "Ti sento 5/9 da Colle Sereno", 185, now, packet_id=5002,
         reply_id=5001)
    _msg(store, "c0:3", n(2), "Ripetitore acceso, controllate il segnale", 170, now, packet_id=5003)
    for k, (who, em) in enumerate([(12, "\U0001F44D"), (13, "\U0001F44D"), (14, "\U0001F4E1")]):
        _msg(store, f"c0:r{k}", n(who), em, 168 - k, now, packet_id=5010 + k, reply_id=5003,
             emoji=True)
    _msg(store, "c0:4", me, "Ricevuto, grazie! Provo il Range Test tra mezz'ora", 160, now,
         packet_id=5004, reply_id=5003, out=True)
    _msg(store, "c0:5", n(15), "Sentito forte e chiaro anche dal Passo", 45, now, packet_id=5005)
    _msg(store, "c0:6", n(9), "Test di copertura in corso, restate in ascolto", 12, now,
         packet_id=5006)
    # canale Escursioni (letto)
    _msg(store, "c1:1", n(21), "Sabato giro ad anello, partenza da Pieve Nord alle 8", 600, now,
         ch=1, packet_id=5101)
    _msg(store, "c1:2", me, "Io ci sono, porto il nodo con la batteria nuova", 590, now, ch=1,
         packet_id=5102, out=True)
    # diretto cifrato (PKI), non letto
    peer = n(PKI_NODE)
    mine, theirs = f"!{me:08x}", f"!{peer:08x}"
    _msg(store, "d1:1", me, "Ciao, hai provato il nuovo firmware?", 120, now, to=theirs,
         packet_id=5201, pki=True, out=True)
    _msg(store, "d1:r1", peer, "👍", 29, now, to=mine, packet_id=5210, reply_id=5201,
         emoji=True, pki=True)
    _msg(store, "d1:2", peer, "Si', molto meglio la stabilita' del collegamento", 28, now,
         to=mine, packet_id=5202, reply_id=5201, pki=True)
    _msg(store, "d1:r2", me, "🙌", 20, now, to=theirs, packet_id=5211, reply_id=5202,
         emoji=True, pki=True, out=True)
    _msg(store, "d1:3", peer, "Domani ti mando la configurazione del ripetitore", 8, now,
         to=mine, packet_id=5203, pki=True)
    # terzo diretto, non letto
    third = n(24)
    _msg(store, "d3:1", third, "Ci vediamo domani al ritrovo? Porto io i cavi", 15, now,
         to=mine, packet_id=5401)
    # secondo diretto, letto
    other = n(DM_NODE)
    _msg(store, "d2:1", other, "Sei in zona Belvedere stasera?", 400, now, to=mine, packet_id=5301)
    _msg(store, "d2:2", me, "Forse dopo cena, ti scrivo io", 390, now, to=f"!{other:08x}",
         packet_id=5302, out=True)
    # lo storico conta come non letto, salvo cio' che e' segnato come letto
    store.conn.execute("INSERT OR REPLACE INTO settings(key, value) VALUES('conv_read_baseline', '0')")
    store.mark_read(f"ch:{RADIO}:0", now - 100 * 60)
    store.mark_read(f"ch:{RADIO}:1", now)
    store.mark_read(f"dm:{RADIO}:!{other:08x}", now)
    store.mark_read(f"dm:{RADIO}:{theirs}", now - 100 * 60)
    return peer


def _seed_metrics(store, rng, nums, now) -> None:
    weather = nums[NAMES.index("Stazione Meteo")]
    for k in range(96):
        t = now - (96 - k) * 1800
        day = math.sin((k % 48) / 48 * 2 * math.pi - 2)
        store.add_metrics(weather, t, "environment", {
            "temperature": round(14 + 6 * day + rng.uniform(-0.4, 0.4), 1),
            "relative_humidity": round(62 - 15 * day + rng.uniform(-2, 2)),
            "barometric_pressure": round(1014 + 3 * math.sin(k / 30) + rng.uniform(-0.3, 0.3), 1)})


def _summary(kind, rng, nums, who, lat, lon) -> dict:
    if kind == "telemetry":
        return {"battery_level": rng.randint(30, 100), "voltage": round(rng.uniform(3.6, 4.1), 2),
                "channel_utilization": round(rng.uniform(1, 18), 1),
                "air_util_tx": round(rng.uniform(0, 3), 1), "uptime_seconds": rng.randint(600, 900000),
                "variant": "device", "metrics": {}}
    if kind == "position":
        return {"lat": round(lat, 5), "lon": round(lon, 5), "alt": rng.randint(20, 900),
                "precision_bits": 32, "time": None}
    if kind == "nodeinfo":
        return {"long_name": NAMES[who], "short_name": f"D{who:03d}"[:4],
                "hw_model": rng.choice(HW), "role": rng.choice(ROLES), "public_key": None}
    if kind == "text":
        return {"text": rng.choice(CHAT), "reply_id": None, "emoji": False}
    if kind == "neighbors":
        return {"neighbors": [{"node": f"!{nums[(who + d) % len(nums)]:08x}",
                               "snr": round(rng.uniform(-12, 8), 1)} for d in (1, 2, 3)]}
    if kind == "mapreport":
        return {"long_name": NAMES[who], "firmware": "2.7.11", "region": "EU_868",
                "lat": round(lat, 5), "lon": round(lon, 5),
                "num_online_local_nodes": rng.randint(2, 20)}
    if kind == "traceroute":
        return {"route": [f"!{nums[(who + 1) % len(nums)]:08x}"],
                "snr_towards": [round(rng.uniform(-8, 8), 1)]}
    return {"seq": rng.randint(1, 500)}


def _seed_packets(store, rng, nums, now) -> None:
    """Aggregati orari (48 ore) per le statistiche e pacchetti recenti per l'ispettore."""
    kinds = [k for k, _, _ in KINDS]
    weights = [w for _, _, w in KINDS]
    port = {k: p for k, p, _ in KINDS}
    hour0 = int(now // 3600) * 3600
    node_acc: dict[tuple, list] = {}
    for h in range(48, -1, -1):
        t = hour0 - h * 3600
        day = 0.55 + 0.45 * math.sin(((t // 3600) % 24 - 6) / 24 * 2 * math.pi)
        for kind, w in zip(kinds, weights):
            for source, share in (("rf", 0.7), ("mqtt", 2.0)):
                p = int(w * day * share * rng.uniform(2.5, 4))
                if p:
                    store.upsert_stats_hourly([(t, source, kind, p, p * rng.randint(1, 3))])
        for i, num in enumerate(nums):
            for source in ("rf", "mqtt"):
                if source == "rf" and i >= 12:
                    continue
                if rng.random() < 0.25 + 0.6 * day * (0.9 if i < 20 else 0.4):
                    pk = max(1, int(rng.uniform(1, 9) * (45 - i) / 22))
                    snr = round(rng.uniform(-14, 9), 1)
                    acc = node_acc.setdefault((t, num, source), [0, 0.0, 0, None])
                    acc[0] += pk
                    acc[1] += snr * pk
                    acc[2] += pk
                    acc[3] = snr if acc[3] is None else max(acc[3], snr)
    store.upsert_node_hourly([(*k, *v) for k, v in node_acc.items()])
    # pacchetti singoli: circa 220 nell'ultima ora, piu' radi nelle ore precedenti
    city_list = list(CITIES.values())
    rows = []
    for k in range(470):
        age = rng.uniform(0, 3500) if k < 220 else rng.uniform(3600, 5 * 3600)
        kind = rng.choices(kinds, weights)[0]
        who = rng.randrange(len(nums))
        clat, clon = city_list[who % len(city_list)]
        source = rng.choice(["mqtt", "mqtt", "rf"])
        hs = rng.choice([3, 3, 3, 5, 7])
        hops = rng.randint(0, min(3, hs))
        status, shown = "ok", kind
        if rng.random() < 0.08:
            status, shown = rng.choice(["encrypted", "undecodable"]), None
        raw = rng.randbytes(rng.randint(16, 90))
        t = now - age
        rec = [{"source": source, "broker": "demo" if source == "mqtt" else None,
                "radio_id": RADIO if source == "rf" else None,
                "gateway": f"!{nums[rng.randrange(6)]:08x}", "snr": round(rng.uniform(-14, 9), 1),
                "rssi": rng.randint(-125, -60), "hops": hops, "relay_node": nums[who] & 0xFF,
                "time": t}]
        copies = rng.choice([1, 1, 1, 2, 3])
        for _ in range(copies - 1):
            rec.append({**rec[0], "gateway": f"!{nums[rng.randrange(6)]:08x}",
                        "snr": round(rng.uniform(-14, 9), 1), "time": t + rng.uniform(0.1, 3)})
        summary = (json.dumps(_summary(shown, rng, nums, who, clat + rng.uniform(-.05, .05),
                                       clon + rng.uniform(-.05, .05))) if shown else None)
        rows.append({
            "time": t, "from_num": nums[who], "to_num": 0xFFFFFFFF,
            "packet_id": 0x3A000000 + k * 7919, "source": source, "broker": rec[0]["broker"],
            "radio_id": rec[0]["radio_id"], "channel": "LongFast",
            "portnum": port[shown] if shown else None, "kind": shown, "status": status,
            "snr": rec[0]["snr"], "rssi": rec[0]["rssi"], "hops": hops, "hop_start": hs,
            "hop_limit": hs - hops, "relay_node": rec[0]["relay_node"],
            "gateway": rec[0]["gateway"], "copies": copies, "receptions": json.dumps(rec),
            "raw": raw, "size": len(raw), "summary": summary})
    rows.sort(key=lambda r: r["time"])
    store.insert_packets(rows)


def _seed_prediction(out_dir: Path, rng, now) -> None:
    """Copertura prevista conclusa, calcolata sul terreno sintetico (nessun download)."""
    sp = SiteParams(lat=PRED_SITE[0], lon=PRED_SITE[1], height_m=25, radius_km=15)
    grid = predict(sp, _HillyDem(), lambda: ThreadPoolExecutor(4), lambda done, total: None,
                   threading.Event())
    w, _s, e, _n = grid.bbox
    cell_m = math.radians((e - w) / grid.width) * 6_371_000.0 * math.cos(math.radians(sp.lat))
    covered = int(np.count_nonzero((grid.values != -128) & (grid.values >= 0)))
    pid = f"p{int(now) - 1800}-{rng.getrandbits(24):06x}"
    meta = {"id": pid, "name": "Base Colli, antenna sul tetto", "created": now - 1800,
            "params": {k: getattr(sp, k) for k in sp.__dataclass_fields__},
            "sensitivity_dbm": sensitivity_dbm(sp.preset), "eirp_dbm": sp.eirp_dbm,
            "bbox": grid.bbox, "width": grid.width, "height": grid.height,
            "covered_km2": round(covered * cell_m * cell_m / 1e6, 1)}
    doc = {**meta, "nodata": -128,
           "values": base64.b64encode(grid.values.astype(np.int8).tobytes()).decode("ascii")}
    d = out_dir / "predictions"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{pid}.json").write_text(json.dumps(doc), encoding="utf-8")
    (d / f"{pid}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


def build(out_dir: Path | str, now: float | None = None) -> dict:
    out_dir = Path(out_dir)
    now = time.time() if now is None else now
    rng = random.Random(DEMO_SEED)
    conn = connect(out_dir / "meshlens.db")
    store = Store(conn)
    city_list = list(CITIES.items())
    nums = []
    for i, name in enumerate(NAMES):
        city, (clat, clon) = city_list[i % len(city_list)]
        num = 0xD0000000 + i * 0x101
        nums.append(num)
        mine = i < 6
        heard = now - rng.choice([60, 300, 1800, 3600 * 3, 3600 * 30]) * rng.uniform(0.5, 1.5)
        store.upsert_node({
            "num": num, "long_name": name, "short_name": f"D{i:03d}"[:4],
            "hw_model": rng.choice(HW), "role": ROLES[i % len(ROLES)], "firmware": "2.7.11",
            "lat": clat + rng.uniform(-0.08, 0.08), "lon": clon + rng.uniform(-0.08, 0.08),
            "precision_bits": 32, "position_source": "rf" if mine else "mqtt",
            "position_time": heard, "country": "IT", "last_heard": heard,
            "sources": ["rf", "mqtt"] if mine else ["mqtt"],
            "battery": rng.randint(15, 100), "voltage": round(rng.uniform(3.5, 4.15), 2),
            "channel_util": round(rng.uniform(1, 25), 1), "air_util_tx": round(rng.uniform(0, 4), 1),
            "mqtt_gateways": rng.randint(1, 4), "last_snr": round(rng.uniform(-15, 9), 1),
            "hops": rng.randint(0, 3),
        }, is_mine=mine)
        # telemetria: 48 ore, un campione ogni 30 minuti, batteria che scende e risale
        level = rng.randint(60, 100)
        for k in range(96):
            t = now - (96 - k) * 1800
            level = max(10, min(100, level + rng.randint(-3, 2) + (6 if k % 40 == 39 else 0)))
            store.add_telemetry(num, t, TelemetryData(
                battery_level=level, voltage=round(3.3 + level / 100 * 0.85, 2),
                channel_utilization=round(rng.uniform(1, 20), 1),
                air_util_tx=round(rng.uniform(0, 3), 1), uptime_seconds=k * 1800))
    # collegamenti tra nodi vicini
    for i in range(0, 30, 2):
        store.upsert_link(nums[i], nums[i + 1], "neighbor", round(rng.uniform(-12, 8), 1),
                          now - rng.randint(60, 7200))
    # messaggi di chat
    for k, text in enumerate(CHAT):
        frm = nums[k % len(nums)]
        store.add_message({"key": f"demo:{k}", "from": f"!{frm:08x}", "to": "!ffffffff",
                           "channel": "LongFast", "text": text, "time": now - (len(CHAT) - k) * 600,
                           "country": "IT", "source": "mqtt"})
    # prova di copertura conclusa, a nord di Roma (percorso inventato)
    base = nums[5]
    sid = store.create_session(
        name="Prova dimostrativa", radio_id="demo", mobile_num=nums[6], mode="range_test",
        channel_index=0, interval_s=30, started=now - 7200, ended=now - 3600,
        end_reason="manual", base_lat=41.95, base_lon=12.50, notes="Dati finti")
    for k in range(60):
        lat, lon = 41.95 + k * 0.0012, 12.50 + k * 0.0016 + rng.uniform(-0.0004, 0.0004)
        t = now - 7200 + k * 60
        store.add_track(sid, t, lat, lon, 32)
        if k % 7 != 3:  # qualche punto mancante
            store.add_point(sid, 0, k, t, round(8 - k * 0.3 + rng.uniform(-2, 2), 1),
                            -70 - k, rng.randint(0, 1), lat, lon, 32)
    # conversazioni, waypoint, metriche ambientali, pacchetti e statistiche
    peer = _seed_chat(store, nums, now)
    for wid, who, name, desc, icon, lat, lon in WAYPOINTS:
        store.upsert_waypoint({
            "id": wid, "from_num": nums[who], "lat": lat, "lon": lon, "name": name,
            "description": desc, "icon": icon, "expire": int(now) + 5 * 86400, "locked_to": 0,
            "time": now - rng.randint(3600, 86400), "source": "rf", "radio_id": RADIO,
            "channel": "LongFast", "country": "IT"})
    _seed_metrics(store, rng, nums, now)
    _seed_packets(store, rng, nums, now)
    store.commit()
    _seed_prediction(out_dir, rng, now)
    # MQTT resta disconnesso: broker locale su una porta chiusa
    save_settings(conn, {"mqtt": {"host": "127.0.0.1", "port": 1, "topics": []},
                         "saved_countries": ["IT"], "packet_log_mode": "archived"})
    conn.close()
    return {"nodes": len(NAMES), "session": sid, "base": base, "pki_peer": peer}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("Uso: python tools/demo_seed.py CARTELLA_DATI")
        return 2
    info = build(argv[0])
    print(f"Creato database dimostrativo con {info['nodes']} nodi in {argv[0]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
