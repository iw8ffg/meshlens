# MeshLens Fase 4 — Copertura sul campo (Range Test): piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** permettere sessioni di prova di copertura. Una radio di base collegata a MeshLens registra i pacchetti Range Test e le posizioni di un nodo mobile con GPS. A fine prova si vedono sulla mappa i punti colorati per segnale, il percorso, i punti mancanti e le statistiche; le sessioni restano in uno storico.

**Architettura:** nuovo modulo server `coverage.py`, diviso in due parti:
- funzioni pure: interpolazione della posizione, punti mancanti, statistiche;
- un `CoverageRecorder` che riceve ogni evento dopo l'ingestione e registra i dati della sessione attiva nelle nuove tabelle.

La sessione continua a registrare anche a browser chiuso e dopo un riavvio del server. Nell'interfaccia c'è una nuova scheda "Copertura" con la guida di preparazione, i controlli automatici, la sessione in corso e lo storico. Sulla mappa c'è un livello per i risultati della sessione aperta.

**Tecnologie:** quelle delle fasi precedenti. Nessuna dipendenza nuova.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md` (§6.4, §7, §9 "Range Test"). Ricerca: `docs/superpowers/research/2026-11-21-range-test.md`.

## Global Constraints

- Testi in italiano.
- **Range Test:** il mittente trasmette `RANGE_TEST_APP` (portnum 66) con testo UTF-8 `"seq N"` (N parte da 0 a ogni avvio). La posizione **non** è nel pacchetto: arriva con pacchetti `POSITION_APP` separati. La libreria espone `decoded.portnum == "RANGE_TEST_APP"`, `decoded.text` e `decoded.payload` (bytes).
- **Preparazione guidata** (scelta dell'utente): MeshLens mostra i passi da fare con l'app Meshtastic e controlla in automatico che i dati arrivino. Non modifica la configurazione delle radio (questo arriva con la fase 5).
- **Il canale lo sceglie l'utente** (scelta dell'utente): se le posizioni del nodo mobile sono approssimate (`precision_bits` < 32), MeshLens lo dice chiaramente con il raggio stimato. Lascia comunque partire la sessione dopo una conferma esplicita ("Continua con posizioni approssimate").
- **Niente GPS, niente sessione** (spec §9): se il nodo mobile non ha mandato una posizione negli ultimi **10 minuti**, la sessione non parte. Messaggio: "Il nodo mobile non ha inviato una posizione negli ultimi 10 minuti: serve il GPS acceso e la posizione attiva."
- **Due modalità:**
  - `rangetest` (principale): i punti sono i pacchetti Range Test, e i numeri di sequenza permettono di dedurre i punti mancanti;
  - `position` (ripiego, spec §9): i punti sono i pacchetti di posizione del mobile ricevuti dalla base, senza punti mancanti.
- **Una sola sessione attiva** alla volta. Si ferma a mano oppure da sola dopo **8 ore**, perché il firmware spegne il mittente dopo 8 h. Dopo un riavvio del server una sessione attiva riprende a registrare.
- **Intervallo:** default 30 s (valori ammessi 10–600). Serve per stimare l'ora dei punti mancanti.
- Le sessioni e i loro punti **non scadono** (spec §7).
- MeshLens non trasmette nulla durante la prova: ascolta soltanto.
- **Colori SNR** uguali alla mappa dei collegamenti: ≥ 0 verde `#2e9d4b`, tra −10 e 0 escluso giallo `#d9a400`, sotto −10 rosso `#c8382e`, sconosciuto grigio `#8a8a8a`. I punti mancanti sono grigi.
- **Raggio di precisione:** si calcola dai `precision_bits` con la funzione dell'interfaccia esistente `precisionRadiusM` (`web/src/lib/geo.ts`). Sul server si usa la stessa formula: `round(2**(32-bits) * 1e-7 * 111320 / 2)` metri; 32 bit o `None` = esatta.

## Contratti JSON

- **Sessione (riepilogo):** `{id, name, radio_id, mobile_id:"!hex", mode:"rangetest"|"position", channel_index:int|null, interval_s, started, ended:number|null, end_reason:"manual"|"timeout"|null, base_lat, base_lon, notes, received:int, expected:int|null, missing:int|null, loss_pct:number|null, best_snr, worst_snr, max_distance_m:number|null, approx_precision_m:number|null}`.
  - In modalità `position`, `expected`, `missing` e `loss_pct` valgono null.
  - `max_distance_m` è null se la base non ha una posizione.
  - `approx_precision_m` è il raggio massimo dei punti ricevuti, null se tutti esatti.
- **Dettaglio:** `GET /api/coverage/sessions/{id}` restituisce il riepilogo più:
  - `points: [{seq:int|null, time, snr, rssi, hops, lat, lon, precision_bits, distance_m}]`;
  - `missing_points: [{seq, time, lat, lon}]` (`lat` e `lon` possono essere null);
  - `track: [{time, lat, lon, precision_bits}]`.
- **Controlli:** `GET /api/coverage/check?radio_id=…&mobile_id=…` restituisce `{radio_connected:bool, radio_channels:[{index,name}], mobile_known:bool, position_age_s:number|null, precision_bits:int|null, precision_m:number|null, gps_ok:bool, rangetest_age_s:number|null, base_position:{lat,lon}|null}`.
  - `gps_ok` vale true se `position_age_s` ≤ 600.
  - `rangetest_age_s` viene dall'ultimo pacchetto Range Test del mobile ricevuto da quella radio, anche fuori sessione, ricordato in memoria.
  - `base_position` è la posizione del nodo della radio di base, se nota.
- **Rotte**, tutte con `require_auth`:
  - `GET /api/coverage/sessions` → riepiloghi, i più recenti prima;
  - `POST /api/coverage/sessions` body `{name?, radio_id, mobile_id, mode?, interval_s?, base_lat?, base_lon?, accept_approx?:bool}` → 201 con il riepilogo. Errori:
    - 409 "C'è già una sessione in corso";
    - 400 se la radio non è collegata;
    - 400 con il messaggio GPS;
    - 400 con codice `approx_position` e messaggio sul raggio, se la posizione è approssimata e `accept_approx` non è true;
  - `POST /api/coverage/sessions/{id}/stop`;
  - `PATCH /api/coverage/sessions/{id}` body `{name?, notes?, base_lat?, base_lon?}`, dove `base_lat` e `base_lon` vanno insieme;
  - `DELETE /api/coverage/sessions/{id}` (vietato sulla sessione attiva: 409);
  - `GET /api/coverage/sessions/{id}`;
  - `GET /api/coverage/check`.
- **WebSocket:** `{"type":"coverage","session":<riepilogo>,"point":<punto>|null}` a ogni punto registrato e a ogni avvio o fine di sessione.
- `name` di default: `"Prova " + data e ora locali`, per esempio `"Prova 21/11 15:30"`.

## Review Focus

1. **Riavvio del nodo mobile durante la prova:** la sequenza riparte da 0. I punti mancanti si calcolano per tratto: un tratto finisce quando la sequenza diminuisce. Il calo non deve generare migliaia di punti mancanti né un `loss_pct` negativo.
2. **Pacchetto Range Test senza posizione vicina:** se il mobile non ha mandato posizioni entro ±120 s, il punto si salva con `lat`/`lon` null. Conta nelle statistiche ma non si disegna, e non va in errore.
3. **Copie duplicate dello stesso `seq`** dallo stesso tratto (stessa radio, ad esempio pacchetto ripetuto): si registra una volta sola, tenendo l'SNR migliore.
4. **Pacchetti di altri nodi o di altre radio:** non entrano nella sessione. Conta solo `source == "rf"`, `radio_id` uguale a quello della sessione e `from_node` uguale al mobile. Le posizioni del mobile per il percorso valgono invece da qualsiasi fonte.
5. **Testo Range Test non valido** (non `"seq N"`, oppure UTF-8 rotto): il pacchetto si ignora senza errori. Il conteggio `rangetest_age_s` si aggiorna comunque, perché dimostra che il modulo è attivo.

---

### Task 1: Server, decodifica Range Test e tabelle

**File:**
- Modifica: `server/meshlens/events.py`, `server/meshlens/rf_convert.py`, `server/meshlens/ingest.py`, `server/meshlens/db.py`, `server/meshlens/store.py`
- Test: `server/tests/test_rf_convert.py`, `server/tests/test_ingest_rf.py`, `server/tests/test_store.py`

**Interfacce prodotte:**
- `RangeTestData(seq: int | None, text: str)`, con kind `"rangetest"`.
  - In `rf_convert.packet_to_event`, `RANGE_TEST_APP` usa `decoded.text`; se manca, prova `decoded.payload.decode("utf-8")`.
  - `seq` si legge con `parse_seq(text) -> int | None`: accetta solo `"seq N"` con N intero ≥ 0, spazi esterni ignorati.
- Ingest: il kind `rangetest` aggiorna solo `last_heard`, `sources` e `heard_by`, come gli altri pacchetti. Non tocca posizione, telemetria e messaggi.
- Schema:
  - `coverage_sessions(id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, radio_id TEXT, mobile_num INTEGER, mode TEXT, channel_index INTEGER, interval_s INTEGER, started REAL, ended REAL, end_reason TEXT, base_lat REAL, base_lon REAL, notes TEXT)`;
  - `coverage_points(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, segment INTEGER, seq INTEGER, time REAL, snr REAL, rssi INTEGER, hops INTEGER, lat REAL, lon REAL, precision_bits INTEGER)`, con indice unico `(session_id, segment, seq)` quando `seq` non è null;
  - `coverage_track(id INTEGER PRIMARY KEY AUTOINCREMENT, session_id INTEGER, time REAL, lat REAL, lon REAL, precision_bits INTEGER)`;
  - indici per `session_id`.
- `Store`:
  - `create_session(**fields) -> int`;
  - `update_session(id, **fields)`;
  - `get_session(id) -> dict | None`;
  - `sessions() -> list[dict]`;
  - `active_session() -> dict | None` (`ended IS NULL`);
  - `delete_session(id)`, che cancella anche punti e percorso;
  - `add_point(session_id, segment, seq, time, snr, rssi, hops, lat, lon, precision_bits) -> bool`. Con lo stesso `(session, segment, seq)` tiene l'SNR migliore e restituisce False se non era nuovo;
  - `points(session_id)`;
  - `add_track(session_id, time, lat, lon, precision_bits)`;
  - `track(session_id)`;
  - `update_point_position(point_id, lat, lon, precision_bits)`.
  - `purge` **non** tocca queste tabelle.

- [ ] **Step 1: Test che falliscono**
  - `test_parse_seq`: `"seq 12"` → 12; `" seq 0 "` → 0; `"seq"`, `"seq -1"`, `"hello 3"` e `"seq 1.5"` → None.
  - `test_rangetest_packet_converted`: dict con `decoded.text "seq 7"` → evento con kind `rangetest` e seq 7. Con solo `payload b"seq 8"` → seq 8. Con UTF-8 rotto → evento con seq None e `text` vuoto (Review Focus 5).
  - `test_rangetest_updates_only_last_heard`.
  - `test_add_point_dedup_keeps_best_snr` (Review Focus 3): due `add_point` con lo stesso seq e SNR −5 e −2 → una riga con −2; la seconda chiamata restituisce False.
  - `test_session_crud_and_active`: create, poi `active_session`, poi update con `ended`, poi `active_session` None; `delete_session` cancella anche i punti.
  - `test_purge_keeps_coverage`.
- [ ] **Step 2: Esegui** `.venv/Scripts/python -m pytest server/tests -q`. Atteso: falliscono solo i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): decodifica Range Test e tabelle copertura`.

### Task 2: Server, calcoli della copertura e registratore

**File:**
- Crea: `server/meshlens/coverage.py`
- Modifica: `server/meshlens/app.py`. L'evento passa al registratore dopo `ingestor.handle`, sia da MQTT sia dalle radio: si usa una funzione `on_event` comune che chiama i due in sequenza.
- Test: `server/tests/test_coverage.py`

**Interfacce:**
- Usa: lo `Store` del Task 1; `live.nodes` per le posizioni della base.
- Produce, come funzioni pure in `coverage.py`:
  - `precision_m(bits: int | None) -> int | None`: None se esatta;
  - `haversine_m(lat1, lon1, lat2, lon2) -> float`;
  - `interpolate_position(track: list[dict], t: float, max_gap: float = 120) -> tuple[float, float, int | None] | None`:
    1. tra due posizioni del percorso che circondano `t`, entrambe entro `max_gap` da `t`, interpola linearmente nel tempo; i bit di precisione sono il minimo dei due;
    2. altrimenti usa la posizione più vicina entro `max_gap`;
    3. altrimenti None.
  - `missing_points(points: list[dict], interval_s: int, track: list[dict]) -> list[dict]`:
    - lavora per `segment`: tra il seq minimo e il massimo ricevuto, ogni seq assente è un punto mancante;
    - l'ora si stima interpolando tra i due punti ricevuti vicini, in proporzione al seq, oppure con `interval_s` se c'è un solo vicino;
    - la posizione viene da `interpolate_position`;
    - un tratto con un solo punto non ha mancanti.
  - `summarize(session: dict, points: list[dict], missing: list[dict]) -> dict`: costruisce il riepilogo del contratto.
    - `expected = received + missing` in modalità rangetest;
    - `loss_pct = round(100 * missing / expected, 1)`, oppure null se `expected` vale 0;
    - le distanze si calcolano da `base_lat`/`base_lon` se impostati.
- Produce, come classe: `CoverageRecorder(store, live, bus, clock=time.time)`.
  - `start()`: carica la sessione attiva e il suo tratto e ultimo seq correnti.
  - `handle(ev: MeshEvent) -> None`:
    1. ricorda in memoria l'ora dell'ultimo Range Test per `(radio_id, from_node)`, anche fuori sessione;
    2. con una sessione attiva, registra nel percorso le posizioni del mobile da qualsiasi fonte;
    3. registra come punti:
       - in modalità `rangetest`, i Range Test con seq valido del mobile ricevuti dalla radio della sessione, solo RF (Review Focus 4). La posizione viene da `interpolate_position` sul percorso fino a quel momento;
       - in modalità `position`, le posizioni del mobile ricevute in RF dalla radio della sessione, con le loro coordinate.
    4. Se un seq è minore dell'ultimo, apre un nuovo `segment` (Review Focus 1).
    5. A ogni nuova posizione del percorso, completa quelli tra i punti degli ultimi 120 s che non hanno ancora una posizione (`update_point_position`). Così un Range Test arrivato poco prima della posizione ottiene comunque coordinate (Review Focus 2).
    6. Pubblica `{"type":"coverage", …}` a ogni punto nuovo.
  - `start_session(radio_id, mobile_num, mode, interval_s, name, base_lat, base_lon, channel_index) -> dict`: se `base_lat` manca, usa la posizione del nodo della radio dal `live`.
  - `stop_session(reason="manual") -> dict | None`.
  - `tick()`: chiamato ogni 60 s da `app.py`, ferma con `reason="timeout"` una sessione iniziata da più di **8 h**.
  - `detail(id) -> dict`: riepilogo, punti con `distance_m`, `missing_points` e `track`.
  - `rangetest_age(radio_id, mobile_num) -> float | None`.

- [ ] **Step 1: Test che falliscono**
  - `test_interpolate_between_and_nearest_and_none`: percorso a t=0 (45.0, 11.0) e t=100 (45.1, 11.0), t=50 → (45.05, 11.0). Un solo punto a t=0 e t=90 → la posizione a t=0. t=500 → None.
  - `test_missing_points_per_segment` (Review Focus 1): tratto 0 con seq [0, 1, 4] ai tempi [0, 30, 120] → mancanti 2 e 3 con tempi 60 e 90. Tratto 1 con seq [0, 1] → nessun mancante; `loss_pct` = 2/5 = 40.0.
  - `test_summarize_position_mode_has_no_loss`.
  - `test_recorder_ignores_other_nodes_and_radios` (Review Focus 4).
  - `test_recorder_new_segment_on_seq_drop`.
  - `test_point_without_position_then_backfilled` (Review Focus 2): Range Test a t=100 senza percorso → lat None. Posizione a t=110 → il punto ottiene le coordinate.
  - `test_point_without_any_position_counts_but_null`.
  - `test_session_auto_stops_after_8h`: orologio finto → `end_reason` vale "timeout".
  - `test_active_session_resumes_after_restart`: un nuovo recorder sullo stesso store continua con lo stesso tratto e lo stesso ultimo seq.
  - `test_rangetest_age_tracked_outside_session`.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): registratore sessioni di copertura`.

### Task 3: Server, rotte della copertura

**File:**
- Modifica: `server/meshlens/api.py`, `server/meshlens/app.py`
- Test: `server/tests/test_api_coverage.py`

**Interfacce:**
- Usa: `CoverageRecorder`, `precision_m` (Task 2); `RadioManager.radios()`, per lo stato `connected` e i canali.
- Produce: tutte le rotte del contratto, con questi errori in JSON: `{"detail": "...", "code": "approx_position"}` per il caso della precisione, gli altri come `{"detail": "..."}` già in uso.
- Controllo della precisione all'avvio: si usano i `precision_bits` dell'ultima posizione del mobile nel `live`. Se valgono meno di 32 e `accept_approx` non è true, si risponde 400 con `code: "approx_position"` e detail `"Le posizioni del nodo mobile sono approssimate (circa ±N m): usa un canale privato con precisione piena oppure continua sapendolo."`, dove N è `precision_m`.
- `mobile_id` si accetta in qualunque maiuscola o minuscola e si normalizza con `node_id`.

- [ ] **Step 1: Test che falliscono**
  - `test_check_reports_gps_and_precision`: mobile con posizione di 5 minuti fa a 13 bit → `gps_ok` true e `precision_m` ≈ 2900 (tolleranza 10%). Posizione di 20 minuti fa → `gps_ok` false.
  - `test_start_requires_connected_radio_and_gps`: rispettivamente 400 e 400 con il messaggio GPS.
  - `test_start_approx_needs_accept`: 400 con `code` `approx_position`; con `accept_approx: true` → 201.
  - `test_start_conflict_when_active`: 409.
  - `test_stop_patch_delete`: DELETE sulla sessione attiva → 409; dopo lo stop → 204 o 200.
  - `test_detail_shape`: chiavi del contratto presenti.
  - `test_default_name`: il nome inizia con `"Prova "`.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): rotte sessioni di copertura`.

### Task 4: Interfaccia, scheda Copertura (guida, sessione in corso, storico)

**File:**
- Crea: `web/src/components/Coverage.svelte`, `web/src/components/CoverageSetup.svelte`, `web/src/lib/coverage.ts`, `web/src/lib/coverage.test.ts`
- Modifica: `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/lib/stores.svelte.ts`, `web/src/lib/ws.ts`, `web/src/App.svelte`

**Interfacce:**
- Usa: i contratti JSON.
- Produce:
  - tipi `CoverageSession`, `CoverageDetail`, `CoveragePoint`, `CoverageMissing`, `CoverageCheck`;
  - funzioni API `coverageSessions()`, `coverageSession(id)`, `startCoverage(body)`, `stopCoverage(id)`, `patchCoverage(id, body)`, `deleteCoverage(id)`, `coverageCheck(radioId, mobileId)`. `ApiError` deve esporre `code` dal JSON di errore, se presente;
  - store `coverage`: `{sessions: CoverageSession[], openId: number|null, detail: CoverageDetail|null}`. Si aggiorna dal WS: sostituisce il riepilogo e, se `session.id === openId`, aggiunge il punto al dettaglio. Si ricarica alla riconnessione;
  - in `coverage.ts`: `checklist(check: CoverageCheck | null, mode): {key, ok: boolean | null, label, hint}[]`, che è la lista dei passi con il loro stato, e `formatLoss(s)`.

**Comportamento:**
- Nuova scheda **"Copertura"**, dopo Rete.
- In alto, se c'è una sessione attiva, un riquadro "In corso", per esempio "In corso: Prova 21/11 15:30 — 42 punti, 3 mancanti (6,7%), ultimo SNR 4 dB, da 12 min", con il pulsante **"Ferma"**. Sotto, il pulsante "Nuova prova", disabilitato durante una sessione attiva.
- **CoverageSetup** è una procedura in un solo pannello:
  1. scelta della radio di base, tra quelle collegate;
  2. scelta del nodo mobile, con ricerca per nome o id tra i nodi noti; di default propone i nodi "miei" non collegati;
  3. scelta della modalità: Range Test (consigliata) o solo posizione;
  4. intervallo in secondi, default 30.
- Sotto c'è la **guida** da `checklist`. Si aggiorna ogni 5 s chiamando `coverageCheck`, con ✓ verde, ⚠ giallo oppure "—" per lo stato. I passi sono:
  - "Radio di base collegata";
  - "Nodo mobile sentito";
  - "Posizione GPS recente (≤ 10 min)";
  - "Precisione della posizione". Esatta → ✓. Approssimata → ⚠ "circa ±N m: per una mappa precisa usa un canale privato con precisione piena", con il suggerimento sotto;
  - "Pacchetti Range Test ricevuti", solo in modalità Range Test. Se non arrivano compare ⚠ "Attiva il modulo Range Test sul nodo mobile (mittente ogni 30 s) e sulla base (ricevitore)".
- Una sezione apribile **"Come preparare le radio"** spiega i passi con l'app Meshtastic:
  - canale privato uguale su entrambe, con posizione a precisione piena;
  - Range Test sul mobile come mittente ogni 30 s;
  - Range Test sulla base come ricevitore (mittente 0);
  - posizione del mobile ogni 30 s, con smart position a intervallo minimo 30 s;
  - spegnere il modulo a fine prova.
  - Più la nota: "Durante la prova il telefono non serve: MeshLens registra da solo."
- **"Avvia prova"** è attivo quando il GPS è ok e la radio è collegata.
  - Se il server risponde con il codice `approx_position`, compare una conferma con il suo messaggio e i pulsanti "Continua con posizioni approssimate" (riprova con `accept_approx: true`) e "Annulla".
  - Gli altri errori si mostrano come testo.
- **Storico:** elenco delle sessioni con nome, data, durata, punti, perdita % e distanza massima. Toccando una sessione si apre, cioè si imposta `openId` e si carica il dettaglio, e la mappa si centra sui punti (Task 5). Da lì si rinomina, si scrivono note, e si elimina con una conferma "Eliminare definitivamente questa prova?".
- Su telefono tutto sta nel pannello a scomparsa, come le altre schede.

- [ ] **Step 1: Test vitest che falliscono** in `coverage.test.ts`:
  - `checklist(null)` → tutti i passi con `ok` null;
  - check con `gps_ok` false → il passo GPS ha `ok` false;
  - `precision_m` 2900 → passo precisione con `ok` false e testo che contiene "2,9 km" (usa `formatPrecision`);
  - in modalità `position` non c'è il passo Range Test;
  - `formatLoss` con null → "—".
- [ ] **Step 2: Esegui** `cd web; npx vitest run`. Atteso: falliscono.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): scheda Copertura con guida e storico`.

### Task 5: Interfaccia, risultati sulla mappa e posizione della base

**File:**
- Modifica: `web/src/components/MapView.svelte`, `web/src/components/Coverage.svelte`, `web/src/lib/coverage.ts`, `web/src/lib/coverage.test.ts`

**Interfacce:**
- Usa: lo store `coverage` (Task 4); `snrColor` (`web/src/lib/links.ts`).
- Produce: `coverageGeoJSON(detail: CoverageDetail): {points: FeatureCollection<Point>, missing: FeatureCollection<Point>, track: FeatureCollection<LineString>, base: FeatureCollection<Point>}`.
  - I punti senza coordinate si saltano (Review Focus 2).
  - `properties` dei punti: `{color, snr, rssi, seq, time, distance_m}`.
  - Il percorso è ordinato per tempo.

**Comportamento:**
- Quando c'è una sessione aperta, la mappa disegna sopra ai nodi:
  - il percorso, linea blu sottile;
  - i punti ricevuti, cerchi colorati per SNR;
  - i punti mancanti, piccole croci o cerchi grigi vuoti;
  - la base, un simbolo distinto.
- Toccando un punto compare un popup con seq, ora, SNR, RSSI, salti e distanza dalla base. Le distanze si scrivono in m sotto i 1000, poi in km con un decimale.
- All'apertura la mappa si adatta ai punti (`fitBounds`).
- Un pulsante "Chiudi prova" torna alla mappa normale.
- I livelli si ricreano dopo un cambio di stile, come gli altri.
- Se la base non ha posizione (Heltec senza GPS), compare l'avviso "Posizione della base sconosciuta: tocca la mappa per impostarla". Il pulsante "Imposta posizione base" attiva la modalità di scelta: il tocco successivo sulla mappa salva le coordinate con PATCH e ricarica il dettaglio, così le distanze compaiono.
- Durante una sessione attiva aperta, i punti nuovi compaiono in diretta dal WS.

- [ ] **Step 1: Test vitest che falliscono:**
  - `coverageGeoJSON` salta i punti con `lat` null;
  - il percorso è ordinato per tempo anche se l'input non lo è;
  - il colore di un punto con SNR −12 è `#c8382e`;
  - la base è assente se `base_lat` è null.
- [ ] **Step 2: Esegui vitest.** Atteso: falliscono.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): risultati copertura sulla mappa e posizione della base`.

### Task 6: Prova con le radio vere (rimandata alla fine di tutte le fasi, scelta dell'utente)

- [ ] Prepara le radio con la guida, usando un canale privato con precisione piena: Heltec V3 come base via USB, T-Pager come mobile.
- [ ] Controlla che la guida diventi tutta verde e avvia la prova.
- [ ] Fai un giro a piedi o in auto senza telefono; al ritorno controlla punti, percorso, mancanti e statistiche.
- [ ] Ripeti sul canale principale accettando le posizioni approssimate e verifica l'avviso.
- [ ] Riavvia il T-Pager durante la prova: si apre un nuovo tratto e non compaiono mancanti assurdi.

---

**Esecuzione in parallelo:** i Task 1→3 (server, nella cartella principale) e 4→5 (interfaccia, in un worktree) si parlano solo tramite i contratti JSON. Si eseguono in parallelo e poi si uniscono sul ramo `fase4`, creato da `fase3`.
