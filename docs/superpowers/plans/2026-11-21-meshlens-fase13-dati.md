# MeshLens Fase 13 — Dati e telemetria: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** usare i dati che MeshLens riceve già e oggi scarta o non mostra. Sono le proposte B4, B5, B6, B7, B8 e C4 di `docs/superpowers/research/2026-11-21-proposte-prossima-release.md`:
- telemetria ambientale, qualità dell'aria, potenza, statistiche locali e salute, decodificata da MQTT e da radio e salvata in una tabella generica;
- grafici più ricchi con lettura al passaggio del mouse e periodo a scelta;
- esportazione CSV, GPX, GeoJSON e KML generata nel browser;
- percorso storico di un nodo con periodo a scelta;
- pagina di statistiche della rete;
- ispettore dei pacchetti con limiti di spazio.

**Architettura:**
- **Database:** la migrazione **5** (di proprietà di questa fase) aggiunge quattro tabelle:
  - `metrics`, in formato lungo `(nodo, tempo, variante, metrica, valore)`;
  - `packets`, i pacchetti deduplicati per l'ispettore, con un tetto di righe;
  - `stats_hourly` e `node_hourly`, aggregati orari del traffico e dei nodi.
  
  La pulizia a blocchi della fase 9 (`purge_step`) le copre tutte.
- **Ingestione:** un modulo nuovo, `telemetry_decode.py`, decodifica tutte le varianti di `Telemetry` ed è condiviso dai decoder MQTT e RF. I pacchetti non decodificati diventano `RawPacket` solo se l'ispettore li vuole. Due osservatori nuovi, `PacketLog` (ispettore) e `NetStats` (aggregati orari), stanno **fuori** dall'`Ingestor`: li chiama il dispatcher `on_event` di `app.py` dopo `ingestor.handle`. Accumulano in memoria e scrivono a lotti con `executemany` sul loop.
- **Letture:** le query pesanti (serie, percorsi, statistiche, ispettore) sono funzioni pure `f(conn, …)` in `queries.py`. Le rotte di `api_data.py` le eseguono con `run_read`, cioè in `asyncio.to_thread` con una connessione propria in sola lettura. `api.py` (1300 righe) cambia solo per agganciare le rotte nuove.
- **Interfaccia:** grafici SVG fatti a mano come l'attuale `TelemetryChart.svelte` (path calcolati in `lib/chart.ts`), **senza librerie di grafici**. Esportazioni con `Blob` lato client. Statistiche e ispettore sono due viste nuove della pagina Rete (Segmented «Nodi / Statistiche / Pacchetti»), senza schede nuove nella navigazione.

**Tech Stack:** Python 3.12 + FastAPI, sqlite3 (stdlib), paho-mqtt, protobuf di meshtastic 2.7.11 (`telemetry_pb2`, `google.protobuf.json_format.ParseDict`); Svelte 5 (runes) + Vite + vitest, SVG.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md`: §6.3 (grafici storici), §7 (dati e retention: «pacchetti (deduplicati)», telemetria per 1 anno, posizioni per 90 giorni) e §9 «Volume» (le osservazioni MQTT si aggregano per pacchetto, limite di spazio). Proposte: `docs/superpowers/research/2026-11-21-proposte-prossima-release.md` (B4–B8, C4). Restano valide le Global Constraints delle fasi 8, 9 e 11 (`docs/superpowers/plans/2026-11-21-meshlens-fase8-design-invio.md`, `…-fase9-fondamenta.md`, `…-fase11-ux-mappa.md`).

## Global Constraints

- Valgono tutte le Global Constraints delle fasi 8, 9 e 11:
  - italiano, `Intl` `it-IT`, il meno tipografico «−»;
  - **nessun colore fuori dai token** (`var(--…)` di `tokens.css`). Per i colori scritti nei file KML si leggono i token `--snr-*` con `getComputedStyle`;
  - testo ≥ 14 px e aree toccabili ≥ 44 px su telefono (`.vp-phone`, `max-width: 820px`); focus sempre visibile;
  - **nessuna risorsa esterna a runtime**;
  - Svelte 5: nessun `$effect` legge e scrive lo stesso `$state`; timer e listener puliti; l'effetto WebSocket e dati di `App.svelte` non segue stati nuovi.
- **Nessuna dipendenza nuova** in `pyproject.toml` né in `web/package.json`. Niente librerie di grafici: SVG e `lib/chart.ts`, come `TelemetryChart.svelte` oggi.
- **Connessione SQLite principale solo dal thread del loop.**
  - Le letture di questa fase passano da `run_read(ctx, fn)`: con `ctx.db_path` impostato girano in `asyncio.to_thread` su `ro_connect(db_path)` (`file:…?mode=ro`, `timeout=30`); senza `db_path` (database in memoria dei test) girano su `ctx.conn`.
  - Le scritture di `PacketLog` e `NetStats` avvengono sul loop: al massimo `FLUSH_MAX = 2000` righe per chiamata, con `executemany`.
- **Ispettore limitato:**
  - righe di `packets` al massimo `PACKETS_MAX_ROWS = 300_000`, controllate ogni 60 s a blocchi di `PURGE_CHUNK` (2000) con `await asyncio.sleep(0.05)` tra un blocco e l'altro;
  - età massima `retention_packets_hours` (predefinita 48, ammessa 1–168);
  - buffer in memoria al massimo `BUFFER_MAX = 20_000` voci: oltre si scartano le più vecchie e si contano;
  - `raw` al massimo `RAW_MAX = 256` byte, `summary` al massimo 2000 caratteri.
- **Migrazione:** questa fase possiede il passo **5** (`SCHEMA_VERSION = 5`) e presuppone che la fase 12 abbia portato lo schema a 4. Se all'avvio del Task 1 `SCHEMA_VERSION` in `db.py` non vale 4, ci si ferma e lo si segnala. Nessun'altra dipendenza dai dettagli della fase 12.
- **Fase 14 in parallelo** (copertura prevista, Store & Forward), che toccherà `radio.py`, `ingest.py` e i decoder. Le modifiche di questa fase in quei file sono piccole e dichiarate:
  - `ingest.py`: guardia sul tipo, `last_outcome`, `is_archived`, ramo della telemetria;
  - `mqtt_decode.py`: `_parse_telemetry`, `decode_any`, `meta`;
  - `rf_convert.py`: telemetria, `meta`, `packet_to_raw`;
  - `radio.py`: solo `on_packet`;
  - `mqtt_client.py`: solo `_on_message`;
  - `app.py`: `on_event` in `build` e i task periodici.
  
  Il resto va in moduli nuovi.
- **Testi estraibili** (la fase 14 tradurrà l'interfaccia):
  - ogni frase è un'unica stringa letterale, al più con valori interpolati;
  - niente frasi composte da pezzi;
  - plurali come due stringhe complete;
  - etichette di metriche, tipi di pacchetto e stati in mappe costanti dentro `lib/*.ts`.
- **Contratti JSON solo additivi:** `GET /api/nodes/{id}/telemetry` e `GET /api/nodes/{id}/positions` mantengono forma e campi; si aggiungono parametri facoltativi e rotte.
- **Nessun cambio di versione.**
- **Test:**
  - nei task di implementazione si eseguono **solo i test mirati** del task: `PYTHONPATH=server .venv/Scripts/python -m pytest -q <file>` dalla radice, `cd web && npx vitest run <file>`;
  - le suite intere si eseguono solo nel Task 11.
- Messaggi di commit in italiano, stile `feat(server): …` / `feat(web): …`.

## Contratti JSON (aggiunte)

- `GET /api/nodes/{id}/telemetry?hours=168&max_points=800`: come oggi, una lista di `{time, battery, voltage, channel_util, air_util_tx}`. Oltre `max_points` i punti sono medie a intervalli di tempo uguali. `hours` è compreso tra 0 (escluso) e 8784.
- `GET /api/nodes/{id}/positions?hours=24&max_points=5000`: come oggi, una lista di `{time, lat, lon, precision_bits, source}`. Oltre `max_points` restano un punto ogni k, più sempre il primo e l'ultimo.
- `GET /api/nodes/{id}/metrics?hours=168` → `{latest: {"<variante>.<metrica>": {value, time}}, series: {"<variante>.<metrica>": [[time, value], …]}}`. `latest` copre tutto lo storico, `series` solo il periodo; al massimo 800 punti per serie.
- `GET /api/nodes/{id}/snr?hours=168` → `[{time, source: "rf"|"mqtt", snr_avg, snr_max, packets}]`, un elemento per ora.
- `GET /api/stats?hours=24` (da 1 a 2160) →
  ```
  {hours, since, totals:{nodes, packets},
   online:[{time, nodes}],
   packets:[{time, kind, packets, receptions}],
   snr:{bins:[-20,-17.5,…,15], rf:[n…], mqtt:[n…]},
   hops:[{hops: 0..7|null, nodes}],
   top:[{id, name, packets, per_hour}],
   hardware:[{value, nodes}], roles:[{value, nodes}], other_hardware: n}
  ```
  Il risultato resta in cache 60 s per valore di `hours`.
- `GET /api/packets?node=!hex&kind=&source=rf|mqtt&status=&min_snr=&since=&until=&before_id=&limit=100` (limit ≤ 200) → `{items:[PacketRow], next_before_id: int|null}`.
  - `PacketRow` = `{id, time, from, from_name, to, packet_id, source, broker, radio_id, channel, portnum, kind, status, snr, rssi, hops, hop_start, hop_limit, relay_node, gateway, copies, size}`.
  - `status` vale `ok | encrypted | unsupported | undecodable | empty`.
- `GET /api/packets/{id}` → `PacketRow` + `{receptions:[{source, broker, radio_id, gateway, snr, rssi, hops, relay_node, time}], summary: object|null, raw_hex: string}`; 404 se assente.
- Impostazioni nuove: `packet_log_mode: "off"|"archived"|"all"` (predefinita `"archived"`) e `retention_packets_hours: int` (predefinita 48, da 1 a 168).
- `GET /api/db`: `rows` guadagna `metrics` e `packets`.

## Review Focus

1. **Raffica dal broker pubblico con `packet_log_mode = "all"`:** il loop non si blocca, `packets` non supera mai `PACKETS_MAX_ROWS` più un minuto di afflusso, gli scarti del buffer sono contati, l'ingestione dei nodi resta invariata. → Task 4 (`test_trim_packets_chunks_and_yields`, `test_buffer_overflow_drops_oldest`).
2. **Aggiornamento di un database 4 con milioni di righe di telemetria:** la migrazione 5 crea solo tabelle e indici nuovi e non riscrive i dati esistenti; una seconda apertura non rifà nulla. → Task 1 (`test_v4_db_migrates_to_5_without_touching_telemetry`).
3. **Telemetria strana:** varianti non gestite (`host_metrics`, `traffic_management_stats`), valori NaN, un pacchetto ambientale vuoto. Niente eccezioni, niente righe salvate, scarto contato come `unsupported_port` o `empty`. La telemetria di dispositivo funziona esattamente come prima. → Task 2.
4. **Nodo mobile con 90 giorni di posizioni ogni 30 s** (circa 260 000 righe): la rotta restituisce al massimo 5000 punti, primo e ultimo inclusi, letti fuori dal loop. → Task 5 (`test_track_decimates_keeping_ends`).
5. **Esportazione di nomi con virgole, virgolette, a capo, `<&>` ed emoji:** CSV quotato correttamente, GPX e KML con XML valido, nomi di file sicuri. → Task 8.

---

### Task 1: Database — migrazione 5, metodi dello Store, pulizia, impostazioni  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/db.py`, `server/meshlens/store.py`, `server/meshlens/settings.py`, `server/meshlens/maintenance.py`
- Test: `server/tests/test_db.py`, `server/tests/test_store.py`, `server/tests/test_settings.py`

**Interfaces:**
- Consumes: `SCHEMA_VERSION = 4` e `_STEPS` (fase 12); `purge_step`, `PURGE_CHUNK` (fase 9).
- Produces:
  - `SCHEMA_VERSION = 5`, `_SCHEMA_V5: str`, `_migration_5(conn)` (esegue `_SCHEMA_V5`, idempotente), `_STEPS[5]`. `SCHEMA` **non** cambia, così si evitano conflitti con la fase 12.
  - Tabelle e indici (tutti con `IF NOT EXISTS`):
    ```sql
    metrics(node_num INTEGER NOT NULL, time REAL NOT NULL, variant TEXT NOT NULL,
            metric TEXT NOT NULL, value REAL NOT NULL)
      idx_metrics_node ON metrics(node_num, variant, metric, time); idx_metrics_time ON metrics(time)
    packets(id INTEGER PRIMARY KEY AUTOINCREMENT, time REAL NOT NULL, from_num INTEGER,
            to_num INTEGER, packet_id INTEGER, source TEXT, broker TEXT, radio_id TEXT,
            channel TEXT, portnum TEXT, kind TEXT, status TEXT NOT NULL, snr REAL, rssi INTEGER,
            hops INTEGER, hop_start INTEGER, hop_limit INTEGER, relay_node INTEGER, gateway TEXT,
            copies INTEGER NOT NULL DEFAULT 1, receptions TEXT, summary TEXT, raw BLOB, size INTEGER)
      idx_packets_time(time); idx_packets_from_time(from_num, time); idx_packets_kind_time(kind, time)
    stats_hourly(time INTEGER NOT NULL, source TEXT NOT NULL, kind TEXT NOT NULL,
                 packets INTEGER NOT NULL, receptions INTEGER NOT NULL, UNIQUE(time, source, kind))
    node_hourly(time INTEGER NOT NULL, node_num INTEGER NOT NULL, source TEXT NOT NULL,
                packets INTEGER NOT NULL, snr_sum REAL NOT NULL DEFAULT 0,
                snr_n INTEGER NOT NULL DEFAULT 0, snr_max REAL, UNIQUE(time, node_num, source))
      idx_node_hourly_node(node_num, time)
    ```
    `time` delle tabelle orarie = inizio dell'ora in secondi epoch. Il nome `time` permette alla pulizia di usare la stessa condizione `time < ?`.
  - In `store.py`:
    - `add_metrics(num: int, time: float, variant: str, metrics: dict[str, float]) -> None` (`executemany`, nessuna riga se il dizionario è vuoto);
    - `insert_packets(rows: list[dict]) -> None` (chiavi = colonne di `packets` senza `id`; `receptions` e `summary` già in JSON, `raw` in bytes);
    - `upsert_stats_hourly(rows: list[tuple[int, str, str, int, int]]) -> None` (time, source, kind, packets, receptions: somma in conflitto);
    - `upsert_node_hourly(rows: list[tuple[int, int, str, int, float, int, float | None]]) -> None` (time, node_num, source, packets, snr_sum, snr_n, snr_max: somme in conflitto, `snr_max` = massimo ignorando NULL);
    - `trim_packets(max_rows: int, limit: int) -> int` (righe cancellate).
  - Impostazioni: `DEFAULTS["packet_log_mode"] = "archived"`, `DEFAULTS["retention_packets_hours"] = 48`. `_RANGE_KEYS["retention_packets_hours"] = (1, 168)`. Il ramo di `_validate` per `packet_log_mode` accetta solo `"off"`, `"archived"` e `"all"`, altrimenti `ValueError("packet_log_mode deve essere off, archived oppure all")`.
  - `maintenance.TABLES` aggiunge `"metrics"` e `"packets"`.

Regole della pulizia in `purge_step` (stesso schema di cancellazione a blocchi per rowid):
- `metrics` e `stats_hourly` con il limite di `retention_telemetry_days`;
- `node_hourly` con il limite di `retention_positions_days`;
- `packets` con `now - retention_packets_hours * 3600`.

`deleted` aggiunge le chiavi `"metrics"` e `"packets"`; le tabelle orarie non entrano nel conteggio, come oggi `links`. Nel ramo del limite di spazio si cancellano per primi i `packets` più vecchi, poi `positions` e `messages`. `purge()` somma le chiavi che arrivano dal passo (`total.get(k, 0) + v`): oggi parte da quattro chiavi fisse e darebbe `KeyError`.

`trim_packets`: `SELECT id FROM packets ORDER BY id DESC LIMIT 1 OFFSET ?` (max_rows); se esiste, `DELETE FROM packets WHERE id IN (SELECT id FROM packets WHERE id <= ? ORDER BY id LIMIT ?)`.

- [ ] **Step 0:** verificare che in `db.py` valga `SCHEMA_VERSION == 4`; altrimenti fermarsi e segnalarlo.
- [ ] **Step 1: test che falliscono:**
  - `test_db.py::test_new_db_is_v5_with_new_tables`: `schema_version(conn) == 5`; `metrics`, `packets`, `stats_hourly` e `node_hourly` presenti in `sqlite_master`, con gli indici elencati sopra.
  - `test_db.py::test_v4_db_migrates_to_5_without_touching_telemetry`: un file a versione 4 con 3 righe in `telemetry`; `connect(path, hook)` → hook chiamato con `(conn, 4, 5)`, le 3 righe restano, la versione è 5; alla seconda `connect` l'hook non viene chiamato.
  - `test_store.py::test_add_metrics_and_empty_noop`: `add_metrics(1, 10.0, "environment", {"temperature": 21.5, "relative_humidity": 40.0})` → 2 righe; `{}` → nessuna riga.
  - `test_store.py::test_upsert_hourly_sums_and_max`: due upsert di `(3600, 1, "mqtt", 2, -10.0, 2, -4.0)` e `(3600, 1, "mqtt", 1, -2.0, 1, None)` → `packets == 3`, `snr_sum == -12.0`, `snr_n == 3`, `snr_max == -4.0`; `stats_hourly` somma `packets` e `receptions`.
  - `test_store.py::test_trim_packets_respects_cap`: 25 pacchetti, `trim_packets(10, 4)` → 4 cancellati, restano gli id più alti; ripetendo fino a 0 restano 10 righe.
  - `test_store.py::test_purge_covers_new_tables`: righe scadute in `metrics`, `packets` (più vecchie di 48 h), `stats_hourly` e `node_hourly` → `purge()` le cancella; `deleted` contiene `metrics` e `packets`; i test `test_purge_*` esistenti restano verdi.
  - `test_settings.py::test_packet_log_settings_validation`: `"all"` accettato; `"tutto"` → ValueError; `retention_packets_hours` 0 e 169 → ValueError; i default valgono `"archived"` e 48.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_db.py server/tests/test_store.py server/tests/test_settings.py` → FAIL.
- [ ] **Step 3:** implementare come sopra.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): migrazione 5 con metriche, pacchetti e aggregati orari; pulizia estesa`.

### Task 2: Telemetria di tutte le varianti (MQTT e radio)  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/telemetry_decode.py`
- Modify: `server/meshlens/events.py` (solo `TelemetryData`), `server/meshlens/mqtt_decode.py` (solo `_parse_telemetry`), `server/meshlens/rf_convert.py` (solo il ramo `TELEMETRY_APP`), `server/meshlens/ingest.py` (solo la telemetria)
- Test: `server/tests/test_telemetry_decode.py` (nuovo), `server/tests/test_mqtt_decode.py`, `server/tests/test_rf_convert.py`, `server/tests/test_ingest.py`

**Interfaces:**
- Consumes: `Store.add_metrics` (Task 1).
- Produces:
  - `TelemetryData` aggiunge `variant: str = "device"` e `metrics: dict[str, float] = field(default_factory=dict)`.
  - In `telemetry_decode.py`:
    - `VARIANTS = {"device_metrics": "device", "environment_metrics": "environment", "air_quality_metrics": "air_quality", "power_metrics": "power", "local_stats": "local_stats", "health_metrics": "health"}`;
    - eccezioni `UnsupportedTelemetry` ed `EmptyTelemetry`;
    - `parse_telemetry_msg(tel: telemetry_pb2.Telemetry) -> TelemetryData`;
    - `parse_telemetry(payload: bytes) -> TelemetryData`;
    - `telemetry_from_dict(d: dict) -> TelemetryData` (con `json_format.ParseDict(d, Telemetry(), ignore_unknown_fields=True)`).
  - `Ingestor._telemetry_time` passa a chiavi `(num, variant)`.

Regole di `parse_telemetry_msg`:
- `device`: campi storici come oggi, `metrics = {}`.
- Altre varianti di `VARIANTS`: `metrics` = i campi impostati (`ListFields()`) di tipo numerico, con valore finito (`math.isfinite`), convertiti in `float`, con il nome del campo protobuf come chiave. Dizionario vuoto → `EmptyTelemetry`.
- Variante assente o fuori da `VARIANTS` → `UnsupportedTelemetry`.
- MQTT traduce le due eccezioni in `_Unsupported` e `_Empty`, così i contatori `drops` restano quelli di oggi.
- RF: se `decoded["payload"]` sono bytes usa `parse_telemetry`, altrimenti `telemetry_from_dict(decoded["telemetry"])`; le due eccezioni → `None`. `nodedb_to_events` resta com'è (solo `deviceMetrics`).

In `ingest.py`, solo il ramo `kind == "telemetry"`:
- il controllo "stale" e `_telemetry_time` usano `(num, p.variant)`;
- `_update_telemetry` e il ramo `no_time` valgono solo per `variant == "device"`;
- in persistenza: `device` → `add_telemetry` come oggi, altre varianti → `add_metrics(num, ev.rx_time, p.variant, p.metrics)`.

- [ ] **Step 1: test che falliscono:**
  - `test_telemetry_decode.py`:
    - `test_environment_metrics`: `Telemetry(environment_metrics=EnvironmentMetrics(temperature=21.5, relative_humidity=40, barometric_pressure=1013.2))` → `variant == "environment"` e `metrics == {"temperature": 21.5, "relative_humidity": 40.0, "barometric_pressure": pytest.approx(1013.2)}`.
    - `test_local_stats_counts`: `LocalStats(num_packets_rx=100, num_rx_dupe=12, noise_floor=-110)` → `metrics["num_rx_dupe"] == 12.0` e `metrics["noise_floor"] == -110.0`.
    - `test_air_quality_and_power_and_health`: un campo per variante → varianti `"air_quality"`, `"power"`, `"health"`.
    - `test_nan_dropped_and_empty_raises`: `temperature=float("nan")` da solo → `EmptyTelemetry`.
    - `test_unsupported_variants`: `host_metrics` e Telemetry vuoto → `UnsupportedTelemetry`.
    - `test_device_unchanged`: `device_metrics(battery_level=87, voltage=4.01)` → `battery_level == 87`, `variant == "device"`, `metrics == {}`.
    - `test_from_dict_camelcase`: `telemetry_from_dict({"environmentMetrics": {"temperature": 20.0, "relativeHumidity": 55.0}})` → `metrics == {"temperature": 20.0, "relative_humidity": 55.0}`.
  - `test_mqtt_decode.py::test_environment_telemetry_decoded`: evento `kind == "telemetry"` con `variant == "environment"`; `test_host_metrics_counted_unsupported`: `None` e `stats["unsupported_port"] == 1`.
  - `test_rf_convert.py`: aggiornare `test_telemetry_without_device_metrics`, perché con `environmentMetrics` nel dict ora esce un evento `variant == "environment"`; un dict `telemetry` vuoto → `None`. Nuovo `test_telemetry_from_payload_bytes`.
  - `test_ingest.py::test_environment_telemetry_stored_as_metrics`: un nodo in una nazione salvata riceve una telemetria ambientale → 0 nuove righe in `telemetry`, 2 in `metrics`, `battery` e `voltage` del nodo invariati. Poi `test_device_after_environment_not_stale`: una telemetria `device` con `rx_time` minore di quella ambientale viene comunque applicata.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_telemetry_decode.py server/tests/test_mqtt_decode.py server/tests/test_rf_convert.py server/tests/test_ingest.py` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): telemetria ambientale, qualità dell'aria, potenza, statistiche locali e salute`.

### Task 3: Metadati dei pacchetti e pacchetti non decodificati  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/events.py`, `server/meshlens/mqtt_decode.py`, `server/meshlens/mqtt_client.py` (solo `_on_message`), `server/meshlens/rf_convert.py`, `server/meshlens/radio.py` (solo `on_packet`), `server/meshlens/ingest.py` (solo inizio di `handle` e un metodo pubblico)
- Test: `server/tests/test_mqtt_decode.py`, `server/tests/test_mqtt_client.py`, `server/tests/test_rf_convert.py`, `server/tests/test_radio.py`, `server/tests/test_ingest.py`

**Interfaces:**
- Produces in `events.py`:
  ```python
  RAW_MAX = 256

  @dataclass
  class PacketMeta:
      portnum: str | None          # "TEXT_MESSAGE_APP"; None se non decifrato
      hop_start: int | None
      hop_limit: int | None
      want_ack: bool = False
      encrypted: bool = False      # arrivato cifrato
      raw: bytes = b""             # Data.payload decifrato, altrimenti i byte cifrati; max RAW_MAX

  @dataclass
  class RawPacket:                 # pacchetto ricevuto ma non trasformato in MeshEvent
      source: str; from_node: int; to_node: int; packet_id: int; channel: str
      rx_time: float; snr: float | None; rssi: int | None; gateway_id: str | None
      radio_id: str | None; broker: str | None; relay_node: int | None
      status: str                  # "encrypted" | "unsupported" | "undecodable" | "empty"
      meta: PacketMeta
  ```
  `MeshEvent` aggiunge `meta: PacketMeta | None = None` in fondo.
- `EnvelopeDecoder`:
  - attributo `raw_filter: Callable[[int], bool] | None = None`;
  - `decode_any(topic, payload, now) -> MeshEvent | RawPacket | None`;
  - `decode()` resta e restituisce solo i `MeshEvent` (`ev if isinstance(ev, MeshEvent) else None`).
  - Gli stessi contatori `stats` di oggi, per ogni caso.
  - Un `RawPacket` esce solo se il `ServiceEnvelope` contiene un `packet` **e** `raw_filter` non è `None` **e** `raw_filter(from_node)` è vero; `json_topic` e `not_protobuf` danno sempre `None`.
  - `status`: `"encrypted"` quando nessuna chiave decifra; `"unsupported"` per `_Unsupported`, con il `portnum` noto; `"empty"` per `_Empty`; `"undecodable"` per le altre eccezioni.
- `MqttConnector._on_message` usa `decode_any` e mette in `inbox` sia `MeshEvent` sia `RawPacket`.
- `rf_convert.py`:
  - `packet_to_event` riempie `meta` (`portnum` = `decoded["portnum"]`, `hop_start`/`hop_limit` da `hopStart`/`hopLimit`, `want_ack` da `wantAck`, `raw` = `bytes(decoded.get("payload") or b"")[:RAW_MAX]`);
  - `packet_to_raw(packet: dict, radio_id: str, now: float) -> RawPacket` (`status` = `"unsupported"` se c'è `decoded`, altrimenti `"encrypted"` con `raw` = i byte di `packet["encrypted"]` se presenti).
- `RadioConnector.on_packet`: se non nasce un `MeshEvent`, compreso il caso `ROUTING_APP` dopo `_handle_routing`, emette `packet_to_raw(...)` con lo stesso `self._emit(self._on_event, …)`.
- `Ingestor`:
  - `handle` comincia con `if not isinstance(ev, MeshEvent): self.last_outcome = "ignored"; return`;
  - `last_outcome: str` vale `"ignored"` (canale filtrato), `"dup"` (copia) o `"new"`, e si imposta nei tre punti già esistenti;
  - `is_archived(num: int) -> bool`: l'attuale `_persisted` reso pubblico; `_persisted` resta come alias.

- [ ] **Step 1: test che falliscono:**
  - `test_mqtt_decode.py::test_meta_filled_for_decrypted_packet`: `ev.meta.portnum == "TEXT_MESSAGE_APP"`, `ev.meta.encrypted is True`, `ev.meta.raw == b"ciao"`, `ev.meta.hop_start` uguale a quello dell'envelope.
  - `test_mqtt_decode.py::test_decode_any_raw_only_with_filter`: un pacchetto con chiave sconosciuta → con `raw_filter=None` `decode_any` dà `None`; con `raw_filter=lambda n: True` dà un `RawPacket` con `status == "encrypted"`, `len(meta.raw) <= 256`, `stats["undecodable"] == 2` dopo le due chiamate; `decode()` dà sempre `None`.
  - `test_mqtt_decode.py::test_decode_any_unsupported_has_portnum`: portnum 5 → `RawPacket.status == "unsupported"`, `meta.portnum == "ROUTING_APP"`.
  - `test_mqtt_client.py::test_raw_packet_goes_to_inbox`: con `raw_filter` vero il `RawPacket` arriva al gestore.
  - `test_rf_convert.py::test_packet_to_raw_and_meta`: un dict con `portnum` `"ADMIN_APP"` → `packet_to_event` dà `None` e `packet_to_raw` dà `status == "unsupported"`; per un testo `meta.raw == b"ciao"`.
  - `test_radio.py::test_unhandled_packet_emits_raw`: `on_packet` con `ADMIN_APP` → l'`on_event` finto riceve un `RawPacket`.
  - `test_ingest.py::test_last_outcome_and_raw_guard`: primo evento → `"new"`; stessa copia → `"dup"`; canale filtrato → `"ignored"`; un `RawPacket` passato a `handle` → nessuna eccezione, `"ignored"`, nessun nodo creato.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_mqtt_decode.py server/tests/test_mqtt_client.py server/tests/test_rf_convert.py server/tests/test_radio.py server/tests/test_ingest.py` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): metadati dei pacchetti e pacchetti non decodificati per l'ispettore`.

### Task 4: `PacketLog`, `NetStats` e collegamento nel Runtime  _(modello: opus)_

**Files:**
- Create: `server/meshlens/packet_log.py`, `server/meshlens/netstats.py`
- Modify: `server/meshlens/app.py` (`build`: `on_event`; `Runtime`: task periodici, `raw_filter`, `stop`, `start_connector`)
- Test: `server/tests/test_packet_log.py` (nuovo), `server/tests/test_netstats.py` (nuovo), `server/tests/test_app.py`

**Interfaces:**
- Consumes: `Store.insert_packets`, `upsert_stats_hourly`, `upsert_node_hourly`, `trim_packets` (Task 1); `MeshEvent.meta`, `RawPacket`, `Ingestor.last_outcome`, `is_archived`, `EnvelopeDecoder.raw_filter` (Task 3).
- Produces:
  - `packet_log.py`: costanti `HOLD_S = 5.0`, `BUFFER_MAX = 20_000`, `FLUSH_MAX = 2000`, `MAX_RECEPTIONS = 8`, `PACKETS_MAX_ROWS = 300_000`, `SUMMARY_MAX = 2000`.
    - `summarize(ev: MeshEvent) -> dict`: `dataclasses.asdict(ev.payload)`, con bytes → esadecimale e `text` tagliato a 200 caratteri.
    - `class PacketLog(store: Store, get_mode: Callable[[], str], clock=time.time)` con:
      - `dropped: int`;
      - `observe(ev: MeshEvent, outcome: str, archived: bool) -> None`;
      - `observe_raw(raw: RawPacket, archived: bool) -> None`;
      - `flush(now: float | None = None, force: bool = False) -> int`.
  - `netstats.py`: `class NetStats(store: Store)` con `observe(ev: MeshEvent, outcome: str, archived: bool) -> None` e `flush() -> int`.
  - `app.py`:
    - `Runtime.packet_log`, `Runtime.netstats`;
    - `Runtime.raw_filter(num: int) -> bool`;
    - `Runtime.refresh_archived() -> None` (ogni 60 s ricostruisce un `frozenset` dei nodi in memoria con `ingestor.is_archived`; si sostituisce con un'assegnazione unica e il thread paho lo legge senza lock);
    - `async Runtime.trim_packets() -> int`.
    - `start_connector` imposta `decoder.raw_filter = self.raw_filter`.
    - Task periodici: `_every(2, packet_log.flush)`, `_every(60, netstats.flush)`, `_every(60, refresh_archived, first_now=True)`, `_every_async(60, trim_packets, 60)`.
    - `stop()`: `packet_log.flush(force=True)` e `netstats.flush()` prima dell'ultimo commit.

Regole di `PacketLog`:
- Con mode `"off"` non fa nulla. Con `"archived"` tiene solo ciò che ha `archived` vero; con `"all"` tiene tutto.
- Ignora `outcome == "ignored"`, `packet_id == 0` e `rx_time <= 0` (replay del database nodi).
- Buffer: `dict[(from, packet_id)] -> voce`, in ordine d'inserimento.
  - Con `"new"` si crea la voce con i dati della prima ricezione: `status="ok"`, `kind=ev.kind`, `portnum`/`hop_*`/`raw` da `meta`, `summary=json(summarize)` tagliato a `SUMMARY_MAX`, `size=len(raw)`, `receptions=[prima]`.
  - Con `"dup"`, se la voce è nel buffer: `copies += 1` e la ricezione si aggiunge (al massimo `MAX_RECEPTIONS`). Una copia tardiva, già scritta, viene ignorata.
  - `observe_raw`: crea la voce con `raw.status` e `kind=None`; se la chiave esiste già aggiunge solo la ricezione.
  - Oltre `BUFFER_MAX` si toglie la voce più vecchia e si fa `dropped += 1`.
- `flush` scrive con `insert_packets` le voci più vecchie di `HOLD_S` (tutte con `force`), al massimo `FLUSH_MAX` per chiamata, poi le toglie dal buffer. Il commit lo fa il task esistente `_every(1, store.commit)`.
- `raw_filter(num)`: `False` con mode `"off"`, `True` con `"all"`, con `"archived"` `num in self._archived`.

Regole di `NetStats`:
- Ignora gli stessi casi di `PacketLog`.
- `hour = int(ev.rx_time // 3600) * 3600`.
- `stats_hourly[(hour, source, kind)]`: `receptions += 1` sempre, `packets += 1` solo con `"new"`.
- Se `archived`, `node_hourly[(hour, from, source)]`: `packets += 1` solo con `"new"`; `snr_sum`, `snr_n` e `snr_max` per ogni ricezione con `snr` non `None`.
- `flush` passa i contatori a `upsert_*` e li azzera.

`on_event` in `build`:
```python
def on_event(ev) -> None:
    if isinstance(ev, RawPacket):
        packet_log.observe_raw(ev, ev.source == "rf" or ingestor.is_archived(ev.from_node))
        return
    ingestor.handle(ev)
    coverage.handle(ev)
    outcome, archived = ingestor.last_outcome, ev.source == "rf" or ingestor.is_archived(ev.from_node)
    try:
        netstats.observe(ev, outcome, archived)
        packet_log.observe(ev, outcome, archived)
    except Exception:
        log.exception("Osservatori dei pacchetti")  # mai a scapito dell'ingestione
```

- [ ] **Step 1: test che falliscono:**
  - `test_packet_log.py`:
    - `test_new_and_dup_merge_into_one_row`: un evento `"new"` e due `"dup"` dello stesso `(from, id)` da gateway diversi, poi `flush(now + 6)` → 1 riga, `copies == 3`, 3 ricezioni nel JSON.
    - `test_late_dup_ignored`: dopo il flush un `"dup"` non crea righe.
    - `test_hold_window`: `flush(now + 1)` → 0 righe scritte.
    - `test_modes`: `"off"` → 0 righe; `"archived"` con `archived=False` → 0; `"all"` → 1.
    - `test_raw_packet_row`: `observe_raw` → riga con `status == "encrypted"`, `kind is None`, `raw` di 256 byte al massimo.
    - `test_flush_max_per_call`: 2500 voci scadute → il primo flush ne scrive 2000, il secondo 500.
    - `test_buffer_overflow_drops_oldest` (con `BUFFER_MAX` a 10 via monkeypatch): 12 voci → `dropped == 2`, la voce più vecchia è assente.
    - `test_skips_nodedb_replay`: `packet_id == 0` → nulla.
  - `test_netstats.py`:
    - `test_hourly_counts`: 2 `"new"` + 1 `"dup"` nella stessa ora → `stats_hourly`: `packets == 2`, `receptions == 3`.
    - `test_node_hourly_only_archived_and_snr`: un nodo archiviato con SNR −5 e −3 → `snr_n == 2`, `snr_max == -3`; un nodo non archiviato → nessuna riga in `node_hourly`.
    - `test_flush_resets`: un secondo `flush` senza eventi → 0.
  - `test_app.py`:
    - `test_trim_packets_chunks_and_yields`: con `PACKETS_MAX_ROWS` a 100 e `PURGE_CHUNK` a 50 (monkeypatch) e 400 righe, un contatore concorrente avanza durante `await rt.trim_packets()` e alla fine restano 100 righe.
    - `test_on_event_routes_raw_packets`: un `RawPacket` passato a `rt.on_event` non arriva all'`Ingestor` e, con mode `"all"`, dopo `flush(force=True)` c'è una riga in `packets`.
    - `test_raw_filter_follows_mode`: `"off"` → False; `"all"` → True; `"archived"` → True solo per un nodo is_mine dopo `refresh_archived()`.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_packet_log.py server/tests/test_netstats.py server/tests/test_app.py` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): registro dei pacchetti deduplicati e aggregati orari, con limiti di spazio`.

### Task 5: Letture fuori dal loop — serie, metriche, SNR, percorso  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/queries.py`, `server/meshlens/api_data.py`
- Modify: `server/meshlens/api.py` (toglie le rotte `/positions` e `/telemetry` dei nodi e chiama `register_data_routes(app, ctx, require_auth)`)
- Test: `server/tests/test_queries.py` (nuovo), `server/tests/test_api.py`

**Interfaces:**
- Consumes: le tabelle del Task 1.
- Produces in `queries.py`:
  - `ro_connect(db_path: Path) -> sqlite3.Connection` (`row_factory = sqlite3.Row`);
  - `bucket_rows(rows: list[dict], keys: tuple[str, ...], max_points: int, tkey: str = "time") -> list[dict]`;
  - `telemetry_series(conn, num: int, since: float, max_points: int = 800) -> list[dict]`;
  - `metric_series(conn, num: int, since: float, max_points: int = 800) -> dict`;
  - `snr_series(conn, num: int, since: float) -> list[dict]`;
  - `track(conn, num: int, since: float, max_points: int = 5000) -> list[dict]`.
- Produces in `api_data.py`:
  - `async run_read(ctx: AppContext, fn: Callable[[sqlite3.Connection], T]) -> T`;
  - `register_data_routes(app: FastAPI, ctx: AppContext, require_auth) -> None`, con le rotte `telemetry`, `positions`, `metrics`, `snr` dei Contratti JSON. `hours` si valida con `Query(…, gt=0, le=8784)`; 404 «Nodo non trovato» per la telemetria se il nodo non è in memoria, come oggi.

Algoritmi:
- `bucket_rows`: se `len(rows) <= max_points` restituisce le righe come sono. Altrimenti divide `[t_primo, t_ultimo]` in `max_points` intervalli uguali; per ogni intervallo non vuoto esce una riga con `time` = media dei tempi e, per ogni chiave, la media dei valori non `None` (`None` se mancano tutti).
- `track`: con n righe e `n > max_points`, `k = ceil(n / max_points)`; tiene le righe di indice `i % k == 0` e sempre l'ultima.
- `metric_series`:
  - `latest` con `SELECT variant, metric, value, MAX(time) … WHERE node_num=? GROUP BY variant, metric`;
  - `series` con una query ordinata per `(variant, metric, time)` dopo `since`, poi `bucket_rows` per serie;
  - le chiavi sono `"<variant>.<metric>"`.
- `snr_series`: `snr_avg = snr_sum / snr_n` (`None` se `snr_n == 0`), ordinato per `time, source`.

- [ ] **Step 1: test che falliscono:**
  - `test_queries.py`:
    - `test_bucket_rows_average_and_nulls`: 10 righe con `battery` 0..9 e `voltage` sempre `None`, `max_points=5` → 5 righe, `battery` della prima = 0,5, `voltage is None`;
    - `test_bucket_rows_passthrough`;
    - `test_track_decimates_keeping_ends`: 260 000 righe sintetiche, `max_points=5000` → `len <= 5001`, primo e ultimo tempo uguali a quelli dell'input;
    - `test_metric_series_latest_all_time`: un valore di 200 giorni fa compare in `latest` ma non in `series` con `since` a 7 giorni;
    - `test_snr_series_avg`: `snr_sum=-12`, `snr_n=3` → `snr_avg == -4.0`.
  - `test_api.py`:
    - `test_telemetry_route` esistente invariato;
    - `test_positions_route_max_points` (`make_ctx`, 50 posizioni, `?hours=24&max_points=10` → al massimo 11 elementi con le chiavi di oggi);
    - `test_metrics_and_snr_routes` (forma `{latest, series}`; lista vuota per `snr` senza dati);
    - `test_data_routes_use_thread_with_db_path` (`build(tmp_path)`, una riga inserita e committata, `GET /api/nodes/!…/metrics` la restituisce; monkeypatch di `asyncio.to_thread` per verificare che sia chiamato);
    - `hours=0` → 422.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_queries.py server/tests/test_api.py` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): serie di telemetria, metriche, SNR e percorsi letti fuori dal loop`.

### Task 6: Statistiche della rete e ricerca nei pacchetti  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/queries.py`, `server/meshlens/api_data.py`
- Test: `server/tests/test_queries.py`, `server/tests/test_api.py`

**Interfaces:**
- Consumes: `ro_connect`, `run_read`, `register_data_routes` (Task 5); le tabelle del Task 1.
- Produces:
  - `SNR_BINS = [-20 + 2.5 * i for i in range(15)]` (da −20 a 15);
  - `network_stats(conn, now: float, hours: int) -> dict`, con la forma dei Contratti JSON;
  - `@dataclass PacketFilter(node: int | None = None, kind: str | None = None, source: str | None = None, status: str | None = None, min_snr: float | None = None, since: float | None = None, until: float | None = None)`;
  - `packet_list(conn, f: PacketFilter, limit: int, before_id: int | None) -> dict`;
  - `packet_detail(conn, pid: int) -> dict | None`;
  - rotte `GET /api/stats`, `GET /api/packets` e `GET /api/packets/{id}`;
  - cache delle statistiche in `api_data.py`: un dizionario `hours -> (calcolato_il, risultato)` con TTL `STATS_TTL_S = 60` e un `asyncio.Lock`, così due richieste uguali fanno un solo calcolo.

Contenuto di `network_stats` (`since = now - hours * 3600`, ore allineate):
- `online`: `COUNT(DISTINCT node_num)` per `time` da `node_hourly`;
- `packets`: righe di `stats_hourly` dopo `since`;
- `snr`: per nodo `SUM(snr_sum) / SUM(snr_n)` per `source` dopo `since`; si assegna al bin `max(i : SNR_BINS[i] <= v)`, con i valori sotto −20 nel primo bin e quelli oltre 15 nell'ultimo;
- `hops`, `hardware`, `roles`: dalla tabella `nodes` con `last_heard >= since`. `hops` va da 0 a 7, con `null` per sconosciuto; `hardware` sono i 12 modelli più frequenti più `other_hardware`; `roles` tutti;
- `top`: i 10 nodi con più `SUM(packets)` in `node_hourly`, con `name` = `long_name` o l'id e `per_hour = packets / hours`;
- `totals`: nodi distinti in `node_hourly` e somma dei `packets` di `stats_hourly`.

Contenuto di `packet_list`:
- `node` confronta `from_num` **o** `to_num`;
- ordine `id DESC` e `id < before_id` se dato;
- `limit` tagliato a 200;
- `next_before_id` = id dell'ultimo elemento se ne sono usciti `limit`, altrimenti `null`;
- `from_name` da `LEFT JOIN nodes`;
- `from` e `to` come `!hex`.

`packet_detail` aggiunge `receptions` (JSON letto), `summary` (JSON letto o `null`) e `raw_hex` (`raw.hex()`, `""` se `NULL`).

- [ ] **Step 1: test che falliscono:**
  - `test_queries.py`:
    - `test_network_stats_shapes`: dati sintetici con 3 nodi in 2 ore, `stats_hourly` con 2 tipi → `online == [{time: h0, nodes: 2}, {time: h1, nodes: 3}]`; `top[0]` è il nodo con più pacchetti; `snr.rf` ha la somma uguale al numero di nodi con SNR RF; un nodo con SNR −30 finisce nel bin 0;
    - `test_network_stats_window`: righe più vecchie di `hours` escluse;
    - `test_packet_list_filters_and_cursor`: 250 righe → la prima pagina ne ha 100 e `next_before_id` = id della centesima; filtri `kind="text"`, `source="rf"`, `min_snr=-5`, `node` (`from` o `to`) e `since` applicati;
    - `test_packet_detail_hex_and_json`: `raw=b"\x01\xff"` → `raw_hex == "01ff"`, `receptions` è una lista.
  - `test_api.py`:
    - `test_stats_route_cached` (`build(tmp_path)`; due `GET /api/stats?hours=24` → `network_stats` chiamata una volta, via monkeypatch);
    - `test_stats_hours_bounds` (0 e 2161 → 422);
    - `test_packets_routes` (lista; dettaglio 404 per un id assente; `limit=500` → al massimo 200).
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_queries.py server/tests/test_api.py` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): statistiche della rete e ricerca nell'ispettore dei pacchetti`.

### Task 7: Interfaccia — grafici con lettura al passaggio, periodo e sensori  _(modello: sonnet)_

**Files:**
- Create: `web/src/components/charts/LineChart.svelte`, `web/src/components/NodeCharts.svelte`, `web/src/lib/metrics.ts`, `web/src/lib/metrics.test.ts`
- Modify: `web/src/lib/chart.ts`, `web/src/lib/chart.test.ts`, `web/src/lib/api.ts`, `web/src/lib/types.ts`, `web/src/components/NodeDetail.svelte` (solo l'import e l'uso del grafico)
- Delete: `web/src/components/TelemetryChart.svelte`

**Interfaces:**
- Consumes: le rotte `telemetry`, `metrics` e `snr` (Task 5).
- Produces:
  - `chart.ts`:
    - `nearestIndex(ts: number[], t: number): number` (ricerca binaria su `ts` ordinato; −1 se vuoto);
    - `chartTime(t: number, spanHours: number): string` (`it-IT`: fino a 48 h «14:05», oltre «21 nov, 14:05»);
    - `pctRange(values: number[]): [number, number]` (`[0, max(10, ceil(max/10)*10)]`).
  - `types.ts`: `MetricsResponse = {latest: Record<string, {value: number; time: number}>; series: Record<string, [number, number][]>}`, `SnrPoint = {time: number; source: 'rf' | 'mqtt'; snr_avg: number | null; snr_max: number | null; packets: number}`.
  - `api.ts`: `metrics(id: string, hours: number): Promise<MetricsResponse>`, `snr(id: string, hours: number): Promise<SnrPoint[]>`.
  - `metrics.ts`:
    - `METRIC_INFO: Record<string, {label: string; unit: string; digits: number; chart?: boolean}>`;
    - `metricInfo(key: string)`, con il ripiego `{label: key, unit: '', digits: 2, chart: true}`;
    - `orderMetrics(keys: string[]): string[]` (ordine delle varianti environment, air_quality, power, health, local_stats, poi l'ordine del catalogo, poi alfabetico);
    - `formatMetric(key: string, value: number): string` (con `num()` di `format.ts` e l'unità);
    - `dupeRatio(latest: MetricsResponse['latest']): number | null` = `local_stats.num_rx_dupe / local_stats.num_packets_rx`, `null` se il secondo manca o vale 0.
  - Catalogo minimo (testi esatti):
    - **ambiente:** `environment.temperature` «Temperatura» °C 1; `relative_humidity` «Umidità relativa» % 0; `barometric_pressure` «Pressione» hPa 1; `gas_resistance` «Resistenza del gas» MΩ 2; `iaq` «Indice qualità dell'aria (IAQ)» 0; `lux` «Luminosità» lx 0; `wind_speed` «Velocità del vento» m/s 1; `wind_direction` «Direzione del vento» ° 0; `rainfall_1h` «Pioggia (1 h)» mm 1; `rainfall_24h` «Pioggia (24 h)» mm 1; `voltage` «Tensione» V 2; `current` «Corrente» mA 1;
    - **qualità dell'aria:** `air_quality.pm10_standard` «PM1,0» µg/m³ 0; `pm25_standard` «PM2,5» µg/m³ 0; `pm100_standard` «PM10» µg/m³ 0; `co2` «CO₂» ppm 0;
    - **potenza:** `power.ch1_voltage` «Canale 1, tensione» V 2; `ch1_current` «Canale 1, corrente» mA 1; idem per i canali 2 e 3;
    - **salute:** `health.heart_bpm` «Battito» bpm 0; `spO2` «Saturazione» % 0; `temperature` «Temperatura corporea» °C 1;
    - **statistiche locali:** `local_stats.num_packets_tx` «Pacchetti trasmessi»; `num_packets_rx` «Pacchetti ricevuti»; `num_packets_rx_bad` «Pacchetti ricevuti con errori»; `num_rx_dupe` «Duplicati ricevuti»; `num_online_nodes` «Nodi online»; `num_total_nodes` «Nodi conosciuti»; `num_tx_relay` «Ritrasmessi»; `num_tx_relay_canceled` «Ritrasmissioni annullate»; `noise_floor` «Rumore di fondo» dBm 0; `uptime_seconds`, `heap_total_bytes` e `heap_free_bytes` con `chart: false`.
  - `LineChart.svelte`, con le props:
    ```ts
    {
      series: {
        key: string; label: string; unit: string; digits: number;
        color: 'accent' | 'ok' | 'warn' | 'danger' | 'sky' | 'teal' | 'amber' | 'radio' | 'mqtt';
        dash?: boolean; axis?: 'left' | 'right'; points: Pt[];
      }[];
      x0: number; x1: number;
      left?: [number, number]; right?: [number, number];
      threshold?: { value: number; label: string };
      height?: number;   // predefinita 120
      label: string;     // aria-label
    }
    ```
    - colori da una mappa costante verso `var(--accent)`, `var(--ok)`, `var(--warn)`, `var(--danger)`, `var(--brand-sky)`, `var(--brand-teal)`, `var(--brand-amber)`, `var(--src-radio)` e `var(--src-mqtt)`;
    - assi automatici con `niceRange` se mancano `left` o `right`;
    - linee con `linePath` e punti isolati con `isolatedPoints`, come oggi;
    - **lettura:** `pointermove` e `pointerdown` sull'SVG → tempo → `nearestIndex` per serie → linea verticale più un riquadro HTML sopra il grafico con `chartTime` e, per ogni serie, «etichetta: valore unità» (`num()` e «−»); `pointerleave` lo nasconde;
    - **tastiera:** l'SVG ha `tabindex="0"`; ←/→ spostano il cursore sui tempi della prima serie con dati, Esc lo nasconde;
    - legenda sotto il grafico come oggi.
  - `NodeCharts.svelte` (`{nodeId: string}`):
    - periodi «24 h», «7 g», «30 g», «90 g» (24, 168, 720, 2160 ore);
    - tre richieste in parallelo con controllo di `nodeId` e periodo all'arrivo, come oggi;
    - sezioni, mostrate solo se hanno dati:
      - «Batteria e tensione» (batteria `ok` sull'asse sinistro 0–100 con la soglia `battery_alert_pct`, tensione `accent` tratteggiata sull'asse destro);
      - «Uso del canale e trasmissione» (`channel_util` `accent` e `air_util_tx` `amber` tratteggiata, asse `pctRange`);
      - «Segnale (SNR)» (`snr_avg` RF `radio`, MQTT `mqtt` tratteggiata, unità dB);
      - «Sensori»: un `<dl>` «Ultimi valori» (`orderMetrics` delle chiavi di `latest`, con `formatMetric` e il tempo con `ago`), più la riga «Duplicati ricevuti: N %» se `dupeRatio` non è `null`, poi un `LineChart` per ogni serie con `chart !== false`, al massimo 8;
    - «Nessun dato nel periodo» se tutte le sezioni sono vuote; «Dati non disponibili» se una richiesta fallisce.

- [ ] **Step 1: test che falliscono:**
  - `chart.test.ts`:
    - `nearestIndex([10, 20, 30], 24) === 1`, `nearestIndex([10, 20, 30], 26) === 2`, `nearestIndex([], 5) === -1`;
    - `chartTime` con un tempo fisso e span 24 → «HH:MM»; span 200 → contiene il mese abbreviato;
    - `pctRange([3, 7]) == [0, 10]`, `pctRange([42]) == [0, 50]`, `pctRange([]) == [0, 10]`.
  - `metrics.test.ts`:
    - `metricInfo('environment.temperature').label === 'Temperatura'`;
    - una chiave sconosciuta → `label` uguale alla chiave;
    - `orderMetrics(['local_stats.num_rx_dupe', 'air_quality.co2', 'environment.temperature'])` → ambiente, aria, locali;
    - `formatMetric('environment.temperature', -3.25) === '−3,3 °C'`;
    - `dupeRatio({'local_stats.num_rx_dupe': {value: 12, time: 0}, 'local_stats.num_packets_rx': {value: 100, time: 0}}) === 0.12`; senza `num_packets_rx` → `null`.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/chart.test.ts src/lib/metrics.test.ts` → FAIL.
- [ ] **Step 3:** implementare `chart.ts`, `metrics.ts`, `api.ts` e `types.ts`; poi `LineChart.svelte` e `NodeCharts.svelte`; in `NodeDetail.svelte` `<NodeCharts nodeId={node.id} />` al posto di `TelemetryChart`; cancellare `TelemetryChart.svelte`.
- [ ] **Step 4:** stesso comando → PASS; `cd web && npm run check` → 0 errori.
- [ ] **Step 5: Commit** `feat(web): grafici con lettura al passaggio, periodo a scelta, uso del canale, SNR e sensori`.

### Task 8: Interfaccia — esportazioni e percorso con periodo a scelta  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/export.ts`, `web/src/lib/export.test.ts`, `web/src/lib/download.ts`
- Modify: `web/src/components/Network.svelte` (pulsante nella barra), `web/src/components/Coverage.svelte` (pulsanti nel dettaglio), `web/src/components/NodeDetail.svelte` (blocco del percorso)

**Interfaces:**
- Consumes: `coverageGeoJSON` (`lib/coverage.ts`); la rotta `positions` con `max_points` (Task 5).
- Produces in `export.ts`:
  - `csv(header: string[], rows: (string | number | null | undefined)[][]): string`: BOM U+FEFF, **separatore `;` e numeri con la virgola decimale (anche lat/lon)** — decisione del controller: Excel in italiano apre il file in colonne; righe CRLF; null/undefined → campo vuoto; un campo che contiene `;`, `"`, CR o LF va tra virgolette con `"` raddoppiate.
  - `networkCsv(nodes: Node[]): string`, con le colonne `id,nome,nome_breve,modello,ruolo,firmware,nazione,ultimo_contatto,batteria,tensione,snr,salti,uso_canale,tx_aria,lat,lon,fonti` (`ultimo_contatto` in ISO 8601 UTC, `fonti` unite da `+`).
  - `gpx(name: string, pts: {time: number; lat: number; lon: number}[]): string`: GPX 1.1 `creator="MeshLens"`, un `trk` con `name` e un `trkseg`, `trkpt lat/lon` con 7 decimali e `<time>` ISO; testo XML con l'escape di `& < > " '`.
  - `coverageGeoJSONFile(detail: CoverageDetail): string`: una `FeatureCollection` unica con `properties.kind` uguale a `"point"`, `"missing"`, `"track"` o `"base"`.
  - `snrClass(snr: number | null): 'good' | 'mid' | 'bad' | 'none'`, con le soglie di `snrColor` in `links.ts`: ≥ 0, ≥ −10, altrimenti, `null`.
  - `cssToKml(color: string): string`: `#rrggbb` (anche `#rgb`) → `ffbbggrr`; per un valore non valido `ff888888`.
  - `coverageKml(detail: CoverageDetail, colors: Record<'good' | 'mid' | 'bad' | 'none', string>): string`: `Document` con il nome della prova, uno `Style` per classe, un `Placemark` per punto con `<description>` «SNR {snr} dB, RSSI {rssi} dBm, salti {hops}, seq {seq}», `LineString` del percorso, `Point` della base.
  - `coverageCsv(detail: CoverageDetail): string`, con le colonne `seq,segmento,ora,lat,lon,snr,rssi,salti,distanza_m,stato`: `stato` vale `ricevuto` per i punti e `mancante` per `missing_points`; righe ordinate per `ora`.
  - `fileStamp(d: Date): string` (`AAAAMMGG` in ora locale) e `slug(s: string): string` (minuscole, solo `[a-z0-9-]`, trattini compressi, al massimo 40 caratteri, `"senza-nome"` se vuoto).
- Produces in `download.ts`: `downloadText(filename: string, mime: string, text: string): void` (`Blob` + `URL.createObjectURL` + `<a download>` + `revokeObjectURL` in un `setTimeout(…, 0)`).
- Nomi dei file:
  - `meshlens-rete-AAAAMMGG.csv` (`text/csv`);
  - `meshlens-percorso-<slug(nome breve o id)>-AAAAMMGG.gpx` (`application/gpx+xml`);
  - `meshlens-copertura-<id>-<slug(nome)>.geojson|kml|csv` (`application/geo+json`, `application/vnd.google-earth.kml+xml`, `text/csv`).

Interfaccia:
- **Rete:** pulsante «Esporta CSV» (icona `download`, già in `icons.ts`) nella `.bar`; esporta le righe mostrate, cioè filtrate e ordinate.
- **Copertura, dettaglio di una prova:** gruppo `role="group"` con `aria-label="Esporta"` e i pulsanti «GeoJSON», «KML» e «CSV». I colori del KML arrivano da `getComputedStyle(document.documentElement).getPropertyValue('--snr-good' …)`.
- **Dettaglio nodo, percorso:**
  - stato `trackHours` (predefinito 24) con i chip «24 h», «7 g», «30 g» e «90 g», visibili quando il percorso è mostrato; cambiando periodo si ricarica `positions?hours=…&max_points=5000`;
  - sotto i chip, la riga «{n} posizioni dal {data} al {data}» (`formatDate`);
  - pulsante «Esporta GPX» con le posizioni caricate;
  - con meno di 2 posizioni, il messaggio «Nessun percorso nel periodo scelto».

- [ ] **Step 1: test che falliscono** in `export.test.ts`:
  - `csv(['a', 'b'], [['x;y', 'di "lui"'], [1.5, null]])` → BOM + `a;b` CRLF `"x;y";"di ""lui"""` CRLF `1,5;` CRLF;
  - un nome con un a capo resta tra virgolette e su una riga logica;
  - `networkCsv` di un nodo con `last_heard` 0 → `1970-01-01T00:00:00.000Z` e `sources` `['rf', 'mqtt']` → `rf+mqtt`;
  - `gpx('A & <B>', pts)` contiene `<name>A &amp; &lt;B&gt;</name>`, i `trkpt` sono in ordine e `new DOMParser().parseFromString(out, 'application/xml')` non contiene `parsererror` (ambiente jsdom di vitest; se manca, controllare con una regex che non ci siano `&` senza escape);
  - `coverageGeoJSONFile` → `JSON.parse` ok, i `kind` presenti corrispondono ai dati, i punti senza coordinate sono saltati;
  - `cssToKml('#2e9d4b') === 'ff4b9d2e'`, `cssToKml('#abc') === 'ffccbbaa'`, `cssToKml('rosso') === 'ff888888'`;
  - `coverageKml` con un nome con emoji e `&` → XML valido, un `Placemark` per punto con coordinate, `styleUrl` `#snr-bad` per SNR −12;
  - `coverageCsv` → punti e mancanti in ordine di tempo, `stato` corretto;
  - `slug('Prova #1: Monte Bianco!') === 'prova-1-monte-bianco'`, `slug('') === 'senza-nome'`, `slug('x'.repeat(80)).length === 40`;
  - `fileStamp(new Date(2026, 10, 21)) === '20261121'`.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/export.test.ts` → FAIL.
- [ ] **Step 3:** implementare `export.ts` e `download.ts`, poi i tre componenti.
- [ ] **Step 4:** stesso comando → PASS; `cd web && npm run check` → 0 errori.
- [ ] **Step 5: Commit** `feat(web): esportazione CSV, GPX, GeoJSON e KML e percorso del nodo con periodo a scelta`.

### Task 9: Interfaccia — pagina Rete con viste e statistiche  _(modello: sonnet)_

**Files:**
- Create: `web/src/components/NetworkPage.svelte`, `web/src/components/NetworkStats.svelte`, `web/src/components/charts/BarChart.svelte`, `web/src/lib/netstats.ts`, `web/src/lib/netstats.test.ts`
- Modify: `web/src/App.svelte` (una riga: `<NetworkPage …>` al posto di `<Network …>`, più l'import), `web/src/lib/viewstate.ts`, `web/src/lib/viewstate.test.ts`, `web/src/lib/api.ts`, `web/src/lib/types.ts`

**Interfaces:**
- Consumes: `GET /api/stats` (Task 6); `LineChart.svelte` e `chartTime` (Task 7).
- Produces:
  - `viewstate.ts`: `ViewState.netView: 'nodes' | 'stats' | 'packets'`, predefinita `'nodes'`; un valore non valido diventa `'nodes'`.
  - `types.ts`: `NetworkStats`, con la forma dei Contratti JSON. `api.ts`: `networkStats(hours: number): Promise<NetworkStats>`.
  - `netstats.ts`:
    - `KIND_LABEL: Record<string, string>` (`text` «Messaggi», `position` «Posizioni», `nodeinfo` «Info nodo», `telemetry` «Telemetria», `mapreport` «Map report», `neighbors` «Vicini», `traceroute` «Traceroute», `rangetest` «Range test»);
    - `kindLabel(k: string): string`, con la chiave stessa come ripiego;
    - `packetsPerHour(rows: NetworkStats['packets']): {time: number; packets: number}[]` (somma per ora, ordinata);
    - `kindTotals(rows): {kind: string; packets: number; share: number}[]` (ordinata in modo decrescente, `share` tra 0 e 1);
    - `barRects(values: number[], w: number, h: number, gap = 2): {x: number; y: number; w: number; h: number}[]` (altezza proporzionale al massimo; tutti 0 → altezza 0);
    - `snrBinLabel(lo: number): string` (`-20` → «−20…−17,5»; l'ultimo bin → «≥ 15»).
  - `BarChart.svelte`: props `{bars: {label: string; values: number[]}[]; series: {label: string; color: 'radio' | 'mqtt' | 'accent'}[]; label: string; height?: number}`. Barre affiancate per serie, lettura al passaggio, al tocco e da tastiera come `LineChart`, colori dai token.
  - `NetworkPage.svelte`: le stesse props di `Network`; `Segmented` «Nodi / Statistiche» (la voce «Pacchetti» arriva nel Task 10) salvato con `saveView({netView})`; mostra `Network` o `NetworkStats`.
  - `NetworkStats.svelte` (`{onpick: (id: string) => void}`):
    - periodi «24 h», «7 g», «30 g»;
    - pulsante «Aggiorna» e aggiornamento automatico ogni 60 s finché la vista è montata, con `clearInterval` alla distruzione;
    - sezioni, ognuna una `Card`:
      - «Nodi online nel tempo» (`LineChart` con `accent`);
      - «Pacchetti all'ora» (`BarChart`) con sotto l'elenco dei tipi (`kindTotals`, «{tipo}: {n} ({%})»);
      - «Distribuzione dell'SNR» (`BarChart` con serie Radio e MQTT);
      - «Salti» (`BarChart`, con l'etichetta «sconosciuti» per `null`);
      - «Nodi più attivi» (`Table` con le colonne «Nodo», «Pacchetti», «All'ora»; il clic chiama `onpick`);
      - «Modelli» e «Ruoli» (elenchi con barre orizzontali in CSS, `width` in % e colore `var(--accent)`, più «Altri: n» per i modelli);
    - nota in testa: «Le statistiche riguardano i nodi archiviati: nazioni salvate, nodi miei e preferiti, nodi sentiti via radio.» e «I pacchetti all'ora comprendono tutto il traffico ricevuto.»;
    - `Empty` con il titolo «Ancora nessun dato» se `totals.packets === 0`.
  - Su telefono la pagina Rete resta nello Sheet come oggi: le sezioni sono a una colonna, le tabelle scorrono in orizzontale dentro la propria `Card`.

- [ ] **Step 1: test che falliscono:**
  - `netstats.test.ts`:
    - `packetsPerHour` somma due tipi della stessa ora;
    - `kindTotals` → l'ordine e `share` (somma 1);
    - `barRects([0, 5, 10], 30, 100)` → altezze `[0, 50, 100]` e x crescenti; `barRects([0, 0], 10, 10)` → altezze 0;
    - `snrBinLabel(-20) === '−20…−17,5'`, `snrBinLabel(15) === '≥ 15'`;
    - `kindLabel('xyz') === 'xyz'`.
  - `viewstate.test.ts`: `netView` salvato e riletto; `'boh'` → `'nodes'`.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/netstats.test.ts src/lib/viewstate.test.ts` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS; `cd web && npm run check` → 0 errori.
- [ ] **Step 5: Commit** `feat(web): statistiche della rete nella pagina Rete`.

### Task 10: Interfaccia — ispettore dei pacchetti e impostazioni di conservazione  _(modello: sonnet)_

**Files:**
- Create: `web/src/components/PacketInspector.svelte`, `web/src/components/PacketDetail.svelte`, `web/src/lib/packets.ts`, `web/src/lib/packets.test.ts`
- Modify: `web/src/components/NetworkPage.svelte` (voce «Pacchetti»), `web/src/components/Settings.svelte` (solo la Card «Conservazione»), `web/src/lib/settings.ts`, `web/src/lib/api.ts`, `web/src/lib/types.ts`

**Interfaces:**
- Consumes: `GET /api/packets` e `GET /api/packets/{id}` (Task 6); le impostazioni `packet_log_mode` e `retention_packets_hours` (Task 1); `copyText` (`lib/clipboard.ts`); `kindLabel` (Task 9).
- Produces:
  - `types.ts`: `PacketRow`, `PacketDetail`, con la forma dei Contratti JSON. `api.ts`: `packets(query: string): Promise<{items: PacketRow[]; next_before_id: number | null}>`, `packet(id: number): Promise<PacketDetail>`.
  - `settings.ts`: in `AppSettings` i campi `packet_log_mode: 'off' | 'archived' | 'all'` e `retention_packets_hours: number`.
  - `packets.ts`:
    - `type PacketFilters = {node: string; kind: string; source: '' | 'rf' | 'mqtt'; status: string; minSnr: string; period: '1h' | '6h' | '24h' | 'all'}`;
    - `packetQuery(f: PacketFilters, now: number, beforeId: number | null, nodeId: string | null): string` (`URLSearchParams` senza i campi vuoti; `period` diventa `since = now − ore·3600`; `minSnr` va passato solo se è un numero finito);
    - `resolveNode(text: string, nodes: Iterable<Node>): string | null` (accetta `!xxxxxxxx`, 8 cifre esadecimali senza `!`, oppure il primo nodo con `short_name` uguale ignorando le maiuscole o con `long_name` che contiene il testo; altrimenti `null`);
    - `hexDump(hex: string, width = 16): {offset: string; hex: string; ascii: string}[]` (offset di 4 cifre esadecimali, byte separati da spazi, ASCII stampabile da 0x20 a 0x7e, `·` per gli altri);
    - `relayCandidates(relay: number | null, nodes: Iterable<Node>): Node[]` (`(num & 0xff) === relay`; `relay` uguale a 0 o `null` → `[]`);
    - `hopsText(p: {hops: number | null; hop_start: number | null; hop_limit: number | null}): string`, con i testi esatti:
      - `hops` noto → «{hops} salti»;
      - `hop_start` noto → «partito con {hop_start}, rimasti {hop_limit}»;
      - altrimenti «–»;
      - per `hops === 1` la stringa intera «1 salto»;
    - `STATUS_LABEL` (`ok` «Decodificato», `encrypted` «Cifrato», `unsupported` «Tipo non gestito», `undecodable` «Non decodificabile», `empty` «Vuoto»).
  - `PacketInspector.svelte` (`{nodes: Node[]; onpick: (id: string) => void}`):
    - **barra dei filtri:** campo «Nodo» (id o nome; se non riconosciuto mostra «Nodo non trovato» e non interroga); `Select` «Tipo» (Tutti più `KIND_LABEL`); `Segmented` «Fonte» (Tutte/Radio/MQTT); `Select` «Stato»; campo «SNR minimo» (number); `Segmented` «Periodo» (Ultima ora/6 h/24 h/Tutto); `Switch` «In diretta»;
    - **elenco:** `Table` con le colonne «Ora», «Da», «A», «Tipo», «Fonte», «SNR», «Salti», «Copie»; «Carica altri» con `before_id`;
    - **in diretta:** ogni 5 s chiede la prima pagina con `since` = tempo del pacchetto più recente, aggiunge in testa le righe con id nuovi e tiene al massimo 500 righe; timer pulito allo spegnimento dello Switch e alla distruzione;
    - con `packet_log_mode === 'off'`: `Banner` «L'ispettore è spento. Attivalo in Impostazioni → Conservazione.».
  - `PacketDetail.svelte` (`{id: number; nodes: Node[]; onpick; onclose}`):
    - intestazione con tipo, stato e ora;
    - `<dl>` con Da/A (cliccabili: `onpick`), id del pacchetto, canale, portnum, fonte e broker o radio, SNR, RSSI, `hopsText`, ritrasmettitore («…{relay in esadecimale}» più i nomi di `relayCandidates`), gateway, copie;
    - «Ricezioni» come elenco di `receptions`;
    - «Contenuto» come `summary` in `<pre>` (JSON indentato);
    - «Dati grezzi»: `hexDump` in una griglia mono con il pulsante «Copia esadecimale»;
    - **disposizione:** su desktop con larghezza ≥ 1100 px il dettaglio sta a destra dell'elenco, altrimenti lo sostituisce con il pulsante «Indietro».
  - **Impostazioni, Card «Conservazione»:**
    - campo «Pacchetti (ore)» (`min` 1, `max` 168);
    - `Select` «Ispettore dei pacchetti» con «Spento», «Nodi archiviati e radio» (predefinito) e «Tutto il traffico»;
    - nota «Con «Tutto il traffico» il broker pubblico occupa molto spazio: si tengono al massimo 300 000 pacchetti.».

- [ ] **Step 1: test che falliscono** in `packets.test.ts`:
  - `packetQuery` con i filtri vuoti e `period: '1h'` → solo `since=…` più `limit=100`; con `minSnr: 'abc'` → niente `min_snr`; con `beforeId` 42 → `before_id=42`;
  - `resolveNode('!0000abcd', …) === '!0000abcd'`, `resolveNode('0000ABCD', …) === '!0000abcd'`, la ricerca per nome breve e per parte del nome lungo, `resolveNode('zzz', …) === null`;
  - `hexDump('48656c6c6f00', 16)` → `[{offset: '0000', hex: '48 65 6c 6c 6f 00', ascii: 'Hello·'}]`; 20 byte → 2 righe, la seconda con offset `'0010'`;
  - `relayCandidates(0xcd, [nodo 0x1234abcd, nodo 0x12340001])` → solo il primo; `relayCandidates(0, …)` → `[]`;
  - `hopsText({hops: 1, …}) === '1 salto'`, `hopsText({hops: null, hop_start: 3, hop_limit: 1}) === 'partito con 3, rimasti 1'`, tutto `null` → `'–'`.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/packets.test.ts` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando più `cd web && npx vitest run src/lib/settings.test.ts` → PASS; `cd web && npm run check` → 0 errori.
- [ ] **Step 5: Commit** `feat(web): ispettore dei pacchetti e impostazioni di conservazione dei pacchetti`.

### Task 11: Verifica finale  _(modello: haiku)_

Nessun codice nuovo; la versione resta 1.3.0.

- [ ] **Step 1:** dalla radice `PYTHONPATH=server .venv/Scripts/python -m pytest -q` → tutti verdi.
- [ ] **Step 2:** `cd web && npx vitest run` → tutti verdi; `cd web && npm run check` → 0 errori; `cd web && npm run build` → build riuscita.
- [ ] **Step 3: migrazione.** Copiare un `meshlens.db` a schema 4 in una cartella temporanea e avviare `PYTHONPATH=server .venv/Scripts/python -m meshlens run --data-dir <cartella> --no-browser`. Verificare:
  - `PRAGMA user_version` = 5;
  - `backups/*-pre-migrazione.db` presente;
  - `GET /api/db` con `rows.metrics` e `rows.packets`.
- [ ] **Step 4: carico.** Con il broker pubblico e `packet_log_mode` su `"all"` per 15 minuti:
  - `queue_dropped` di `/api/mqtt/status` non cresce più di quanto cresceva prima della fase;
  - `SELECT COUNT(*) FROM packets` ≤ 300 000 più l'afflusso di un minuto;
  - l'interfaccia resta reattiva;
  - poi riportare la modalità ad `"archived"`.
- [ ] **Step 5: browser** (1280×800 e 390×844, temi scuro e chiaro):
  - dettaglio nodo: grafici con lettura al passaggio (mouse, tocco, frecce), periodo 24 h/7 g/30 g/90 g, sezione «Sensori» su un nodo con telemetria ambientale;
  - percorso con periodo ed «Esporta GPX» (il file si apre in un visualizzatore GPX);
  - Rete → «Esporta CSV» (si apre in un foglio di calcolo con gli accenti corretti);
  - Copertura → GeoJSON, KML (si apre in Google Earth) e CSV;
  - Rete → Statistiche (tutte le sezioni, aggiornamento);
  - Rete → Pacchetti (filtri, «Carica altri», «In diretta», dettaglio con dati grezzi e «Copia esadecimale»);
  - Impostazioni → Conservazione (le nuove voci si salvano).
- [ ] **Step 6:** testo ≥ 14 px e aree ≥ 44 px su telefono nelle viste nuove; nessuno scorrimento orizzontale della pagina, solo dentro le tabelle.
- [ ] **Step 7:** `git status` pulito, un commit per task.
