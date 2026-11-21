# MeshLens Fase 6 — Mappe offline e rifinitura: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:**
- mappe utilizzabili senza internet: mondo a basso dettaglio, Italia a zoom 14 e aree scelte dall'utente, scaricate con un passo guidato in Impostazioni → Mappe offline;
- passaggio automatico tra mappa online e offline;
- primo caricamento della mappa più rapido;
- rifinitura dell'uso da telefono.

**Architettura:**
- **Server:**
  - `maps.py` gestisce lo strumento ufficiale `go-pmtiles`, scaricato una volta da GitHub con verifica SHA-256 e usato per ritagliare dal planet Protomaps giornaliero con letture a range;
  - gli archivi `.pmtiles` stanno in `data/maps/`;
  - un endpoint `/tiles/{z}/{x}/{y}.mvt` legge le tessere dagli archivi in ordine di priorità (aree e Italia prima, poi mondo) con il pacchetto Python `pmtiles`, così la mappa ha **una sola sorgente** vettoriale.
- **Interfaccia:**
  - uno stile Protomaps generato con `@protomaps/basemaps`;
  - glifi e sprite inclusi nell'app, quindi nessuna risorsa esterna offline;
  - lo stile OpenFreeMap liberty resta per l'online.

**Tecnologie:** in più alle precedenti:
- `pmtiles` (PyPI, Reader);
- `go-pmtiles` (exe Windows ufficiale, BSD-3);
- `@protomaps/basemaps` (npm);
- glifi Noto Sans (OFL) e sprite (MIT) da `protomaps/basemaps-assets`.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md` (§5.2, §9 "Mappe"). Ricerca: `docs/superpowers/research/2026-11-21-mappe-offline.md`.

## Global Constraints

- Testi in italiano.
- **Scelte dell'utente:**
  - ritaglio con `go-pmtiles` ufficiale;
  - Italia a **maxzoom 14**: bbox `6.6,36.6,18.6,47.1`;
  - mondo a **maxzoom 6**, senza bbox;
  - in più si può scaricare l'**area visibile** sulla mappa, sempre a maxzoom 14.
- **Fonte dei dati:**
  - `https://build.protomaps.com/YYYYMMDD.pmtiles`. Si prova con `HEAD` da oggi indietro fino a 7 giorni e si usa la prima che risponde 200;
  - impostazione `maps_source_url` per un URL personalizzato, che ha la precedenza se valorizzato.
- **Attribuzione obbligatoria (ODbL)** sulla mappa offline: `© OpenStreetMap contributors · Protomaps`.
- **Strumento go-pmtiles:**
  - versione fissata nel codice (l'ultima release stabile di `protomaps/go-pmtiles` al momento dell'implementazione), con URL dell'asset Windows x86_64 e **SHA-256 fissati nel codice**, presi dal `checksums.txt` di quella release;
  - si scarica **solo su azione dell'utente** ("Scarica strumento" o il primo download di una mappa, con conferma che mostra nome, fonte e dimensione);
  - si salva in `data/tools/` dopo la verifica dell'impronta;
  - un'impronta diversa fa rifiutare il file (cancellato) con il messaggio "Impronta del file non valida: download annullato".
- **Spazio su disco:** prima di ogni download si controlla con `shutil.disk_usage` che restino libere almeno la stima × 1,5 + 1 GB, altrimenti 409 "Spazio su disco insufficiente: servono circa N GB".
- **Stime delle dimensioni**, mostrate prima di confermare: mondo 0,2 GB; Italia z14 2 GB; area = `2 GB × (area bbox / area bbox Italia)`, con un minimo di 0,05 GB.
- **Un download alla volta.** Si può annullare: il processo termina e il file parziale viene cancellato.
- **Ritaglio:**
  - comando `pmtiles extract <url> <out.tmp> [--bbox=minLon,minLat,maxLon,maxLat] --maxzoom=N --download-threads=4`;
  - il file temporaneo viene rinominato in `.pmtiles` solo a fine riuscita;
  - all'avvio del server si cancellano i `.tmp` rimasti.
- **Endpoint tessere:**
  - `GET /tiles/{z}/{x}/{y}.mvt` cerca in ordine aree (la più recente prima), poi Italia, poi mondo;
  - restituisce i byte della tessera con `Content-Type: application/x-protobuf` e `Content-Encoding: gzip` se l'archivio dichiara la compressione gzip;
  - 204 se non c'è nessuna tessera;
  - si esclude dalla compressione GZip del server;
  - Reader con cache delle directory.
- **Modalità mappa** (impostazione `map_mode`):
  - `auto` (default): online se il browser è online e lo stile online si carica entro 8 s **e** sono presenti mappe offline; altrimenti offline se ci sono archivi, altrimenti lo stile di riserva attuale senza tessere;
  - `online`;
  - `offline`.
  - Il passaggio usa `setStyle` e ricrea tutti i livelli MeshLens, che è già supportato.
- **Risorse offline incluse nell'app** (in `web/public/map-assets/`):
  - sprite `light` (png e json, @1x e @2x);
  - glifi Noto Sans Regular, Medium e Italic per gli intervalli `0-255`, `256-511`, `512-767`, `768-1023`, `1024-1279`, `8192-8447`.
  - Le etichette con caratteri fuori da questi intervalli (per esempio arabo o CJK) possono non comparire offline. È una scelta accettata.
- **Tema offline:** `namedFlavor('light')`, lingua `it`.

## Contratti JSON

- **Mappa offline:** `{id, name, kind:"world"|"italy"|"area", bbox:[minLon,minLat,maxLon,maxLat]|null, maxzoom, size_bytes, created, source_date:"YYYYMMDD"|null}`.
- **Stato:** `GET /api/maps` → `{maps:[Mappa], tool:{installed:bool, version, size_bytes}, job:<Lavoro>|null, disk_free_bytes, mode:"auto"|"online"|"offline"}`.
- **Lavoro:** `{id, kind:"tool"|"world"|"italy"|"area", name, status:"running"|"done"|"failed"|"cancelled", step, bytes_done, bytes_total:int|null, error:string|null, started, ended}`.
  - WebSocket: `{"type":"map_job","job":{...}}` almeno ogni 2 s mentre gira, più ogni cambio di stato.
- **Stima:** `POST /api/maps/estimate` body `{kind, bbox?}` → `{estimate_bytes, source_url, source_date, needs_tool:bool, tool_size_bytes}`.
  - 502 "Nessuna mappa Protomaps disponibile negli ultimi 7 giorni" se nessuna data risponde.
- **Rotte**, tutte con `require_auth`; quelle POST con JSON:
  - `POST /api/maps/download` body `{kind, bbox?, name?}` → 202 Lavoro. Errori: 409 per un lavoro già in corso o spazio insufficiente; 400 per una bbox non valida (fuori da −180..180 e −85..85, min ≥ max, area > 40°×40°).
    - Se lo strumento manca, il lavoro lo scarica prima (`kind` del primo passo `tool`).
  - `POST /api/maps/jobs/{id}/cancel`;
  - `DELETE /api/maps/{id}`;
  - `PUT /api/settings` accetta `map_mode` e `maps_source_url` (stringa vuota o URL `https://` che termina con `.pmtiles`);
  - `GET /tiles/{z}/{x}/{y}.mvt` (anche questa autenticata con il cookie);
  - `GET /api/maps/style-info` → `{has_offline:bool, maxzoom:int, bounds:[...]}`, usata dall'interfaccia per costruire lo stile offline.

## Review Focus

1. **Annullare a metà o chiudere il server durante un download:** nessun file `.pmtiles` corrotto viene usato. Il `.tmp` viene cancellato subito all'annullamento oppure al prossimo avvio. Il processo figlio non resta vivo dopo la chiusura del server.
2. **Strumento con impronta sbagliata o download interrotto:** non viene mai eseguito un file non verificato.
3. **Tessere sovrapposte:** a zoom 5 in Italia si usa l'archivio Italia, non il mondo. Fuori dall'Italia a zoom 10, senza area scaricata, si risponde 204, e la mappa mostra il mondo sovra-ingrandito oppure niente, senza errori a cascata.
4. **Nessuna mappa offline e nessuna rete:** si vede lo stile di riserva attuale e un avviso "Mappa non disponibile offline: scaricala da Impostazioni → Mappe offline". Nessun ciclo di cambi di stile.
5. **Passaggio online ↔ offline:** marker, cluster, collegamenti, risultati di copertura e scelta della base restano funzionanti dopo `setStyle`. Il passaggio non si ripete in un ciclo quando la rete va e viene (si commuta al massimo una volta ogni 30 s).

---

### Task 1: Server, strumento, download e archivi

**File:**
- Crea: `server/meshlens/maps.py`
- Modifica: `server/meshlens/api.py`, `server/meshlens/app.py`, `server/meshlens/settings.py`, `pyproject.toml` (dipendenza `pmtiles`)
- Test: `server/tests/test_maps.py`, `server/tests/test_api_maps.py`

**Interfacce prodotte:**
- `TOOL_VERSION`, `TOOL_URL`, `TOOL_SHA256` (costanti);
- `find_source(head: Callable[[str], int], today: date, custom: str | None) -> tuple[str, str | None]`, che restituisce url e data, oppure solleva `MapsError`;
- `estimate_bytes(kind, bbox) -> int`;
- `validate_bbox(bbox) -> list[float]`;
- `class MapsManager(data_dir, store_settings, bus, runner, downloader, clock)`, con:
  - `status() -> dict`;
  - `estimate(kind, bbox) -> dict`;
  - `start(kind, bbox, name) -> job`;
  - `cancel(job_id)`;
  - `delete(map_id)`;
  - `cleanup_tmp()`.
- `runner` è iniettabile per i test. Di default è `asyncio.create_subprocess_exec` e uccide il processo all'annullamento e alla chiusura.
- `downloader` è iniettabile; di default un download a blocchi con `httpx` o `urllib`, in un thread, che pubblica l'avanzamento.
- **Avanzamento del ritaglio:** si stimano `bytes_done` dalla dimensione del file `.tmp` ogni 2 s, mentre `bytes_total` è la stima. Si analizza anche l'output di go-pmtiles se contiene percentuali.
- **Elenco delle mappe:** file `data/maps/maps.json`, scritto in modo atomico.

- [ ] **Step 1: Test che falliscono**
  - `test_find_source_walks_back_7_days`: risponde 200 solo per oggi − 3 → si usa quella data. Nessuna data → `MapsError`. Un URL personalizzato ha la precedenza.
  - `test_estimate_and_bbox_validation`: Italia 2 GB; mondo 0,2 GB; un'area metà di quella italiana → circa 1 GB; area minima 0,05 GB; bbox invertita o troppo grande → errore.
  - `test_tool_bad_checksum_rejected` (Review Focus 2): un downloader finto restituisce byte sbagliati → lavoro `failed` con il messaggio dell'impronta; nessun file in `data/tools/`.
  - `test_extract_success_renames_tmp`: il runner finto scrive un `.tmp` → si ottengono `.pmtiles` e una voce in `maps.json`.
  - `test_cancel_kills_and_deletes_tmp` (Review Focus 1).
  - `test_cleanup_tmp_on_start`.
  - `test_disk_space_check_409`.
  - `test_one_job_at_a_time`.
  - `test_settings_map_mode_and_source_validation`.
- [ ] **Step 2: Esegui** `.venv/Scripts/python -m pytest server/tests -q`. Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.** Installa `pmtiles` nel venv e aggiungilo a `pyproject.toml`. Prendi versione, URL e SHA-256 dello strumento dalla release ufficiale (`checksums.txt`) e scrivi in un commento la data della verifica.
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): gestione mappe offline (strumento, ritaglio, archivi)`.

### Task 2: Server, endpoint delle tessere e informazioni sullo stile

**File:**
- Crea: `server/meshlens/tiles.py`
- Modifica: `server/meshlens/api.py`, `server/meshlens/app.py`
- Test: `server/tests/test_tiles.py`

**Interfacce:**
- Usa: l'elenco delle mappe del Task 1.
- Produce: `class TileStore(maps_dir)`, con
  - `reload()`, chiamato dopo ogni download o cancellazione;
  - `get(z, x, y) -> tuple[bytes, str | None] | None`, che restituisce i byte e la codifica;
  - `info() -> dict`, che dà `has_offline`, il `maxzoom` massimo e i `bounds` uniti.
- Ordine di ricerca: aree dalla più recente, poi Italia, poi mondo. Si salta un archivio se `z` è sopra il suo maxzoom o se la tessera è fuori dalla sua bbox.
- Le rotte `/tiles/...` e `/api/maps/style-info`. `/tiles` è esclusa dal middleware GZip.

- [ ] **Step 1: Test che falliscono**
  - Gli archivi di prova si creano con `pmtiles.writer` dentro il test: un "mondo" con una tessera z5 e un'"Italia" con le stesse coordinate z5 e una tessera z10.
  - `test_priority_italy_over_world_same_tile` (Review Focus 3).
  - `test_missing_tile_204`.
  - `test_gzip_header_when_archive_gzip`.
  - `test_reload_after_delete`.
  - `test_style_info`.
  - `test_tiles_require_auth`.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): endpoint tessere offline con priorità degli archivi`.

### Task 3: Interfaccia, stile offline, modalità e prima apertura più rapida

**File:**
- Crea: `web/src/lib/mapstyle.ts`, `web/src/lib/mapstyle.test.ts`, `web/public/map-assets/` (sprite e glifi elencati nelle Global Constraints, scaricati da `protomaps/basemaps-assets` e committati)
- Modifica: `web/src/components/MapView.svelte`, `web/package.json` (`@protomaps/basemaps`), `web/index.html` (preconnect a `tiles.openfreemap.org`)

**Interfacce:**
- Usa: `/api/maps/style-info`, `/tiles/{z}/{x}/{y}.mvt`, l'impostazione `map_mode`.
- Produce:
  - `offlineStyle(info): StyleSpecification`:
    - una sorgente `protomaps`, di tipo vector, con `tiles: [location.origin + '/tiles/{z}/{x}/{y}.mvt']`, `maxzoom: info.maxzoom` e `attribution` obbligatoria;
    - `layers('protomaps', namedFlavor('light'), {lang:'it'})`;
    - `glyphs: '/map-assets/fonts/{fontstack}/{range}.pbf'` e `sprite: location.origin + '/map-assets/sprites/light'`.
  - `chooseMode(mode, online: boolean, hasOffline: boolean, onlineFailed: boolean): 'online'|'offline'|'fallback'`, una funzione pura.
  - `canSwitch(lastSwitch, now)`: limite di un cambio ogni 30 s.

**Comportamento:**
- All'avvio, se `chooseMode` dà offline, si usa subito lo stile offline. Così la prima apertura è istantanea anche quando lo stile online sarebbe lento.
- Se si è online e la modalità è `auto`, si passa allo stile online solo dopo il suo caricamento riuscito (stile precaricato con fetch), al massimo una volta ogni 30 s.
- Ascolta gli eventi `online`/`offline` del browser.
- Senza mappe offline e senza rete compare l'avviso del Review Focus 4.
- `fadeDuration: 0`.
- Il passaggio ricrea tutti i livelli MeshLens con la funzione `setup()` esistente (Review Focus 5).
- **Misura del primo caricamento:** lo step 4 lo verifica nel browser e annota nel report i tempi prima e dopo.

- [ ] **Step 1: Test vitest che falliscono:**
  - tutte le combinazioni di `chooseMode`;
  - `canSwitch` a 29 s dà false e a 30 s true;
  - `offlineStyle` ha una sola sorgente, l'attribuzione OSM e i percorsi locali di glifi e sprite.
- [ ] **Step 2: Esegui** `cd web; npx vitest run`. Atteso: falliscono.
- [ ] **Step 3: Implementa.** Nessun `$effect` deve leggere e scrivere lo stesso `$state`, e i timer vanno puliti.
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): stile offline Protomaps, modalità mappa e avvio rapido`.

### Task 4: Interfaccia, Impostazioni → Mappe offline

**File:**
- Crea: `web/src/components/OfflineMaps.svelte`, `web/src/lib/maps.ts`, `web/src/lib/maps.test.ts`
- Modifica: `web/src/components/Settings.svelte`, `web/src/lib/api.ts`, `web/src/lib/types.ts`, `web/src/lib/stores.svelte.ts`, `web/src/lib/ws.ts`, `web/src/components/MapView.svelte` (fornisce la bbox dell'area visibile)

**Interfacce:**
- Usa: le rotte `/api/maps/*` e il WS `map_job`.
- Produce: `formatBytes`, `jobPercent(job)`, `bboxFromBounds(bounds)` (arrotondata a 4 decimali).

**Comportamento:**
- La sezione **"Mappe offline"** in Impostazioni mostra:
  - la modalità mappa (Automatica, Solo online, Solo offline);
  - lo spazio libero;
  - l'elenco delle mappe con nome, zona, dimensione, data dei dati e il pulsante "Elimina", con conferma.
- Pulsanti **"Scarica mondo (base)"**, **"Scarica Italia"** e **"Scarica area visibile"**. L'ultimo usa l'area inquadrata adesso sulla mappa e chiede un nome.
- Ognuno chiede prima la stima: compare una conferma con dimensione, fonte e data. Se lo strumento manca, la conferma dice "Verrà scaricato anche lo strumento ufficiale go-pmtiles (≈ N MB) da GitHub".
- Durante il download: barra di avanzamento, passo corrente, pulsante "Annulla". Gli errori si mostrano in chiaro.
- Campo avanzato "Fonte personalizzata (URL .pmtiles)".
- A download finito la mappa ricarica `style-info` e, se è in modalità offline, si aggiorna da sola.

- [ ] **Step 1: Test vitest che falliscono:**
  - `formatBytes(2_000_000_000)` restituisce "2,0 GB";
  - `jobPercent` con `bytes_total` null restituisce null;
  - `bboxFromBounds` arrotonda.
- [ ] **Step 2: Esegui vitest.** Atteso: falliscono.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): impostazioni mappe offline con download guidato`.

### Task 5: Rifinitura per il telefono

**File:** i componenti in `web/src/components/` che risultano difettosi dal controllo.

- [ ] **Step 1:** avvia il server e apri l'app nel browser integrato con viewport 375×812 (preset mobile). Per ogni scheda (Mappa, Nodi, Rete, Copertura, Chat, Radio, Impostazioni) e per i pannelli (dettaglio nodo, Configura, anteprima delle modifiche, prova di copertura) cattura una schermata e annota i difetti: contenuto tagliato, scorrimento orizzontale non voluto, pulsanti più piccoli di 40 px, testo sotto i 13 px, sovrapposizioni con la barra di stato.
- [ ] **Step 2:** correggi i difetti trovati con CSS e piccole modifiche. Non cambiare funzionalità.
- [ ] **Step 3:** ricontrolla le stesse schermate; vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 4: Commit** `fix(web): rifinitura interfaccia per telefono`.

### Task 6: Prova con le radio e offline reale (rimandata alla fine, scelta dell'utente)

- [ ] Scarica il mondo e l'Italia; stacca internet e riavvia: la mappa si vede e le radio funzionano.
- [ ] Scarica un'area di confine e verifica la priorità delle tessere.
- [ ] Prova l'uso dal telefono sulla Wi-Fi di casa.

---

**Esecuzione in parallelo:** i Task 1→2 (server) e 3→4 (interfaccia, in un worktree) si parlano tramite i contratti. Il Task 5 si fa dopo l'unione. Ramo `fase6`, creato da `fase5`.
