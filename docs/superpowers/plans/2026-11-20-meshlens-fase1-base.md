# MeshLens — Fase 1 (Base) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Webapp locale che riceve il traffico Meshtastic dal broker MQTT pubblico, lo decodifica, ricava la nazione dei nodi e lo mostra su una mappa (online) con elenco nodi, feed messaggi, filtro per nazione e accesso con PIN, utilizzabile da PC e telefono.

**Architecture:** Server Python (FastAPI + uvicorn) con un connettore MQTT (paho, thread proprio) che passa i pacchetti al loop asyncio; una pipeline `decode → dedup → nazione → stato live (memoria) → SQLite (solo nazioni scelte)`; API REST + WebSocket con aggiornamenti a lotti. Interfaccia Svelte 5 + MapLibre compilata in statici serviti dal server. Le fasi 2–6 avranno piani separati: questo piano predispone le interfacce (`source`, `MeshEvent`) che le radio useranno.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, paho-mqtt 2.x, meshtastic 2.7.11 (solo protobuf in questa fase), cryptography, shapely 2.x, argon2-cffi, sqlite3 (stdlib), pytest + pytest-asyncio + httpx; Node 24, Svelte 5, Vite, TypeScript, maplibre-gl, vitest.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md` (studio: `docs/studio-iniziale.md`)

## Fatti verificati il 2026-11-20 (non ri-derivare)
- `meshtastic` 2.7.11: protobuf in `meshtastic.protobuf` (`mqtt_pb2.ServiceEnvelope{packet,channel_id,gateway_id}`, `mesh_pb2.MeshPacket`, `mesh_pb2.Data`, `mesh_pb2.Position` con `precision_bits`, `mesh_pb2.User`, `mqtt_pb2.MapReport`, `telemetry_pb2.Telemetry.device_metrics{battery_level,voltage,channel_utilization,air_util_tx,uptime_seconds}`). La libreria **non** offre funzioni di decifratura MQTT.
- PortNum: TEXT_MESSAGE_APP=1, POSITION_APP=3, NODEINFO_APP=4, RANGE_TEST_APP=66, TELEMETRY_APP=67, TRACEROUTE_APP=70, NEIGHBORINFO_APP=71, MAP_REPORT_APP=73.
- Decifratura verificata su traffico reale: AES-128-CTR, chiave di default `d4f1bb3a20290759f0bcffabcf4e6901`, nonce = `struct.pack("<QI", packet.id, packet.from) + b"\0"*4`.
- Broker `mqtt.meshtastic.org:1883`, utente `meshdev` / `large4cats`: iscrizione a `msh/EU_868/#` accettata (QoS 0). Volume misurato: **~110 messaggi/s**. Esistono sotto-topic per paese non standard (`msh/EU_868/IT/...`, `/SE/`, `/DE/`...), quindi la nazione si ricava dalle coordinate. Arrivano anche payload non protobuf (topic `/json/`, `/stat/`): da ignorare. Pacchetti con `channel_id == "PKI"` o chiavi sconosciute non sono decifrabili: si contano e si scartano. Alcuni pacchetti arrivano già `decoded` (es. map report).

## Global Constraints
- Python ≥ 3.12, < 3.15; Windows 11; avvio con `start.bat`.
- Porta HTTP `8686`. Ascolto su `127.0.0.1` per default; `0.0.0.0` solo se l'impostazione `lan_access` è `true` (letta all'avvio).
- MeshLens **non pubblica mai** sui broker MQTT: solo `subscribe`.
- Default MQTT: host `mqtt.meshtastic.org`, porta `1883`, utente `meshdev`, password `large4cats`, topic `["msh/EU_868/#"]`, chiavi extra `[]`.
- Storico: si salvano solo le nazioni in `saved_countries` (default `["IT"]`). Retention default: messaggi 90 giorni, posizioni 90 giorni, telemetria 365 giorni. Limite spazio default 2048 MB.
- Tolleranza nazione: 25 km.
- Ultimo contatto: verde < 2 h, giallo < 24 h, grigio oltre.
- Id nodo in formato `!` + 8 cifre esadecimali minuscole (es. `!a1b2c3d4`).
- Dati in `data/` nella cartella del progetto (ignorata da git): `data/meshlens.db`.
- Interfaccia in italiano. Mai `{@html}` in Svelte (testi dei messaggi sono input non fidato).
- Mappa online: stile `https://tiles.openfreemap.org/styles/liberty` (le mappe offline sono nella fase 6).

## Review Focus
1. Payload MQTT malformati (JSON, `/stat/`, protobuf troncato, chiave sbagliata, PKI): contati e ignorati, il connettore non si ferma mai → test in Task 2.
2. Posizione assente o `latitude_i == 0 and longitude_i == 0`: il nodo resta senza posizione e senza nazione, non finisce "nel Golfo di Guinea" né nella nazione più vicina → test in Task 4 e Task 6.
3. Nessuna connessione internet all'avvio o broker che cade: l'app parte comunque, lo stato MQTT risulta "disconnesso" e si ricollega da sola → test in Task 9.
4. Messaggi con HTML/emoji/testo lunghissimo: mostrati come testo, mai interpretati → controllo in Task 12.
5. Accesso dalla LAN senza PIN o con tentativi ripetuti: API → 401, WebSocket chiuso, blocco dopo 5 errori → test in Task 7 e Task 8.

---

## File Structure

```
meshlens/
  pyproject.toml            dipendenze, pytest, entry point `meshlens`
  start.bat                 crea venv se manca, installa, avvia, apre il browser
  .gitignore                data/, .venv/, web/node_modules/, web/dist/, __pycache__/
  tools/build_countries.py  genera server/meshlens/data/countries.geojson da Natural Earth
  server/meshlens/
    __init__.py             __version__ = "0.1.0"
    __main__.py             CLI: `run`, `reset-pin`
    crypto.py               chiavi PSK e decifratura AES-CTR
    events.py               dataclass MeshEvent e sottotipi
    mqtt_decode.py          ServiceEnvelope → MeshEvent | None (+ contatori)
    dedup.py                deduplica (from, packet_id)
    geo.py                  CountryLocator
    db.py                   connessione SQLite + schema
    store.py                scritture/letture/pulizia su SQLite
    settings.py             default + lettura/scrittura impostazioni nel DB
    live.py                 LiveState: nodi in memoria, ring buffer messaggi, nodi modificati
    ingest.py               Ingestor: pipeline per qualsiasi fonte
    auth.py                 PIN, sessioni, blocco tentativi
    bus.py                  fan-out eventi ai client WebSocket
    api.py                  create_app(): REST + WebSocket + statici
    mqtt_client.py          MqttConnector
    app.py                  wiring: avvio componenti, task periodici
    data/countries.geojson  confini (generato, committato)
  server/tests/
    conftest.py, helpers.py (costruzione envelope sintetici), test_*.py
  web/
    package.json, vite.config.ts, tsconfig.json, index.html
    src/main.ts, src/App.svelte
    src/lib/api.ts, ws.ts, types.ts, filters.ts, format.ts, stores.svelte.ts
    src/lib/filters.test.ts, format.test.ts
    src/components/Login.svelte, MapView.svelte, NodeList.svelte, NodeDetail.svelte,
                   Filters.svelte, MessageFeed.svelte, Settings.svelte, StatusBar.svelte
```

## Contratti condivisi

**`MeshEvent`** (`server/meshlens/events.py`): dataclass con campi comuni
`source: str` ("mqtt" in questa fase; "rf" in fase 2), `from_node: int`, `to_node: int`, `packet_id: int`, `channel: str` (channel_id MQTT o nome canale), `rx_time: float` (epoch s, ora di ricezione locale), `snr: float | None`, `rssi: int | None`, `hops: int | None` (`hop_start - hop_limit` se `hop_start > 0`), `gateway_id: str | None`, `radio_id: str | None` (None per MQTT), più `kind` e `payload`:
- `kind="position"`, payload `PositionData(lat: float, lon: float, alt: int | None, precision_bits: int | None, time: int | None)`
- `kind="nodeinfo"`, payload `NodeInfoData(long_name, short_name, hw_model: str, role: str, public_key: bytes | None)`
- `kind="text"`, payload `TextData(text: str)`
- `kind="telemetry"`, payload `TelemetryData(battery_level: int | None, voltage: float | None, channel_utilization: float | None, air_util_tx: float | None, uptime_seconds: int | None)`
- `kind="mapreport"`, payload `MapReportData(long_name, short_name, hw_model, role, firmware_version, region, modem_preset, lat, lon, precision_bits, num_online_local_nodes)` — `lat/lon` None se zero

`hw_model`, `role`, `region`, `modem_preset` sono i nomi enum (es. `"HELTEC_V3"`, `"CLIENT"`). Funzione `node_id(num: int) -> str` restituisce `f"!{num:08x}"`.

**JSON nodo** (API e WebSocket):
```json
{"id":"!a1b2c3d4","num":2712847316,"long_name":"…","short_name":"…","hw_model":"HELTEC_V3","role":"CLIENT",
 "firmware":null,"lat":45.46,"lon":9.19,"precision_bits":13,"position_source":"mqtt","position_time":1763660000,
 "country":"IT","last_heard":1763660123,"sources":["mqtt"],"battery":87,"voltage":4.01,
 "channel_util":12.5,"air_util_tx":1.2,"mqtt_gateways":3,"last_snr":-7.5,"hops":2}
```
**JSON messaggio**: `{"key":"2712847316:123456","from":"!a1b2c3d4","from_name":"…","to":"!ffffffff","channel":"LongFast","text":"…","time":1763660123,"country":"IT","source":"mqtt"}`

**WebSocket `/ws`** (server → client, testo JSON):
`{"type":"nodes","nodes":[<nodo>…]}` ogni 2 s solo con i nodi modificati; `{"type":"message","message":<messaggio>}`; `{"type":"status","mqtt":{"connected":bool,"msgs_per_s":float,"undecodable":int}}` ogni 5 s.

---

### Task 1: Scaffold del progetto e decifratura

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `server/meshlens/__init__.py`, `server/meshlens/crypto.py`
- Test: `server/tests/test_crypto.py`

**Interfaces:**
- Produces: `DEFAULT_KEY: bytes` (16 byte sopra); `expand_psk(b64: str) -> bytes` (base64 → chiave; 1 byte `0x01` → DEFAULT_KEY, `0x02..0x0a` → DEFAULT_KEY con ultimo byte incrementato di (n-1), `0x00` o vuoto → `b""` = nessuna cifratura; 16 o 32 byte → così come sono; altre lunghezze → `ValueError`); `make_nonce(packet_id: int, from_node: int) -> bytes`; `decrypt(key: bytes, packet_id: int, from_node: int, data: bytes) -> bytes`.

- [ ] **Step 1: Creare `pyproject.toml`** con `[project] name="meshlens"`, `requires-python=">=3.12,<3.15"`, dipendenze `fastapi`, `uvicorn[standard]`, `paho-mqtt>=2.1`, `meshtastic==2.7.11`, `cryptography`, `shapely>=2.0`, `argon2-cffi`; extra `dev = ["pytest", "pytest-asyncio", "httpx"]`; `[project.scripts] meshlens = "meshlens.__main__:main"`; package in `server/` (setuptools `package-dir = {"" = "server"}`, includere `meshlens/data/*.geojson`); `[tool.pytest.ini_options] testpaths=["server/tests"]`, `asyncio_mode="auto"`. `.gitignore` come da File Structure.

- [ ] **Step 2: Creare venv e installare**

Run: `python -m venv .venv; .venv\Scripts\python -m pip install -e ".[dev]"`
Expected: installazione completata senza errori.

- [ ] **Step 3: Scrivere i test**

```python
from meshlens.crypto import DEFAULT_KEY, expand_psk, make_nonce, decrypt
import pytest

def test_expand_default_psk():
    assert expand_psk("AQ==") == bytes.fromhex("d4f1bb3a20290759f0bcffabcf4e6901")

def test_expand_simple_psk_variant():
    assert expand_psk("Ag==")[-1] == DEFAULT_KEY[-1] + 1

def test_expand_none_and_full_and_invalid():
    assert expand_psk("AA==") == b""
    k = bytes(range(32)); import base64
    assert expand_psk(base64.b64encode(k).decode()) == k
    with pytest.raises(ValueError):
        expand_psk(base64.b64encode(b"abc").decode())

def test_nonce_layout():
    assert make_nonce(0x01020304, 0xa1b2c3d4) == bytes.fromhex("0403020100000000d4c3b2a100000000")

def test_decrypt_roundtrip_is_symmetric():
    plain = b"\x08\x01\x12\x05ciao!"
    enc = decrypt(DEFAULT_KEY, 42, 0xa1b2c3d4, plain)
    assert enc != plain
    assert decrypt(DEFAULT_KEY, 42, 0xa1b2c3d4, enc) == plain
```

- [ ] **Step 4: Verificare che falliscano** — Run: `.venv\Scripts\pytest server/tests/test_crypto.py -v` · Expected: FAIL (modulo mancante).

- [ ] **Step 5: Implementare `crypto.py`** con `cryptography` (`Cipher(algorithms.AES(key), modes.CTR(nonce))`).

- [ ] **Step 6: Verificare** — stesso comando · Expected: 5 passed.

- [ ] **Step 7: Commit** — `git add pyproject.toml .gitignore server && git commit -m "feat: scaffold progetto e decifratura AES-CTR"`

---

### Task 2: Eventi e decodifica degli envelope MQTT

**Files:**
- Create: `server/meshlens/events.py`, `server/meshlens/mqtt_decode.py`, `server/tests/helpers.py`
- Test: `server/tests/test_mqtt_decode.py`

**Interfaces:**
- Consumes: `crypto.decrypt`, `crypto.expand_psk`, `crypto.DEFAULT_KEY`.
- Produces: dataclass del contratto `MeshEvent` + `node_id()` in `events.py`; in `mqtt_decode.py` la classe `EnvelopeDecoder(keys: list[bytes])` con `decode(topic: str, payload: bytes, now: float) -> MeshEvent | None` e attributo `stats: collections.Counter` (chiavi: `"ok"`, `"not_protobuf"`, `"json_topic"`, `"undecodable"`, `"unsupported_port"`, `"empty"`). Le chiavi si provano in ordine; la prima che produce un `Data` valido con `portnum != 0` vince. `helpers.make_envelope(portnum: int, payload_msg, from_node=0xa1b2c3d4, packet_id=1, channel_id="LongFast", gateway="!00000001", key=DEFAULT_KEY, encrypted=True, hop_start=3, hop_limit=1, rx_snr=-5.0) -> bytes` per i test.

- [ ] **Step 1: Scrivere `helpers.make_envelope`** (costruisce `Data`, lo cifra con `decrypt` se `encrypted`, altrimenti lo mette in `packet.decoded`, serializza `ServiceEnvelope`).

- [ ] **Step 2: Scrivere i test**

```python
T = "msh/EU_868/2/e/LongFast/!00000001"

def test_position_decoded():
    pos = mesh_pb2.Position(latitude_i=454642000, longitude_i=91900000, precision_bits=13)
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(3, pos), now=1000.0)
    assert ev.kind == "position" and ev.source == "mqtt"
    assert ev.payload.lat == pytest.approx(45.4642) and ev.payload.lon == pytest.approx(9.19)
    assert ev.payload.precision_bits == 13 and ev.hops == 2 and ev.gateway_id == "!00000001"
    assert node_id(ev.from_node) == "!a1b2c3d4"

def test_zero_position_has_no_coordinates():
    ev = EnvelopeDecoder([DEFAULT_KEY]).decode(T, make_envelope(3, mesh_pb2.Position()), now=1.0)
    assert ev is None  # posizione vuota = nessun evento

def test_text_nodeinfo_telemetry_mapreport(): ...
    # text: payload b"ciao <b>x</b>" → TextData("ciao <b>x</b>") (nessuna trasformazione)
    # nodeinfo: User(long_name="Base", short_name="BS", hw_model=HELTEC_V3) → hw_model == "HELTEC_V3"
    # telemetry: Telemetry(device_metrics=DeviceMetrics(battery_level=87, voltage=4.01)) → battery_level == 87
    # mapreport (encrypted=False, portnum 73, topic ".../2/map/"): lat/lon e firmware_version presenti

def test_second_key_is_tried():
    k2 = bytes(range(16))
    ev = EnvelopeDecoder([DEFAULT_KEY, k2]).decode(T, make_envelope(1, b"x", key=k2), now=1.0)
    assert ev.kind == "text"

@pytest.mark.parametrize("topic,payload,stat", [
    ("msh/EU_868/2/json/LongFast/!1", b'{"a":1}', "json_topic"),
    ("msh/EU_868/2/stat/!1", b"online", "not_protobuf"),
    (T, b"\xff\xff\xff", "not_protobuf"),
])
def test_garbage_is_counted_not_raised(topic, payload, stat):
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(topic, payload, now=1.0) is None and d.stats[stat] == 1

def test_unknown_key_counted_undecodable():
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(T, make_envelope(1, b"x", key=bytes(range(16))), now=1.0) is None
    assert d.stats["undecodable"] == 1

def test_unsupported_port_counted():
    d = EnvelopeDecoder([DEFAULT_KEY])
    assert d.decode(T, make_envelope(70, b""), now=1.0) is None and d.stats["unsupported_port"] == 1
```
Scrivere per intero i quattro casi di `test_text_nodeinfo_telemetry_mapreport` come test separati con le asserzioni indicate.

- [ ] **Step 3: Verificare che falliscano** — `.venv\Scripts\pytest server/tests/test_mqtt_decode.py -v` · FAIL.

- [ ] **Step 4: Implementare** `events.py` e `mqtt_decode.py`. Topic con segmento `json` → `json_topic` senza parsing. `ServiceEnvelope.ParseFromString` che solleva o envelope senza `packet` → `not_protobuf`. `rx_time` dell'evento = `now`. Ogni eccezione interna è catturata e contata: `decode` non solleva mai.

- [ ] **Step 5: Verificare** — stesso comando · tutti PASS.

- [ ] **Step 6: Commit** — `git commit -am "feat: decodifica envelope MQTT in MeshEvent"` (aggiungere i nuovi file).

---

### Task 3: Deduplica

**Files:** Create `server/meshlens/dedup.py` · Test `server/tests/test_dedup.py`

**Interfaces:** Produces `Deduplicator(window_s: float = 600)` con `is_new(from_node: int, packet_id: int, now: float) -> bool` (True alla prima vista nella finestra) e `prune(now: float) -> None`; memoria limitata a 200 000 chiavi (scarta le più vecchie).

- [ ] **Step 1: Test** — `is_new(1, 5, 0)` True; `is_new(1, 5, 10)` False; `is_new(2, 5, 10)` True; `is_new(1, 5, 700)` True (finestra scaduta); dopo 200 001 chiavi distinte la prima è dimenticata.
- [ ] **Step 2: FAIL** — `.venv\Scripts\pytest server/tests/test_dedup.py -v`
- [ ] **Step 3: Implementare** con `collections.OrderedDict` (chiave `(from, id)` → tempo).
- [ ] **Step 4: PASS** — stesso comando.
- [ ] **Step 5: Commit** — `git commit -m "feat: deduplica pacchetti"`

---

### Task 4: Nazione dalle coordinate

**Files:**
- Create: `tools/build_countries.py`, `server/meshlens/data/countries.geojson`, `server/meshlens/geo.py`
- Test: `server/tests/test_geo.py`

**Interfaces:** Produces `CountryLocator(geojson_path: Path | None = None, tolerance_km: float = 25.0)` (default: file del pacchetto) con `locate(lat: float | None, lon: float | None) -> str | None` (codice ISO alpha-2) e `names: dict[str, str]` (codice → nome italiano se disponibile in `NAME_IT`, altrimenti `NAME`).

- [ ] **Step 1: Scrivere `tools/build_countries.py`**: scarica `https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_admin_0_countries.geojson` (dominio pubblico), tiene per ogni feature solo `geometry` e le proprietà `iso` (= `ISO_A2_EH`, scartando `-99`), `name` (`NAME_IT` o `NAME`), arrotonda le coordinate a 4 decimali e scrive `server/meshlens/data/countries.geojson`.
- [ ] **Step 2: Eseguirlo** — `.venv\Scripts\python tools/build_countries.py` · Expected: file creato, < 10 MB, contiene `"iso": "IT"`.
- [ ] **Step 3: Test**

```python
loc = CountryLocator()
def test_inside(): assert loc.locate(45.4642, 9.19) == "IT"      # Milano
def test_border_city(): assert loc.locate(46.2044, 6.1432) == "CH"  # Ginevra
def test_sea_within_tolerance(): assert loc.locate(43.75, 10.10) == "IT"  # ~10 km da Viareggio
def test_open_sea_is_none(): assert loc.locate(39.5, 14.0) is None    # mar Tirreno meridionale, > 100 km dalla costa
def test_missing_or_zero(): assert loc.locate(None, None) is None and loc.locate(0.0, 0.0) is None
def test_names(): assert loc.names["IT"] in ("Italia", "Italy")
```
- [ ] **Step 4: FAIL** — `.venv\Scripts\pytest server/tests/test_geo.py -v`
- [ ] **Step 5: Implementare** con `shapely.STRtree` sui poligoni: contenimento con `query(point, predicate="within")`; se nessuno, `nearest` e distanza approssimata in km = distanza in gradi × 111 × (cos(lat) per la componente lon — usare `shapely.ops.nearest_points` e formula equirettangolare); oltre `tolerance_km` → None. `(0,0)` → None prima di qualsiasi calcolo.
- [ ] **Step 6: PASS** — stesso comando.
- [ ] **Step 7: Commit** — `git add tools server && git commit -m "feat: nazione da coordinate con confini Natural Earth"`

---

### Task 5: Database, impostazioni e store

**Files:**
- Create: `server/meshlens/db.py`, `server/meshlens/settings.py`, `server/meshlens/store.py`
- Test: `server/tests/test_store.py`, `server/tests/test_settings.py`

**Interfaces:**
- Produces:
  - `db.connect(path: Path | str) -> sqlite3.Connection` (WAL, `row_factory=sqlite3.Row`, crea lo schema se assente; `":memory:"` ammesso).
  - Schema: `nodes(num INTEGER PK, id TEXT, long_name, short_name, hw_model, role, firmware, lat REAL, lon REAL, precision_bits INT, position_source TEXT, position_time INT, country TEXT, last_heard REAL, sources TEXT /*json list*/, battery INT, voltage REAL, channel_util REAL, air_util_tx REAL, mqtt_gateways INT, last_snr REAL, hops INT, is_mine INT DEFAULT 0)`; `positions(id PK, node_num, time REAL, lat, lon, precision_bits, source)`; `messages(key TEXT PK, from_num, to_num, channel, text, time REAL, country, source)`; `telemetry(id PK, node_num, time REAL, battery, voltage, channel_util, air_util_tx, uptime)`; `settings(key TEXT PK, value TEXT /*json*/)`; `auth(key TEXT PK, value TEXT)`; `sessions(token_hash TEXT PK, created REAL, last_seen REAL, user_agent TEXT)`. Indici su `positions(node_num,time)`, `messages(time)`, `telemetry(node_num,time)`.
  - `settings.DEFAULTS: dict` con chiavi `saved_countries=["IT"]`, `retention_messages_days=90`, `retention_positions_days=90`, `retention_telemetry_days=365`, `storage_cap_mb=2048`, `lan_access=False`, `mqtt={"host":"mqtt.meshtastic.org","port":1883,"username":"meshdev","password":"large4cats","topics":["msh/EU_868/#"],"extra_keys":[]}`; `load_settings(conn) -> dict` (default + valori salvati); `save_settings(conn, changes: dict) -> dict` (valida tipi; `saved_countries` codici di 2 lettere maiuscole; `extra_keys` validate con `expand_psk`; solleva `ValueError` con messaggio in italiano).
  - `Store(conn)` con `upsert_node(node: dict)`, `add_position(num, time, lat, lon, precision_bits, source)`, `add_message(msg: dict)` (ignora chiave duplicata), `add_telemetry(num, time, t: TelemetryData)`, `load_nodes() -> list[dict]`, `positions(num, since: float) -> list[dict]`, `messages(countries: list[str] | None, before: float | None, limit: int) -> list[dict]`, `telemetry(num, since) -> list[dict]`, `purge(now: float, settings: dict) -> dict[str, int]` (righe eliminate per tabella, secondo retention; poi, se il file supera `storage_cap_mb`, elimina il 10% più vecchio di posizioni e messaggi finché sotto), `commit()`.

- [ ] **Step 1: Test** — upsert e rilettura nodo (lista `sources` preservata); messaggio duplicato non solleva e non duplica; `messages(["IT"], None, 50)` filtra; `purge` con retention 90 giorni elimina una posizione di 91 giorni fa e tiene una di 89; `load_settings` su DB vuoto == `DEFAULTS`; `save_settings({"saved_countries": ["it"]})` → `ValueError`; `save_settings({"mqtt": {"extra_keys": ["abc"]}})` → `ValueError`; modifica parziale di `mqtt` mantiene le altre chiavi.
- [ ] **Step 2: FAIL** — `.venv\Scripts\pytest server/tests/test_store.py server/tests/test_settings.py -v`
- [ ] **Step 3: Implementare** i tre moduli (sqlite3 puro, nessun ORM).
- [ ] **Step 4: PASS** — stesso comando.
- [ ] **Step 5: Commit** — `git commit -m "feat: schema SQLite, impostazioni e store"`

---

### Task 6: Stato live e Ingestor

**Files:**
- Create: `server/meshlens/live.py`, `server/meshlens/ingest.py`
- Test: `server/tests/test_ingest.py`

**Interfaces:**
- Consumes: `MeshEvent`, `Deduplicator`, `CountryLocator`, `Store`, settings dict.
- Produces:
  - `LiveState(max_messages: int = 2000)` con `nodes: dict[int, dict]` (JSON nodo), `messages: collections.deque`, `take_changed() -> list[dict]` (nodi modificati dall'ultima chiamata), `load(nodes: list[dict])`.
  - `Ingestor(live, store, dedup, locator, get_settings: Callable[[], dict], on_message: Callable[[dict], None])` con `handle(ev: MeshEvent) -> None`.
- Regole di `handle` (dalla spec §9):
  1. Aggiorna sempre `last_heard`, `sources`, `last_snr`, `hops` del nodo; per MQTT, se il pacchetto è un duplicato (`dedup.is_new` False) incrementa solo `mqtt_gateways` e termina.
  2. **Posizione migliore**: una nuova posizione sostituisce quella del nodo se è più precisa (`precision_bits` maggiore; `None` = 32 per RF) oppure se quella attuale è più vecchia di 24 h; la nazione si ricalcola a ogni sostituzione.
  3. `nodeinfo`/`mapreport` aggiornano anagrafica (mapreport aggiorna anche `firmware` e, con la regola 2, la posizione con source `"mqtt_map"`).
  4. `telemetry` aggiorna `battery`, `voltage`, `channel_util`, `air_util_tx`.
  5. `text` crea il JSON messaggio (chiave `f"{from}:{packet_id}"`, `country` = nazione del mittente o None), lo aggiunge a `live.messages` e chiama `on_message`.
  6. **Persistenza**: si scrive su `store` solo se la nazione del nodo è in `saved_countries` oppure `ev.source == "rf"` oppure il nodo è `is_mine`. Un nodo senza nazione non si salva (finché non riceve una posizione in una nazione scelta).
  7. Tutti i nodi (anche non salvati) restano in `live.nodes` e sono segnati come modificati.

- [ ] **Step 1: Test** (eventi costruiti direttamente come `MeshEvent`, store su `:memory:`, locator reale):
  - posizione a Milano → nodo `country == "IT"`, presente in `store.load_nodes()` e una riga in `positions`;
  - posizione a Berlino → nodo in `live.nodes` con `country == "DE"`, **assente** dallo store (`saved_countries=["IT"]`);
  - testo da nodo italiano → `on_message` chiamato con `country == "IT"`, `text` invariato, messaggio salvato;
  - stesso pacchetto due volte via MQTT → un solo messaggio, `mqtt_gateways == 2`;
  - posizione `precision_bits=13` poi `precision_bits=10` entro 24 h → resta la 13; poi `precision_bits=10` con `rx_time` + 25 h → sostituita;
  - nodo con solo `nodeinfo` → in `live.nodes` senza `lat`, `country` None, non salvato;
  - `take_changed()` restituisce i nodi toccati e poi lista vuota.
- [ ] **Step 2: FAIL** — `.venv\Scripts\pytest server/tests/test_ingest.py -v`
- [ ] **Step 3: Implementare** `live.py` e `ingest.py`.
- [ ] **Step 4: PASS** — stesso comando.
- [ ] **Step 5: Commit** — `git commit -m "feat: stato live e pipeline di ingestione"`

---

### Task 7: PIN e sessioni

**Files:** Create `server/meshlens/auth.py` · Test `server/tests/test_auth.py`

**Interfaces:** Produces `Auth(conn, clock: Callable[[], float] = time.time)` con `pin_is_set() -> bool`, `set_pin(pin: str) -> None` (4–12 cifre, altrimenti `ValueError`; hash argon2), `login(pin: str, client_ip: str) -> str` (restituisce token di sessione; salva `sha256(token)`; `PermissionError` se PIN errato; `LockedError(retry_after: int)` dopo 5 errori consecutivi dallo stesso IP per 300 s), `check(token: str | None) -> bool` (aggiorna `last_seen`), `logout(token)`, `reset() -> None` (cancella PIN e tutte le sessioni).

- [ ] **Step 1: Test** — `set_pin("12")` → `ValueError`; `set_pin("1234")` poi login corretto → token e `check(token)` True; `check("x")` False; 5 login errati → il 6° (anche corretto) solleva `LockedError`; con clock avanzato di 301 s il login corretto riesce; `reset()` → `pin_is_set()` False e vecchio token non valido.
- [ ] **Step 2: FAIL** — `.venv\Scripts\pytest server/tests/test_auth.py -v`
- [ ] **Step 3: Implementare** con `argon2.PasswordHasher` e `secrets.token_urlsafe(32)`.
- [ ] **Step 4: PASS** — stesso comando.
- [ ] **Step 5: Commit** — `git commit -m "feat: PIN, sessioni e blocco tentativi"`

---

### Task 8: API REST, WebSocket e bus

**Files:**
- Create: `server/meshlens/bus.py`, `server/meshlens/api.py`
- Test: `server/tests/test_api.py`

**Interfaces:**
- Consumes: `LiveState`, `Store`, `Auth`, `CountryLocator.names`, `load_settings/save_settings`.
- Produces:
  - `Bus` con `subscribe() -> asyncio.Queue`, `unsubscribe(q)`, `publish(msg: dict)` (code piene: scarta il messaggio più vecchio; max 1000).
  - `create_app(ctx: AppContext) -> FastAPI`, dove `AppContext` (dataclass in `api.py`) contiene `live, store, auth, bus, locator, conn, mqtt_status: Callable[[], dict], on_settings_changed: Callable[[dict], Awaitable[None]], static_dir: Path | None`.
  - Cookie di sessione `meshlens_session` (HttpOnly, SameSite=Strict, Max-Age 1 anno).
  - Endpoint (tutti sotto `/api`, tutti con sessione valida salvo `auth/*`; senza → 401 `{"detail":"Accesso richiesto"}`):
    - `GET /auth/status` → `{"pin_set":bool,"authenticated":bool,"is_local":bool}` (`is_local` = client `127.0.0.1`/`::1`)
    - `POST /auth/setup {"pin"}` → solo se PIN non impostato **e** client locale, altrimenti 403; imposta cookie
    - `POST /auth/login {"pin"}` → 200 + cookie, 401 PIN errato, 429 con header `Retry-After` se bloccato
    - `POST /auth/logout`
    - `GET /nodes` → lista JSON nodo da `live.nodes`; query opzionali `country` (lista separata da virgole, `"none"` = senza nazione), `max_age_h`
    - `GET /nodes/{id}` → nodo + `"telemetry"` (ultime 24 h da store, vuota se non salvato); 404 se assente
    - `GET /nodes/{id}/positions?hours=24`
    - `GET /messages?country=IT&limit=200` → da `live.messages` (più recenti prima)
    - `GET /messages/history?country=IT&before=<ts>&limit=200` → da store
    - `GET /countries` → `[{"code":"IT","name":"Italia","nodes":123}]` dai nodi live, più `{"code":"none","name":"Sconosciuta",...}`
    - `GET /settings` (password MQTT restituita come `"••••"` se non vuota) · `PUT /settings` (parziale; `"••••"` = invariata) → impostazioni aggiornate; 400 con il messaggio di `ValueError`; dopo il salvataggio chiama `on_settings_changed`
    - `GET /status` → `mqtt_status()`
  - `WS /ws`: accetta solo con cookie valido, altrimenti chiude con codice 4401; inoltra i messaggi del bus.
  - Statici: se `static_dir` esiste, montato su `/` con `index.html` come fallback.

- [ ] **Step 1: Test** con `httpx.AsyncClient(transport=ASGITransport(app))` e `starlette.testclient.TestClient` per il WebSocket:
  - senza cookie `GET /api/nodes` → 401; `WS /ws` → chiusura 4401;
  - `POST /auth/setup` da client non locale (impostare `client=("192.168.1.50", 1234)` nel transport) → 403; da locale → 200 e cookie; secondo setup → 403;
  - login errato ×5 poi → 429 con `Retry-After`;
  - con cookie: `GET /api/nodes?country=IT` filtra; `GET /api/countries` conta; `GET /api/settings` maschera la password; `PUT /api/settings {"saved_countries":["XX1"]}` → 400; `PUT` valido chiama `on_settings_changed`;
  - `bus.publish({"type":"message",...})` arriva a un client WebSocket autenticato.
- [ ] **Step 2: FAIL** — `.venv\Scripts\pytest server/tests/test_api.py -v`
- [ ] **Step 3: Implementare** `bus.py` e `api.py`.
- [ ] **Step 4: PASS** — stesso comando.
- [ ] **Step 5: Commit** — `git commit -m "feat: API REST, WebSocket e autenticazione"`

---

### Task 9: Connettore MQTT, wiring, CLI e avvio

**Files:**
- Create: `server/meshlens/mqtt_client.py`, `server/meshlens/app.py`, `server/meshlens/__main__.py`, `start.bat`
- Test: `server/tests/test_mqtt_client.py`, `server/tests/test_app.py`

**Interfaces:**
- Consumes: tutto quanto sopra.
- Produces:
  - `MqttConnector(cfg: dict, decoder: EnvelopeDecoder, loop: asyncio.AbstractEventLoop, on_event: Callable[[MeshEvent], None], client_factory=paho.mqtt.client.Client)` con `start()`, `stop()`, `status() -> {"connected":bool,"msgs_per_s":float,"undecodable":int}`. Client id `f"meshlens-{secrets.token_hex(4)}"`; `reconnect_delay_set(1, 60)`; `connect_async` + `loop_start` (non blocca se il broker non è raggiungibile); in `on_connect` sottoscrive ogni topic di `cfg["topics"]` con QoS 0; `on_message` decodifica nel thread paho e passa gli eventi con `loop.call_soon_threadsafe(on_event, ev)`. Nessuna chiamata `publish` nel modulo.
  - `app.build(data_dir: Path) -> tuple[FastAPI, Runtime]`: apre DB, crea componenti, carica nodi salvati in `LiveState`, avvia su startup: connettore MQTT, task ogni 2 s (`live.take_changed()` → bus `nodes` se non vuoto), ogni 5 s (status → bus), ogni 1 s `store.commit()`, ogni 24 h + all'avvio `store.purge`, ogni 60 s `dedup.prune`. `on_settings_changed` ricrea il connettore se cambia `mqtt`.
  - `__main__.main()`: `meshlens run [--data-dir data] [--port 8686] [--no-browser]` (host secondo `lan_access`; apre `http://127.0.0.1:8686` nel browser); `meshlens reset-pin` (chiama `Auth.reset()` e stampa "PIN azzerato: al prossimo accesso dal PC potrai sceglierne uno nuovo.").
  - `start.bat`: crea `.venv` se assente e installa (`pip install -e .`), se `web\dist` manca e `npm` è disponibile esegue `npm ci && npm run build` in `web`, poi `.venv\Scripts\meshlens run`.

- [ ] **Step 1: Test** con un `FakeClient` (registra `subscribe`, permette di invocare `on_connect`/`on_message`, fallisce se viene chiamato `publish`):
  - dopo `on_connect` sottoscrive esattamente `["msh/EU_868/#"]`;
  - un `on_message` con envelope di `helpers.make_envelope` porta `on_event` a essere chiamato sul loop;
  - un `FakeClient` il cui `connect_async` solleva `OSError` (nessuna rete): `start()` non solleva e `status()["connected"] is False`;
  - `test_app.py`: `app.build(tmp_path)` con connettore sostituito da un fake → `GET /api/auth/status` risponde 200; `meshlens reset-pin` su quel DB azzera il PIN.
- [ ] **Step 2: FAIL** — `.venv\Scripts\pytest server/tests/test_mqtt_client.py server/tests/test_app.py -v`
- [ ] **Step 3: Implementare** i moduli e `start.bat`.
- [ ] **Step 4: PASS** — stesso comando, poi l'intera suite: `.venv\Scripts\pytest -q` · tutto verde.
- [ ] **Step 5: Prova reale** — `.venv\Scripts\meshlens run --no-browser`, poi (altro terminale, dopo il setup PIN da browser o via `httpx`) `GET http://127.0.0.1:8686/api/status` · Expected entro 30 s: `connected: true`, `msgs_per_s` > 10; `GET /api/countries` contiene `IT`.
- [ ] **Step 6: Commit** — `git commit -m "feat: connettore MQTT, avvio e CLI"`

---

### Task 10: Scaffold interfaccia, accesso e client

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`, `web/index.html`, `web/src/main.ts`, `web/src/App.svelte`, `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/lib/ws.ts`, `web/src/lib/filters.ts`, `web/src/lib/format.ts`, `web/src/lib/stores.svelte.ts`, `web/src/components/Login.svelte`
- Test: `web/src/lib/filters.test.ts`, `web/src/lib/format.test.ts`

**Interfaces:**
- Produces:
  - `types.ts`: `Node`, `Message`, `Status`, `Settings` conformi ai JSON del contratto.
  - `api.ts`: `getJSON<T>(path)`, `send<T>(method, path, body?)`; su 401 emette l'evento `auth-required`.
  - `ws.ts`: `connectWS(handlers: {nodes(n: Node[]), message(m: Message), status(s: Status)})` con riconnessione ogni 3 s; su chiusura 4401 emette `auth-required`.
  - `filters.ts`: `type NodeFilter = {countries: string[]; maxAgeH: number | null; sources: string[]; text: string}`; `matchNode(n: Node, f: NodeFilter, now: number): boolean` (`countries` vuoto = tutti; `"none"` corrisponde a `country === null`; `text` cerca in `long_name`, `short_name`, `id`, senza maiuscole); `ageClass(lastHeard: number, now: number): "fresh" | "recent" | "old"` (< 2 h, < 24 h, oltre).
  - `format.ts`: `timeAgo(ts: number, now: number): string` in italiano ("adesso", "5 min fa", "3 h fa", "2 g fa"); `flag(code: string | null): string` (emoji bandiera o "🏳️").
  - `stores.svelte.ts`: stato reattivo (`$state`) con `nodes: Map<string, Node>`, `messages: Message[]` (max 500), `status`, `filter: NodeFilter`, `selectedId`.
  - `Login.svelte`: se `pin_set` false e `is_local` → "Scegli un PIN" (conferma doppia); se `pin_set` false e non locale → "Configura MeshLens dal PC"; altrimenti campo PIN; mostra messaggio di blocco con i secondi del `Retry-After`.
  - `vite.config.ts`: proxy `/api` e `/ws` verso `http://127.0.0.1:8686` in sviluppo; build in `web/dist`.

- [ ] **Step 1: Creare il progetto** — in `web/`: Svelte 5 + Vite + TypeScript (`npm create vite@latest . -- --template svelte-ts`), poi `npm i maplibre-gl` e `npm i -D vitest`; script `"test": "vitest run"`.
- [ ] **Step 2: Test**

```ts
const now = 1_000_000;
const n = {id:"!a1b2c3d4", long_name:"Base Milano", short_name:"BM", country:"IT", last_heard: now-3600, sources:["mqtt"]} as Node;
test("country filter", () => {
  expect(matchNode(n, {countries:["IT"], maxAgeH:null, sources:[], text:""}, now)).toBe(true);
  expect(matchNode(n, {countries:["FR"], maxAgeH:null, sources:[], text:""}, now)).toBe(false);
  expect(matchNode({...n, country:null}, {countries:["none"], maxAgeH:null, sources:[], text:""}, now)).toBe(true);
});
test("age and text", () => {
  expect(matchNode(n, {countries:[], maxAgeH:0.5, sources:[], text:""}, now)).toBe(false);
  expect(matchNode(n, {countries:[], maxAgeH:null, sources:[], text:"milano"}, now)).toBe(true);
  expect(ageClass(now-3600, now)).toBe("fresh");
  expect(ageClass(now-3*3600, now)).toBe("recent");
  expect(ageClass(now-25*3600, now)).toBe("old");
});
test("format", () => {
  expect(timeAgo(now-30, now)).toBe("adesso");
  expect(timeAgo(now-300, now)).toBe("5 min fa");
  expect(flag("IT")).toBe("🇮🇹");
});
```
- [ ] **Step 3: FAIL** — `cd web; npm test` · FAIL.
- [ ] **Step 4: Implementare** i moduli `lib/`, `Login.svelte` e un `App.svelte` minimo che mostra Login o il testo "Connesso".
- [ ] **Step 5: PASS** — `npm test` verde; `npm run build` senza errori.
- [ ] **Step 6: Commit** — `git add web && git commit -m "feat: scaffold interfaccia, accesso e client API/WS"`

---

### Task 11: Mappa, elenco nodi, dettaglio, filtri

**Files:** Create `web/src/components/MapView.svelte`, `NodeList.svelte`, `NodeDetail.svelte`, `Filters.svelte`, `StatusBar.svelte` · Modify `web/src/App.svelte`

**Interfaces:** Consumes `stores`, `filters`, `format`, `api`, `ws`.

Comportamento:
- `MapView`: MapLibre con lo stile dei Global Constraints, centrata sull'Italia (lat 42.5, lon 12.5, zoom 5). Nodi come layer GeoJSON `circle` (non marker DOM: centinaia di nodi), colore per `ageClass` (verde `#2e9e44`, giallo `#e0a800`, grigio `#8a8a8a`), raggio maggiore per il nodo selezionato; clustering MapLibre sotto zoom 8. Click → `selectedId`. Aggiornamento della sorgente al massimo una volta al secondo. Per i nodi con `precision_bits` < 16 mostra, quando selezionati, un cerchio approssimativo dell'incertezza (raggio dal valore: `23_300_000 / 2**precision_bits` metri circa, arrotondato).
- `NodeList`: nodi filtrati ordinati per `last_heard` decrescente, con bandiera, nome, tempo fa, batteria; click seleziona e centra la mappa.
- `NodeDetail`: campi del JSON nodo in italiano; precisione posizione ("± 1,5 km"); pulsante "Mostra percorso" che carica `/api/nodes/{id}/positions?hours=24` e disegna una linea.
- `Filters`: multi-selezione nazioni da `/api/countries` (con bandiere e conteggi, "Sconosciuta" in fondo), ultimo contatto (tutti / 2 h / 24 h / 7 g), ricerca testo. Il filtro scelto si ricorda in `localStorage`. Default: nazioni `["IT"]`.
- `StatusBar`: stato MQTT (pallino verde/rosso), messaggi/s, numero nodi visibili.
- Layout: su schermo < 768 px mappa a tutto schermo, barra inferiore con schede Mappa / Nodi / Chat / Impostazioni, pannelli a comparsa dal basso; ≥ 768 px pannello laterale sinistro a schede.

- [ ] **Step 1: Implementare** i componenti e integrarli in `App.svelte` (`GET /api/nodes` all'avvio, poi aggiornamenti WS).
- [ ] **Step 2: Build** — `npm run build` · nessun errore né warning di accessibilità bloccanti.
- [ ] **Step 3: Verifica nel browser** — server avviato, aprire `http://127.0.0.1:8686` nel browser integrato; Expected: nodi italiani sulla mappa entro 30 s, filtro "Germania" mostra nodi tedeschi, click su un nodo apre il dettaglio. Ripetere con viewport mobile (375×812): schede in basso funzionanti.
- [ ] **Step 4: Commit** — `git commit -am "feat: mappa, elenco nodi, dettaglio e filtri"` (aggiungere i nuovi file).

---

### Task 12: Feed messaggi e impostazioni

**Files:** Create `web/src/components/MessageFeed.svelte`, `web/src/components/Settings.svelte` · Modify `web/src/App.svelte`

Comportamento:
- `MessageFeed`: `GET /api/messages` + messaggi WS; filtrati con le stesse nazioni del filtro nodi; ogni riga: bandiera, nome mittente (click → seleziona il nodo), canale, testo, tempo fa. Pulsante "Carica precedenti" → `/api/messages/history?before=`. Testo sempre come testo (`{msg.text}`), a capo automatico, nessun troncamento distruttivo.
- `Settings`: nazioni da salvare nello storico (multi-selezione), giorni di retention (3 campi), limite spazio MB, accesso dalla rete locale (con nota "richiede il riavvio di MeshLens"), MQTT (host, porta, utente, password mascherata, topic uno per riga, chiavi aggiuntive in base64 una per riga), pulsante "Esci". Salvataggio con `PUT /api/settings`; mostra in rosso il messaggio d'errore del server.

- [ ] **Step 1: Implementare** i due componenti.
- [ ] **Step 2: Controllo sicurezza testi** — Run: `git grep -n "@html" web/src` · Expected: nessun risultato.
- [ ] **Step 3: Build** — `npm run build` senza errori.
- [ ] **Step 4: Verifica nel browser** — Expected: arrivano messaggi pubblici; con filtro Italia solo messaggi di nodi italiani; cambiando `saved_countries` in `["IT","CH"]` il salvataggio riesce e `GET /api/settings` lo riflette; inserendo `"abc"` tra le chiavi compare l'errore.
- [ ] **Step 5: Commit** — `git commit -am "feat: feed messaggi e impostazioni"`

---

### Task 13: Verifica finale della fase

- [ ] **Step 1: Suite completa** — `.venv\Scripts\pytest -q` e `cd web; npm test` · tutto verde.
- [ ] **Step 2: Avvio pulito** — eliminare `data/`, eseguire `start.bat` · Expected: browser aperto, richiesta "Scegli un PIN", poi mappa con nodi entro 30 s.
- [ ] **Step 3: Senza internet** — disattivare la rete, riavviare · Expected: l'app parte, stato MQTT rosso, nodi italiani salvati visibili; riattivando la rete torna verde senza riavvio.
- [ ] **Step 4: Accesso dal telefono** — impostare `lan_access` a true, riavviare, aprire `http://<ip-del-PC>:8686` dal telefono · Expected: richiesta PIN, poi interfaccia mobile. (Se Windows chiede il permesso del firewall per Python, va concesso per le reti private.)
- [ ] **Step 5: Storico solo per le nazioni scelte** — con `saved_countries=["IT"]`: `GET /api/nodes?country=DE` restituisce nodi; dopo il riavvio la stessa chiamata restituisce lista vuota, mentre `GET /api/nodes?country=IT` restituisce ancora i nodi italiani.
- [ ] **Step 6: Commit finale e tag** — `git tag fase1`
