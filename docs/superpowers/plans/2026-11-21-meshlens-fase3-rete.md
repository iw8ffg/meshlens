# MeshLens Fase 3 — Gestione rete: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** dare all'utente una vista Rete con stato dei nodi, "i miei nodi", grafico della batteria, avvisi in app, mappa dei collegamenti e traceroute a richiesta.

**Architettura:** il server decodifica due nuovi tipi di pacchetto (NeighborInfo e Traceroute) da MQTT e da RF e li registra in una nuova tabella `links`. I collegamenti diretti delle radio si ricavano dai pacchetti RF ricevuti con 0 hop. Gli avvisi si calcolano sul server, così telefono e PC vedono gli stessi. L'interfaccia aggiunge la scheda "Rete", alcuni elementi in NodeDetail e un livello di linee sulla mappa.

**Tecnologie:** quelle delle fasi 1 e 2: Python 3.12, FastAPI, SQLite, `meshtastic` 2.7.11 (protobuf `mesh_pb2.NeighborInfo`, `mesh_pb2.RouteDiscovery`), Svelte 5, MapLibre GL. Nessuna dipendenza nuova: il grafico è SVG scritto a mano.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md` (§6.3, §7, §9 "I miei nodi"). Note sulla libreria: `docs/superpowers/research/2026-11-20-meshtastic-python-api.md`.

## Global Constraints

- Testi dell'interfaccia e messaggi d'errore in italiano.
- Avvisi **solo per i nodi "miei"**. Batteria sotto `battery_alert_pct` (default **20**); il valore 101 indica alimentazione esterna e non genera avvisi. Nodo "mio" silenzioso da più di `silent_alert_hours` (default **6**, scelto dall'utente).
- Traceroute **solo a richiesta dell'utente** (scelto dall'utente): nessun invio automatico. Al massimo un traceroute ogni **30 s** per radio, perché il firmware scarta quelli più frequenti.
- Il traceroute trasmette via radio: passa dall'API autenticata, come l'invio dei messaggi.
- MeshLens non pubblica nulla su MQTT.
- I collegamenti scadono come le posizioni (`retention_positions_days`, default 90). Gli avvisi non si salvano: si ricalcolano.
- Le radio collegate sono "mie" in automatico (già fatto in fase 2); l'utente marca a mano gli altri nodi.
- SNR nei protobuf di traceroute: intero in quarti di dB (dividere per 4); il valore -128 significa "sconosciuto" (`None`).
- Un collegamento `(from_num, to_num)` significa che **`to_num` ha ricevuto `from_num` direttamente**; l'SNR è quello misurato da `to_num`.
- Nuovi messaggi WebSocket: `{"type":"alerts","alerts":[...]}` e `{"type":"traceroute","result":{...}}`.
- Test: pytest per il server, vitest per le funzioni pure dell'interfaccia, `npm run check` (svelte-check) senza errori.

## Contratti JSON (l'interfaccia dipende solo da questi)

- **Nodo**: aggiunge `is_mine: bool`, oggi nascosto da `INTERNAL_KEYS` in `api.py` e filtrato in `app.py:_publish_changed`.
- **Link**: `{from_id:"!hex", to_id:"!hex", source:"neighborinfo"|"traceroute"|"rf_direct", snr:number|null, time:number}`.
- **Avviso**: `{key:"battery:!hex"|"silent:!hex", kind:"battery_low"|"silent", node_id, node_name, value:number, since:number}`. `value` vale la percentuale per `battery_low` e le ore di silenzio per `silent`.
- **Punto di telemetria**: `{time, battery, voltage, channel_util, air_util_tx}`. Viene da `store.telemetry`, che esiste già.
- **Traceroute**: `{id:int, radio_id, target_id:"!hex", time, status:"pending"|"ok"|"failed"|"timeout", error:string|null, forward:[{id:"!hex", snr:number|null}], back:[{id, snr}]}`.
  - `forward` va dalla radio al nodo. Il primo elemento è il nodo della radio con `snr` null; ogni elemento successivo porta l'SNR con cui è stato ricevuto.
  - `back` segue la stessa regola, dal nodo alla radio.
- **Nuove rotte**, tutte con `require_auth`:
  - `GET /api/nodes/{id}/telemetry?hours=168` → `[Punto]`
  - `PUT /api/nodes/{id}/mine` body `{mine:bool}` → Nodo
  - `GET /api/links?hours=24` → `[Link]`
  - `GET /api/alerts` → `[Avviso]`
  - `POST /api/nodes/{id}/traceroute` body `{radio_id?:string}` → 202 Traceroute. Errori: 409 se nessuna radio è collegata, 429 con "Attendi N s" se il limite di 30 s non è passato.
  - `GET /api/nodes/{id}/traceroutes` → gli ultimi 10 Traceroute.
- **Impostazioni**: nuove chiavi `battery_alert_pct` (intero 1–99) e `silent_alert_hours` (intero 1–168).

## Review Focus

1. **Traceroute senza risposta** (nodo spento o fuori portata): dopo **60 s** lo stato diventa `timeout` e l'interfaccia lo mostra. Un errore di instradamento (ROUTING_APP con errore e `requestId` del traceroute) dà subito `failed` con il motivo. Non deve mai finire tra le conferme dei messaggi chat.
2. **Nodo "mio" senza GPS e sentito solo via MQTT** (fuori dalle nazioni salvate): marcato a mano, deve essere archiviato con la sua telemetria e generare avvisi. `persist` in ingest già guarda `is_mine`: va verificato con un test.
3. **Batteria al 101%** (alimentato da USB) e **batteria mancante**: nessun avviso, e il grafico non disegna 101 come percentuale.
4. **Avvisi stabili**: un avviso resta uguale (stessa `key` e `since`) da un controllo all'altro. Si invia su WebSocket solo quando l'elenco cambia, mai ogni minuto se è uguale.
5. **Collegamenti con un estremo senza posizione** (come l'Heltec senza GPS): si salvano lo stesso, ma la mappa li salta senza errori. L'elenco del traceroute mostra comunque i nomi.

---

### Task 1: Dati: tabelle, impostazioni, "mio"

**File:**
- Modifica: `server/meshlens/db.py`, `server/meshlens/store.py`, `server/meshlens/settings.py`, `server/meshlens/api.py` (solo `INTERNAL_KEYS`), `server/meshlens/app.py` (solo il filtro di `_publish_changed`)
- Test: `server/tests/test_store.py`, `server/tests/test_settings.py`, più un test in `server/tests/test_ingest.py`, `server/tests/test_ingest_rf.py`

**Interfacce prodotte:**
- Schema:
  - `links(from_num INTEGER, to_num INTEGER, source TEXT, snr REAL, time REAL, PRIMARY KEY(from_num,to_num,source))`;
  - `traceroutes(id INTEGER PRIMARY KEY AUTOINCREMENT, radio_id TEXT, target_num INTEGER, time REAL, status TEXT, error TEXT, forward TEXT, back TEXT)`, dove `forward` e `back` sono JSON;
  - indice su `links(time)`.
- `Store`:
  - `upsert_link(from_num:int, to_num:int, source:str, snr:float|None, time:float) -> None`: tiene la riga più recente per terna;
  - `links(since:float) -> list[dict]` nel formato del contratto Link, con id `"!hex"`;
  - `set_mine(num:int, mine:bool) -> None`;
  - `add_traceroute(radio_id, target_num, time) -> int`;
  - `update_traceroute(id, status, error, forward, back) -> None`;
  - `traceroutes(target_num, limit=10) -> list[dict]` nel formato del contratto Traceroute;
  - `purge` elimina anche i `links` più vecchi di `retention_positions_days`; i `traceroutes` non scadono.
- Default delle impostazioni `battery_alert_pct: 20` e `silent_alert_hours: 6`, con la stessa validazione delle altre chiavi intere.
- `is_mine` compare nel Nodo JSON di REST e WebSocket.

- [ ] **Step 1: Scrivi i test che falliscono**
  - `test_upsert_link_keeps_latest`: due upsert della stessa terna con `time` 100 e 200 → una riga sola con `time` 200 e l'SNR della seconda.
  - `test_links_since_filters_and_formats`: un link con time 50 e uno con 150, `links(100)` → solo il secondo, con `from_id` del tipo `"!0000000a"`.
  - `test_purge_drops_old_links`.
  - `test_set_mine_roundtrip`: `set_mine(10, True)`, poi `load_nodes` → `is_mine` vale True.
  - `test_traceroute_roundtrip`: add, update con forward `[{"id":"!0000000a","snr":None}]`, poi `traceroutes(…)` restituisce le liste decodificate.
  - `test_alert_settings_defaults_and_validation`: default 20 e 6; `battery_alert_pct` 0 rifiutato; `silent_alert_hours` 200 rifiutato.
  - `test_mine_node_outside_saved_countries_is_persisted` (Review Focus 2): nodo con `is_mine` e telemetria MQTT, `country` assente → la riga di telemetria è salvata.
  - `test_node_json_exposes_is_mine`: `GET /api/nodes/{id}` contiene `is_mine`.
- [ ] **Step 2: Esegui** `.venv/Scripts/python -m pytest server/tests -q`. Atteso: falliscono solo i test nuovi.
- [ ] **Step 3: Implementa.** Nuove tabelle in `SCHEMA` (`CREATE TABLE IF NOT EXISTS` basta per i database esistenti). Togli `is_mine` da `INTERNAL_KEYS` e dal filtro di `_publish_changed`.
- [ ] **Step 4: Esegui di nuovo tutta la suite.** Atteso: tutta verde.
- [ ] **Step 5: Commit** `feat(server): tabelle links e traceroutes, nodi miei, impostazioni avvisi`.

### Task 2: Decodifica NeighborInfo e Traceroute, registrazione dei collegamenti

**File:**
- Modifica: `server/meshlens/events.py`, `server/meshlens/mqtt_decode.py`, `server/meshlens/rf_convert.py`, `server/meshlens/ingest.py`
- Test: `server/tests/test_mqtt_decode.py`, `server/tests/test_rf_convert.py`, `server/tests/test_ingest.py`, `server/tests/test_ingest_rf.py`

**Interfacce:**
- Usa: `Store.upsert_link` (Task 1).
- Produce:
  - `NeighborData(neighbors: list[tuple[int, float | None]])`, con kind `"neighbors"`. Ogni tupla è `(node_id del vicino, snr)`; il nodo che riferisce è `ev.from_node`.
  - `RouteData(request_id: int | None, route: list[int], snr_towards: list[float | None], route_back: list[int], snr_back: list[float | None])`, con kind `"traceroute"`. È il pacchetto di risposta: `from_node` è il nodo raggiunto e `to_node` chi ha avviato il traceroute.
  - `traceroute_chains(ev) -> tuple[list[tuple[int, float|None]], list[tuple[int, float|None]]]` in `ingest.py` (funzione pura):
    - andata: `[(to_node, None)] + zip(route + [from_node], snr_towards)`;
    - ritorno: `[(from_node, None)] + zip(route_back + [to_node], snr_back)`;
    - le liste SNR più corte dei nodi si completano con `None`.
  - `Ingestor.set_radio_node(radio_id: str, num: int)`, chiamato da `RadioManager._on_state` accanto a `mark_local_radio`.

**Regole in ingest:**
- `neighbors` → `upsert_link(vicino, from_node, "neighborinfo", snr, rx_time)` per ogni vicino.
- `traceroute` → un link `"traceroute"` per ogni coppia consecutiva di ciascuna catena; l'SNR è quello del secondo elemento.
- Qualunque evento RF con `hops == 0`, `radio_id` noto a `set_radio_node` e `rx_time > 0` → `upsert_link(from_node, nodo_della_radio, "rf_direct", ev.snr, rx_time)`.
- Questi kind non toccano posizione, telemetria e messaggi, ma aggiornano `last_heard`, come gli altri pacchetti.
- I duplicati registrano comunque il link: un'altra copia può portare un SNR migliore, e l'upsert la tiene.

- [ ] **Step 1: Test che falliscono**
  - `test_mqtt_neighborinfo_decoded`: costruisci con `mesh_pb2.NeighborInfo` 2 vicini (snr 6.5 e -3.0), cifrato con la chiave di default come negli altri test → `NeighborData` con i due valori.
  - `test_mqtt_traceroute_decoded_snr_scaled`: `RouteDiscovery(route=[0x0b], snr_towards=[24, -128], route_back=[], snr_back=[-8])` → `snr_towards == [6.0, None]` e `snr_back == [-2.0]`; `request_id` viene da `Data.request_id`.
  - `test_rf_traceroute_and_neighbors_converted`: dict nel formato della libreria. `decoded.portnum` vale `"TRACEROUTE_APP"` con `decoded.traceroute` `{route, snrTowards, routeBack, snrBack}` e `requestId`; vale `"NEIGHBORINFO_APP"` con `decoded.neighborinfo.neighbors[{nodeId, snr}]`. Se `decoded.traceroute` manca, decodifica `decoded.payload` con il protobuf.
  - `test_traceroute_chains`: from=T (3), to=O (1), route [2], snr_towards [6.0, -1.0], route_back [], snr_back [4.0] → andata `[(1,None),(2,6.0),(3,-1.0)]`, ritorno `[(3,None),(1,4.0)]`.
  - `test_ingest_records_links`: un evento neighbors e uno traceroute producono le righe attese in `store.links(0)`.
  - `test_rf_direct_link_only_with_zero_hops`: hops 0 crea il link verso il nodo della radio; hops 2 no; `rx_time` 0 (replay dal database della radio) no.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.** Usa la funzione `_scale_snr(v)` (`None if v == -128 else v / 4`) sia in `mqtt_decode` sia in `rf_convert`: definiscila in `events.py`.
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): NeighborInfo e traceroute da MQTT e RF, collegamenti`.

### Task 3: Traceroute a richiesta

**File:**
- Modifica: `server/meshlens/radio.py`, `server/meshlens/radio_manager.py`, `server/meshlens/api.py`, `server/meshlens/app.py`
- Test: `server/tests/test_radio.py`, `server/tests/test_radio_manager.py`, `server/tests/test_api_radios.py`

**Interfacce:**
- Usa: `RouteData`, `traceroute_chains` (Task 2); `Store.add_traceroute`, `update_traceroute` e `traceroutes` (Task 1).
- Produce:
  - `RadioConnector.send_traceroute(dest_num: int, channel_index: int = 0) -> int`: restituisce il packet id e usa lo stesso lock e lo stesso timeout di 30 s di `send_text`. Chiama `iface.sendData(mesh_pb2.RouteDiscovery(), destinationId=dest_num, portNum=portnums_pb2.TRACEROUTE_APP, wantResponse=True, channelIndex=channel_index)` in un thread.
  - `RadioConnector.on_packet`: con `TRACEROUTE_APP` e `requestId` chiama la nuova callback `on_traceroute(radio_id, request_id, event)`. Il pacchetto continua comunque verso `on_event`, così l'ingest registra i link. La callback si passa al costruttore come `on_ack`.
  - `RadioManager.traceroute(node_id: str, radio_id: str | None) -> dict`:
    1. se `radio_id` manca, sceglie la radio collegata che sente il nodo con meno hop secondo `heard_by`, altrimenti la prima collegata;
    2. applica il limite di 30 s per radio (`TracerouteThrottled(wait_s)` → 429);
    3. invia, salva una riga `pending` e ne pubblica il risultato.
  - `RadioManager._on_ack`: se `(radio_id, packet_id)` è un traceroute in attesa, non va nel buffer `_early_acks`. Con `ok=False` lo stato diventa `failed` con il motivo tradotto, la stessa mappatura dei messaggi; con `ok=True` si ignora (ack implicito).
  - Il risultato pubblicato è `{"type":"traceroute","result":<Traceroute JSON>}` a ogni cambio di stato. Un controllo periodico, lo stesso giro di `check_acks`, porta a `timeout` i pending più vecchi di **60 s**.
  - Rotte `POST /api/nodes/{id}/traceroute` e `GET /api/nodes/{id}/traceroutes`, come da contratto.

- [ ] **Step 1: Test che falliscono**, con il FakeIface o FakeConnector già usati nei test della fase 2:
  - `test_send_traceroute_calls_senddata`: `portNum` TRACEROUTE_APP, `wantResponse` True; restituisce l'id.
  - `test_traceroute_response_resolves_pending`: la risposta con `requestId` uguale porta lo stato a `ok`, e `forward`/`back` hanno id `"!hex"` e SNR scalati.
  - `test_traceroute_routing_error_fails_and_is_not_a_chat_ack` (Review Focus 1): errore `NO_RESPONSE` → `failed`; `_early_acks` resta vuoto.
  - `test_traceroute_timeout_after_60s`: orologio finto avanzato di 61 s → `timeout`.
  - `test_traceroute_throttled_per_radio`: secondo traceroute dopo 10 s → `TracerouteThrottled` con attesa 20; la rotta risponde 429 con "Attendi 20 s".
  - `test_traceroute_picks_radio_with_fewest_hops`.
  - `test_traceroute_no_radio_409`.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): traceroute a richiesta con timeout e limite per radio`.

### Task 4: API di gestione e avvisi

**File:**
- Crea: `server/meshlens/alerts.py`
- Modifica: `server/meshlens/api.py`, `server/meshlens/app.py`
- Test: `server/tests/test_alerts.py`, `server/tests/test_api.py`

**Interfacce:**
- Usa: `Store.telemetry`, `links`, `set_mine` (Task 1).
- Produce:
  - `compute_alerts(nodes: Iterable[dict], settings: dict, now: float, previous: dict[str, dict]) -> list[dict]`: funzione pura in `alerts.py`. Considera solo i nodi con `is_mine`. `since` si conserva da `previous` quando la `key` c'era già, altrimenti vale `now`. Ordine: prima `battery_low`, poi per nome.
  - `AppContext.alerts()`, ricalcolata ogni **60 s** e dopo ogni `PUT /mine`; pubblica `{"type":"alerts"}` solo se l'elenco di key e value arrotondati cambia.
  - Rotte `GET /api/nodes/{id}/telemetry`, `PUT /api/nodes/{id}/mine` (aggiorna nodo live, database e WS `nodes`), `GET /api/links`, `GET /api/alerts`.

- [ ] **Step 1: Test che falliscono**
  - `test_battery_low_only_for_mine`: nodo mio al 15% → un avviso con `value` 15; nodo non mio al 5% → nessuno.
  - `test_battery_101_and_none_ignored` (Review Focus 3).
  - `test_silent_after_threshold`: `last_heard` = now − 7 h, soglia 6 → `value` 7; now − 5 h → nessuno; `last_heard` None → **nessun avviso**, per non segnalare un nodo mai sentito appena marcato a mano.
  - `test_since_preserved` (Review Focus 4): due calcoli di fila con `previous` → stesso `since`.
  - `test_publish_only_on_change`: due tick senza cambi → un solo messaggio `alerts` sul bus.
  - `test_put_mine_and_get_alerts`: PUT `{mine:true}` su un nodo al 10% → `GET /api/alerts` lo contiene.
  - `test_telemetry_route`, `test_links_route`: formato del contratto, e 404 per un id sconosciuto.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): avvisi su nodi miei, rotte telemetria/collegamenti/mine`.

### Task 5: Interfaccia, scheda Rete e avvisi

**File:**
- Crea: `web/src/components/Network.svelte`, `web/src/components/Alerts.svelte`, `web/src/lib/network.ts`, `web/src/lib/network.test.ts`
- Modifica: `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/lib/stores.svelte.ts`, `web/src/lib/ws.ts`, `web/src/App.svelte`, `web/src/components/Settings.svelte`

**Interfacce:**
- Usa: i contratti JSON qui sopra.
- Produce:
  - tipi `Link`, `Alert`, `TelemetryPoint`, `Traceroute` e `Node.is_mine`;
  - funzioni `api.telemetry(id, hours)`, `setMine(id, mine)`, `links(hours)`, `alerts()`, `traceroute(id, radioId?)`, `traceroutes(id)`;
  - store `alerts` (array, sostituito dal messaggio WS e ricaricato alla riconnessione come gli altri) e `traceroutes` (SvelteMap da id a Traceroute, aggiornata dal WS);
  - in `network.ts`:
    - `type SortKey = 'name'|'last_heard'|'role'|'firmware'|'battery'|'voltage'|'snr'|'hops'|'channel_util'|'air_util_tx'`;
    - `sortNodes(nodes, key, dir:'asc'|'desc')`: i valori null vanno sempre in fondo; il nome si confronta con `localeCompare`;
    - `batteryLabel(b)`: 101 → "USB", null → "—".

**Comportamento:**
- Nuova scheda **"Rete"**, tra Nodi e Chat.
- Interruttore "Solo i miei nodi": acceso di default se esiste almeno un nodo mio. Se è acceso e non ci sono nodi miei, compare il testo "Nessun nodo segnato come tuo: aprilo e premi ☆".
- Tabella con le colonne del `SortKey`; si ordina cliccando l'intestazione. Cliccando una riga si seleziona il nodo, come in NodeList.
- Su telefono la tabella scorre in orizzontale e la prima colonna resta ferma.
- `Alerts.svelte` è un banner sotto la StatusBar quando ci sono avvisi, per esempio "⚠ 2 avvisi" (tocca per espandere). Ogni voce dice, per esempio, "Batteria 15% — Nome" oppure "Silenzioso da 7 h — Nome" e porta al nodo.
- In Impostazioni si aggiungono i campi "Avviso batteria sotto (%)" e "Avviso nodo silenzioso dopo (ore)".

- [ ] **Step 1: Test vitest che falliscono** in `network.test.ts`:
  - `sortNodes` mette in fondo i null in entrambe le direzioni;
  - ordina per batteria in modo decrescente;
  - `batteryLabel(101) === 'USB'`.
- [ ] **Step 2: Esegui** `cd web; npx vitest run`. Atteso: falliscono.
- [ ] **Step 3: Implementa** funzioni, store e componenti.
- [ ] **Step 4: Verifica:** `npx vitest run` e `npm run check` senza errori; `npm run build` riesce.
- [ ] **Step 5: Commit** `feat(web): scheda Rete, avvisi, impostazioni soglie`.

### Task 6: Interfaccia, dettaglio nodo (mio, grafico, traceroute)

**File:**
- Crea: `web/src/components/TelemetryChart.svelte`, `web/src/components/Traceroute.svelte`, `web/src/lib/chart.ts`, `web/src/lib/chart.test.ts`
- Modifica: `web/src/components/NodeDetail.svelte`

**Interfacce:**
- Usa: le funzioni API e gli store del Task 5.
- Produce:
  - in `chart.ts`: `linePath(points: {t:number, v:number|null}[], x0, x1, y0, y1, w, h): string`, che genera il path SVG. Un valore null interrompe la linea con un nuovo `M`. `batterySeries(points)` scarta i valori 101 (Review Focus 3). `niceRange(values, pad)` dà un intervallo dell'asse y per la tensione.
  - `TelemetryChart`:
    - periodo 24 h, 7 g o 30 g (default 7 g);
    - linea della batteria in % (asse 0–100) e linea della tensione in V (asse destro);
    - linea tratteggiata alla soglia di avviso;
    - "Nessun dato di telemetria nel periodo" se vuoto.
  - `Traceroute`:
    - pulsante "Traceroute"; se ci sono più radio collegate, accanto c'è una scelta della radio, con default "automatica";
    - durante l'attesa mostra "In corso… (max 60 s)";
    - il risultato è un elenco di andata e ritorno, con nomi brevi e SNR per salto (per esempio `Base → Rip1 (6 dB) → Nodo (−1 dB)`). I nodi senza nome compaiono come id; l'SNR sconosciuto come "?";
    - in caso di errore lo mostra (`failed` con motivo, `timeout` come "Nessuna risposta entro 60 s", 429 con il testo del server);
    - sotto, gli ultimi traceroute da `GET /traceroutes`.
- NodeDetail aggiunge il pulsante ☆/★ "Mio nodo" (PUT `/mine`), il grafico e il traceroute. Il traceroute è disabilitato con la spiegazione "Collega una radio" se nessuna radio è collegata.

- [ ] **Step 1: Test vitest che falliscono** in `chart.test.ts`:
  - `linePath` con 3 punti genera `M…L…L…`;
  - con un null in mezzo genera due `M`;
  - `batterySeries` toglie il 101;
  - `niceRange([3.7, 4.1])` restituisce un minimo ≤ 3.7 e un massimo ≥ 4.1.
- [ ] **Step 2: Esegui vitest.** Atteso: falliscono.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): nodo mio, grafico telemetria, traceroute nel dettaglio`.

### Task 7: Interfaccia, collegamenti sulla mappa

**File:**
- Crea: `web/src/lib/links.ts`, `web/src/lib/links.test.ts`
- Modifica: `web/src/components/MapView.svelte`, `web/src/components/Filters.svelte`, `web/src/lib/filters.ts` (interruttore salvato come gli altri filtri)

**Interfacce:**
- Usa: `api.links` (Task 5).
- Produce:
  - `snrColor(snr: number|null): string`: con SNR ≥ 0 verde `#2e9d4b`, tra −10 e 0 escluso giallo `#d9a400`, sotto −10 rosso `#c8382e`, null grigio `#8a8a8a`;
  - `linksToGeoJSON(links, nodes: Map<string, Node>): FeatureCollection<LineString>`:
    - unisce `A→B` e `B→A` in una sola linea, tenendo l'SNR migliore e il tempo più recente;
    - salta i link che hanno un estremo senza `lat`/`lon` (Review Focus 5);
    - `properties: {color, source, snr, age_h}`.
- In Filters c'è l'interruttore "Collegamenti", spento di default.
- Quando è acceso, MapView carica `GET /api/links?hours=24` e lo ricarica ogni 60 s. Disegna un layer `line` sotto i marker, con colore da `color` e opacità decrescente con `age_h` (1 → 0,35 a 24 h). Le linee da `traceroute` sono tratteggiate.
- Toccando una linea compare un popup con i due nomi, SNR, fonte ed età.
- Il layer va ricreato dopo un cambio di stile, che esiste già per il passaggio online/offline.

- [ ] **Step 1: Test vitest che falliscono** in `links.test.ts`:
  - colori alle soglie −10, 0 e null;
  - A→B e B→A diventano una sola feature con l'SNR migliore;
  - un link con un estremo senza posizione viene saltato;
  - un nodo assente dalla mappa viene saltato.
- [ ] **Step 2: Esegui vitest.** Atteso: falliscono.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): livello collegamenti sulla mappa`.

### Task 8: Prova con le radio vere (insieme all'utente)

Si fa insieme al Task 8 della fase 2.

- [ ] Marca un nodo come mio dal telefono e verifica che compaia nella scheda Rete sul PC.
- [ ] Controlla il grafico della batteria del T-Pager dopo almeno un'ora di telemetria.
- [ ] Imposta la soglia a 99% e verifica che compaia l'avviso; riportala a 20.
- [ ] Fai un traceroute dall'Heltec al T-Pager: risultato `ok` con SNR, e linea sulla mappa.
- [ ] Fai un traceroute verso un nodo spento: `timeout` dopo 60 s.
- [ ] Verifica che compaiano i collegamenti `rf_direct` dei nodi sentiti a 0 hop.

---

**Esecuzione in parallelo:** i Task 1→4 (server) e 5→7 (interfaccia) toccano file diversi e si parlano solo tramite i contratti JSON qui sopra. Si possono eseguire in due worktree separati, ciascuno in sequenza, e poi unire sul ramo `fase3`.
