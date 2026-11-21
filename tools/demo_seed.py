"""Crea un database dimostrativo di MeshLens con dati interamente inventati.

Uso:  python tools/demo_seed.py CARTELLA_DATI
Poi:  meshlens run --data-dir CARTELLA_DATI

Nodi, nomi e posizioni sono finti (citta' italiane con scostamenti casuali ma
riproducibili). MQTT punta a 127.0.0.1:1, quindi resta sempre disconnesso.
"""
import random
import sys
import time
from pathlib import Path

from meshlens.db import connect
from meshlens.events import TelemetryData
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
    store.commit()
    # MQTT resta disconnesso: broker locale su una porta chiusa
    save_settings(conn, {"mqtt": {"host": "127.0.0.1", "port": 1, "topics": []},
                         "saved_countries": ["IT"]})
    conn.close()
    return {"nodes": len(NAMES), "session": sid, "base": base}


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
