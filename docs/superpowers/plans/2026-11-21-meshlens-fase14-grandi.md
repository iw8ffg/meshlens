# MeshLens Fase 14 — Progetti grandi: copertura prevista, Store & Forward, interfaccia in inglese: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** realizzare le proposte C1, C2 e C3 di `docs/superpowers/research/2026-11-21-proposte-prossima-release.md`.
- **C1, copertura prevista:** per un sito (posizione, altezza dell'antenna, frequenza EU_868, potenza, guadagni) MeshLens calcola un raster di copertura prevista con il modello ITM (Longley-Rice, modo punto-punto su radiali). Usa i dati di altitudine scaricati su richiesta e conservati nella cartella dati. Mostra il raster sulla mappa e lo confronta con i punti misurati delle prove di copertura.
- **C2, Store & Forward:** riconoscere i nodi router S&F e chiedere loro lo storico dalla radio collegata. I messaggi rigiocati entrano nel percorso normale, senza duplicati. Il pulsante «Recupera messaggi persi» sta nella scheda Radio.
- **C3, interfaccia in inglese:** tutta l'interfaccia web passa per un catalogo di testi. L'italiano resta predefinito, l'inglese si sceglie in Impostazioni e la scelta resta salvata. Anche i messaggi d'errore del server vengono tradotti, tramite uno strato di corrispondenze lato client.

**Architettura:**
- **Parte A (C1 + C2), da eseguire subito, in parallelo con la fase 12:**
  - **C1:**
    - moduli nuovi `elevation.py` (riquadri Terrarium: download, cache, decodifica PNG con `zlib` e `numpy`), `itm.py` (porting Python dell'ITM NTIA, modo punto-punto), `prediction.py` (profili radiali, bilancio di collegamento, raster in griglia Mercatore, calcolo in un `ProcessPoolExecutor`) e `prediction_service.py` (lavoro unico con avanzamento sul bus, risultati in file JSON, confronto con le sessioni);
    - rotte in un modulo a parte, `api_prediction.py`;
    - interfaccia: `lib/prediction.ts`, `lib/prediction.svelte.ts`, `lib/map/PredictionLayer.ts` e `components/Prediction.svelte` nella scheda Copertura. I colori vengono dai token e sono applicati nel browser: il server manda solo valori numerici.
  - **C2:**
    - modulo nuovo `storeforward.py`: decodifica dei pacchetti `STORE_FORWARD_APP`, registro dei router (tabella `sf_routers` creata in `SCHEMA` con `CREATE TABLE IF NOT EXISTS`), richieste `CLIENT_HISTORY` e `CLIENT_STATS`, rigioco con deduplica sulla chiave del messaggio;
    - rotte in `api_storeforward.py`;
    - interfaccia in `components/StoreForward.svelte`, aperta dalla scheda Radio;
    - in `radio.py`, `rf_convert.py`, `events.py`, `ingest.py` e `app.py` solo modifiche piccole e dichiarate.
- **Parte B (C3), da eseguire dopo l'unione delle fasi 12 e 13:**
  - catalogo `lib/i18n/` scritto a mano (`it.ts` è la fonte, `en.ts` è tipizzato sulle stesse chiavi);
  - funzione `t()` reattiva su uno `$state`;
  - formati `Intl` che seguono la lingua;
  - traduzione dei messaggi del server con `server-en.json` (esatti più modelli regex), verificata da un test Python che scorre il codice del server;
  - estrazione dei testi in tre blocchi di componenti, controllata da un test che cerca testo italiano rimasto nei `.svelte`.

**Tech Stack:** Python 3.12 + FastAPI + sqlite3 + `numpy` (già presente come dipendenza di `shapely` e già nel pacchetto PyInstaller: impatto sulla dimensione nullo) + `concurrent.futures.ProcessPoolExecutor`; libreria `meshtastic` 2.7.11 (`storeforward_pb2`, `portnums_pb2.STORE_FORWARD_APP` = 65); Svelte 5 (runes), MapLibre GL 6 (sorgente `image`), vitest.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md`. Proposte: `docs/superpowers/research/2026-11-21-proposte-prossima-release.md` (C1, C2, C3). Restano valide le Global Constraints della fase 8 (`docs/superpowers/plans/2026-11-21-meshlens-fase8-design-invio.md`) e della fase 9.

## Decisioni di progetto (con motivazione)

- **Modello di propagazione: ITM in modo punto-punto, portato dal codice di riferimento NTIA** (`github.com/NTIA/itm`, C++).
  - **Licenza:** opera del governo USA, di fatto dominio pubblico. La licenza chiede di citare NTIA e di segnalare nelle versioni modificate che cosa è cambiato e quando: intestazione di `itm.py` più `THIRD_PARTY_NOTICES.md`.
  - **Verifica:** il repository NTIA pubblica casi di prova con risultato atteso (`p2p.csv` più `pfls.csv`, 5 casi), che diventano i test del porting.
  - **Alternativa scartata:** spazio libero più diffrazione Deygout (ITU-R P.526). È più semplice ma ignora troposcatter e variabilità, ed è proprio la parte "ITM" che rende la previsione credibile.
  - **Costo:** con 360 radiali × fino a 200 passi servono circa 72 000 chiamate ITM, che su 3–4 processi richiedono decine di secondi. Il calcolo gira in un lavoro con avanzamento.
- **Dati di altitudine: AWS Terrain Tiles, formato Terrarium** (`https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`, open data, senza chiave).
  - **Livello:** zoom 12 (circa 27 m/pixel a 45°N). Un'area di 15 km di raggio richiede circa 30–40 riquadri, cioè pochi MB.
  - **Formato:** sono PNG RGB, decodificati con `zlib` e `numpy`. Copernicus GLO-30 è stato scartato: GeoTIFF da 1° × 1° di decine di MB, che richiede un lettore TIFF/DEFLATE con predittore.
  - **Attribuzione richiesta** (`tilezen/joerd/docs/attribution.md`): va in `THIRD_PARTY_NOTICES.md` e sotto il modulo della previsione.
  - **Fondali:** i riquadri contengono la batimetria, cioè quote negative in mare. Per la propagazione la quota è limitata a ≥ 0.
- **Calcolo in processi separati:** `ProcessPoolExecutor` con `max(1, min(4, os.cpu_count() - 1))` processi, creato per ogni lavoro e chiuso a fine lavoro. Con PyInstaller serve `multiprocessing.freeze_support()` nel lanciatore. I test passano un esecutore finto (in linea o a thread).
- **Raster:** valori `int8` del **margine** (RSSI previsto meno sensibilità del preset), compresi tra −127 e +127 dB; −128 = nessun dato. Griglia uniforme in Web Mercator, quindi la sorgente `image` di MapLibre combacia esattamente. Lato massimo 400 celle.
- **Store & Forward** (verificato su `firmware/src/modules/StoreForwardModule.cpp`):
  - **Richiesta:** il router accetta `CLIENT_HISTORY` da qualsiasi nodo. `history.window` è in **minuti**. Il router **ignora** il massimo richiesto e applica il proprio `return_max`.
  - **Canale pubblico:** il router **rifiuta le richieste sul canale predefinito** e risponde con il testo `S&F not permitted on the public channel.`. Quando è occupato risponde `S&F - Busy. Try again shortly.`.
  - **Rigioco:** il router risponde con `ROUTER_HISTORY` (`history_messages` = quanti messaggi seguiranno; `window` in ms). Poi rigioca ogni messaggio come pacchetto `STORE_FORWARD_APP` con `rr` = `ROUTER_TEXT_BROADCAST` o `ROUTER_TEXT_DIRECT`. Il pacchetto conserva `from`, `id`, `channel` e `rx_time` (l'ora originale) del messaggio; `to` è il richiedente anche per i broadcast; il testo sta nel campo `text` (bytes).
  - **Messaggi già inviati:** il router ricorda per ogni client fin dove è arrivato. Una seconda richiesta non rimanda i messaggi già mandati.

## Global Constraints

- Valgono le Global Constraints delle fasi 8 e 9:
  - **italiano** (fino alla Parte B); `Intl` `it-IT`; il meno tipografico «−»;
  - **nessun colore fuori dai token** (`var(--…)` di `tokens.css`; per MapLibre e per il raster i valori letti con `readTokens()` di `lib/map/tokens.ts`);
  - testo ≥ 14 px e aree toccabili ≥ 44 px su telefono (`.vp-phone`, `max-width: 820px`); focus sempre visibile;
  - **nessuna risorsa esterna a runtime**, salvo i download espliciti avviati dall'utente (come le mappe offline). I riquadri di altitudine si scaricano solo dopo il clic su «Scarica e calcola», con la stima in byte mostrata prima.
  - Svelte 5: nessun `$effect` legge e scrive lo stesso `$state`; timer e listener puliti; l'effetto WebSocket e dati di `App.svelte` non segue stati nuovi (leggere con `untrack`).
- **Dipendenze:** nessuna nuova in `pyproject.toml` né in `web/package.json`. `numpy` si importa come dipendenza già garantita da `shapely>=2.0`: va aggiunto un commento in `pyproject.toml` accanto a `shapely`, senza nuova voce.
- **Database:** **nessun nuovo passo di migrazione** (il passo 4 è della fase 12, il 5 della fase 13); `SCHEMA_VERSION` resta com'è. Le tabelle nuove si aggiungono solo a `SCHEMA` con `CREATE TABLE IF NOT EXISTS`, in fondo all'elenco delle tabelle e prima degli indici.
- **Contratti JSON solo additivi.** I messaggi rigiocati hanno la stessa forma degli altri.
- **Legge:** con un EIRP (`tx_power_dbm + antenna_gain_dbi − cable_loss_db`) oltre 29,15 dBm (500 mW ERP, sottobanda 869,4–869,65 MHz) la previsione si calcola lo stesso, ma compare il Banner «Oltre il limite di legge EU 868 (500 mW ERP)». La potenza resta limitata a 0–30 dBm. Le richieste S&F hanno un limite di frequenza, per rispettare il duty cycle.
- **Fase 12 in parallelo** (messaggi: non letti, elenco conversazioni, reazioni e risposte, PKI, waypoint, notifiche esterne). La Parte A **non tocca** `Chat.svelte`, `MessageFeed.svelte`, `lib/chat.ts`, `mqtt_decode.py`, `store.py`, `settings.py`, `lib/types.ts` né i passi di migrazione di `db.py`. File condivisi toccati, solo nei punti indicati:
  - `events.py` (un campo in fondo a `MeshEvent`);
  - `rf_convert.py` (un ramo `elif` in `packet_to_event`);
  - `radio.py` (un metodo nuovo `send_storeforward`);
  - `ingest.py` (una condizione `not ev.replayed` su tre blocchi di `handle`);
  - `db.py` (una tabella in `SCHEMA`);
  - `app.py` (costruzione dei servizi, `on_event`, `start`/`stop`);
  - `api.py` (due campi di `AppContext` e due chiamate `register` in fondo a `create_app`);
  - `lib/ws.ts` (gestori facoltativi nuovi);
  - `MapView.svelte` (una riga in `setup()` e un `$effect`);
  - `Coverage.svelte` e `Radios.svelte` (un componente inserito ciascuno);
  - `packaging/launcher.py` (`freeze_support`);
  - `THIRD_PARTY_NOTICES.md`.
- **Parte B dopo le fasi 12 e 13:** tocca ogni componente, quindi si esegue solo sul `main` che contiene entrambe.
- **Test:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q` (dalla radice; da un worktree `../../.venv/...`) e `cd web && npx vitest run`.
  - **Regola dell'utente:** nei task si eseguono **solo i test mirati** del task, più `npm run check` quando si tocca il web. Le suite complete si eseguono solo nei task «Verifica finale» di ciascuna parte.
- **Nessun cambio di versione** (né `pyproject.toml` né `web/package.json` né `__init__.py`).
- Commit in italiano, stile `feat(server): …` / `feat(web): …` / `fix: …`.

## Contratti JSON (aggiunte)

**Previsione**
- `PredictionParams`:

  ```json
  {"lat":40.85,"lon":14.27,"height_m":10,"tx_power_dbm":22,"antenna_gain_dbi":2,"cable_loss_db":0,"rx_height_m":1.5,"rx_gain_dbi":2,"frequency_mhz":869.525,"preset":"LONG_FAST","radius_km":15}
  ```

  Limiti:

  | Campo | Intervallo |
  |---|---|
  | `lat` | −85..85 |
  | `lon` | −180..180 |
  | `height_m` | 0,5..200 |
  | `tx_power_dbm` | 0..30 |
  | `antenna_gain_dbi` | −5..15 |
  | `cable_loss_db` | 0..20 |
  | `rx_height_m` | 0,5..30 |
  | `rx_gain_dbi` | −5..15 |
  | `frequency_mhz` | 863..870 |
  | `preset` | uno di `PRESETS` |
  | `radius_km` | 1..50 |

  Fuori limite → 400 con un testo italiano che nomina il campo.
- `POST /api/prediction/estimate` body `PredictionParams` → `{"tiles_total":36,"tiles_missing":12,"download_bytes":1080000,"bbox":[w,s,e,n]}`.
- `POST /api/prediction/jobs` body `{"params":PredictionParams,"name":"Tetto casa","download":true}` → 202 `PredictionJob`:
  - 409 `{"detail":"Mancano 12 riquadri di altitudine: scaricali per continuare","code":"elevation_missing"}` se mancano riquadri e `download` è falso;
  - 409 «C'è già un calcolo in corso».
- `PredictionJob`: `{"id":"…","status":"running|done|failed|cancelled","step":"Download dei dati di altitudine|Calcolo|Salvataggio","done":3,"total":12,"error":null,"result_id":null,"started":…,"ended":null}`. Sul WS arriva come `{"type":"prediction_job","job":PredictionJob}`.
- `POST /api/prediction/jobs/{id}/cancel` → `PredictionJob`.
- `GET /api/predictions` → `[PredictionMeta]`, dalla più recente. `PredictionMeta` = `{"id","name","created","params":PredictionParams,"sensitivity_dbm":-131.5,"eirp_dbm":24.0,"bbox":[w,s,e,n],"width":400,"height":400,"covered_km2":123.4}`.
- `GET /api/predictions/{id}` → `PredictionMeta` + `{"values":"<base64 di width*height int8, righe da nord a sud>","nodata":-128}`; 404 se manca.
- `DELETE /api/predictions/{id}` → 204.
- `GET /api/predictions/{id}/compare?session_id=N` → `{"received":40,"missing":8,"received_covered":35,"received_uncovered":5,"missing_covered":3,"missing_uncovered":5,"outside":0,"agreement_pct":83.3,"rssi_bias_db":-2.1,"rssi_rmse_db":6.4,"points":[{"lat","lon","received":true,"measured_rssi":-112,"predicted_rssi":-109.5}]}`. `agreement_pct = 100·(received_covered + missing_uncovered)/(received + missing − outside)`, con una cifra decimale; `null` se il divisore è 0. "Coperto" significa margine ≥ 0.

**Store & Forward**
- `SfRouter`: `{"id":"!a1b2c3d4","name":"Router Vesuvio","radio_id":"r1","last_seen":…,"heartbeat_period":900,"secondary":false,"stats":{"messages_saved":120,"messages_max":3000,"return_max":100,"return_window":240}|null,"last_request":…|null}`. Sul WS arriva come `{"type":"sf_routers","routers":[SfRouter]}`.
- `GET /api/storeforward/routers` → `[SfRouter]`.
- `POST /api/storeforward/request` body `{"radio_id":"r1","router_id":"!a1b2c3d4","window_min":240,"channel_index":1}`, con `window_min` 5..1440 e `channel_index` 0..7. Risposte:
  - 202 → `SfJob`;
  - 409 «Radio non connessa» oppure «C'è già un recupero in corso su questa radio»;
  - 429 «Attendi N s prima di una nuova richiesta a questo router», con `Retry-After`.
- `POST /api/storeforward/probe` body `{"radio_id","router_id","channel_index"}` → 202 `{}`. Chiede le statistiche (`CLIENT_STATS`).
- `GET /api/storeforward/jobs` → `[SfJob]`.
- `SfJob`: `{"id":"…","radio_id","router_id","window_min","channel_index","status":"waiting|receiving|done|failed","expected":12|null,"received":3,"duplicates":2,"error":null,"started":…,"ended":null}`. Sul WS arriva come `{"type":"sf_job","job":SfJob}`.

**Lingua (Parte B):** localStorage `meshlens.lang` = `"it"` oppure `"en"`. Nessun contratto del server cambia.

## Review Focus

1. **App installata (PyInstaller) che avvia un calcolo:** senza `freeze_support()` ogni processo figlio rilancia MeshLens (più server, più icone nel vassoio). Il calcolo deve partire con i figli che fanno solo il loro lavoro, e alla fine nessun processo resta vivo. → Task 3 (test che il lanciatore chiama `freeze_support` prima di tutto) e Task 8 (prova sull'eseguibile).
2. **Download dei riquadri interrotto (rete che cade a metà, risposta 403/404, PNG troncato):**
   - il lavoro finisce `failed` con un testo chiaro;
   - i riquadri già scaricati restano in cache;
   - nessun file corrotto resta col nome definitivo;
   - un nuovo tentativo scarica solo quelli mancanti;
   - un'area tutta in cache si calcola senza rete.
   
   → Task 1.
3. **Lo stesso messaggio rigiocato più volte** (già nel database, già nel feed in memoria, oppure arrivato via radio pochi secondi prima): niente doppioni in chat e nel database. Il contatore «già presenti» cresce. → Task 6.
4. **Richiesta S&F senza esito:**
   - con il canale pubblico arriva il testo di rifiuto → `failed` con «Il router rifiuta le richieste sul canale pubblico: scegli un canale privato condiviso con il router»;
   - con un nodo che non è un router → `failed` dopo 60 s con «Nessuna risposta dal router»;
   - con la radio scollegata durante la ricezione → il lavoro si chiude e non resta mai «in attesa» per sempre.
   
   → Task 6 e Task 7.
5. **Sito sulla costa o in mare:** i riquadri Terrarium hanno quote negative (batimetria). Quindi:
   - la quota si limita a 0 m;
   - sul mare aperto la previsione è quella di una superficie piana;
   - un sito a meno di 1 km da celle senza dati non solleva eccezioni: le chiamate ITM che falliscono ricadono sulla perdita in spazio libero.
   
   → Task 1 e Task 3.

**Review Focus — Parte B**
1. Cambiando lingua con un Modal aperto, la mappa visibile e un lavoro in corso, i testi si aggiornano senza ricaricare la pagina. Restano tradotti anche i popup della mappa, la legenda e il titolo della scheda del browser. → Task 9.
2. Un errore del server con parti variabili («Attendi 7 s…», «Mancano 12 riquadri…») appare in inglese con i numeri giusti; un messaggio senza corrispondenza appare in italiano, senza eccezioni. → Task 9.
3. Date, numeri e il meno «−» in inglese (`en-GB`: 24 h, punto decimale) in grafici, Rete e popup. → Task 9 e Task 10.

---

# Parte A — da eseguire subito (in parallelo con la fase 12)

### Task 1: Dati di altitudine, download, cache e decodifica  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/elevation.py`, `server/tests/test_elevation.py`
- Modify: `pyproject.toml` (solo un commento accanto a `shapely`: «porta con sé numpy, usato da elevation/prediction»)

**Interfaces:**
- Produces in `elevation.py`:
  - costanti: `TERRARIUM_URL = "https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png"`, `DEM_ZOOM = 12`, `TILE_SIZE = 256`, `TILE_BYTES_ESTIMATE = 90_000`;
  - `class ElevationError(Exception)`;
  - `tiles_for_bbox(bbox: list[float], z: int = DEM_ZOOM) -> list[tuple[int, int, int]]`: elenco `(z, x, y)` che copre `[w, s, e, n]`, in ordine per riga e poi per colonna;
  - `bbox_around(lat: float, lon: float, radius_m: float) -> list[float]`;
  - `decode_terrarium_png(data: bytes) -> numpy.ndarray`:
    - restituisce un array `float32` 256 × 256 in metri, calcolati come `R*256 + G + B/256 − 32768`;
    - accetta solo PNG a 8 bit, tipo colore 2 (RGB) o 6 (RGBA), non interlacciato; per il resto solleva `ElevationError`;
    - toglie i filtri PNG 0–4 (None, Sub, Up, Average, Paeth) riga per riga con `numpy`;
  - `class Dem` con:
    - `array: ndarray` (mosaico), `z: int`, `x0: int`, `y0: int` (riquadro in alto a sinistra);
    - `sample(lats: ndarray, lons: ndarray) -> ndarray`: interpolazione bilineare in coordinate pixel Mercatore, con le quote limitate a ≥ 0 (Review Focus 5);
  - `class ElevationCache(root: Path, fetch: Callable[[str], bytes] = default_fetch)`:
    - `root` = `data_dir / "elevation"`, file in `terrarium/{z}/{x}/{y}.png`;
    - `missing(tiles) -> list[tuple]`;
    - `download(tiles, progress: Callable[[int, int], None], cancel: threading.Event, workers: int = 4) -> None`: per ogni riquadro esegue fetch, poi `decode_terrarium_png` come verifica, poi scrive su `.tmp` e fa `os.replace`;
    - `mosaic(bbox) -> Dem`: solleva `ElevationError("Dati di altitudine mancanti per l'area")` se manca un riquadro;
    - `cleanup_tmp() -> None`;
  - `default_fetch(url) -> bytes`:
    - solo `https` (altrimenti `ElevationError("Sono ammessi solo download https")`);
    - `User-Agent` da `maps.user_agent()`, timeout di 30 s;
    - 404 → `ElevationError("Riquadro di altitudine non disponibile: z/x/y")`;
    - altri errori di rete → `ElevationError("Download dei dati di altitudine non riuscito: …")`.

- [ ] **Step 1: test che falliscono** (`test_elevation.py`, con un aiutante `_png(rgb: ndarray, filters: list[int]) -> bytes` scritto nel test, che codifica le righe con i filtri indicati e `zlib`):
  - `test_decode_filters`: un'immagine 256 × 256 casuale codificata con i filtri `[0,1,2,3,4]` a rotazione → stesse quote calcolate a mano;
  - `test_decode_values`: pixel `(128,0,0)` → 0,0 m; `(128,100,128)` → 100,5 m; `(127,0,0)` → −256,0 m;
  - `test_decode_rejects`: PNG a 16 bit, interlacciato o dati troncati → `ElevationError`;
  - `test_tiles_for_bbox`: `bbox_around(40.85, 14.27, 15000)` a z12 → tra 9 e 30 riquadri contigui, senza doppioni;
  - `test_sample_bilinear_and_clamp`: un `Dem` 2 × 2 riquadri con rampa nota → al centro di un pixel il valore esatto; a metà tra due pixel la media; quote negative → 0;
  - `test_download_atomic` (Review Focus 2): il fetch finto restituisce PNG validi per 3 riquadri e solleva un errore al quarto → `ElevationError`; 3 file `.png` presenti, nessun `.tmp`; `missing()` restituisce solo il quarto; un PNG troncato non viene salvato;
  - `test_download_cancel`: `cancel.set()` dopo il primo riquadro → si ferma, `progress` mai oltre il numero scaricato;
  - `test_mosaic_missing`: manca un riquadro → `ElevationError`; `test_fetch_https_only`.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_elevation.py` → FAIL.
- [ ] **Step 3:** implementare `elevation.py`. I riquadri si scaricano con un `ThreadPoolExecutor(workers)`; `cancel` si controlla prima di ogni fetch.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): dati di altitudine Terrarium con cache locale`.

### Task 2: Porting dell'ITM NTIA (modo punto-punto)  _(modello: opus)_

**Files:**
- Create: `server/meshlens/itm.py`, `server/tests/test_itm.py`, `server/tests/data/itm_p2p.csv`, `server/tests/data/itm_pfls.csv`
- Modify: `THIRD_PARTY_NOTICES.md` (voce NTIA ITM)

**Interfaces:**
- Produces in `itm.py`:
  - `@dataclass ItmResult(loss_db: float, warnings: int, mode: int)`, dove `mode` = 1 visibilità, 2 diffrazione, 3 troposcatter, come in NTIA;
  - `class ItmError(Exception)` con l'attributo `code: int` (codici d'errore NTIA);
  - `itm_p2p_loss(h_tx_m: float, h_rx_m: float, pfl: Sequence[float], climate: int = 5, n0: float = 301.0, f_mhz: float = 869.525, pol: int = 1, epsilon: float = 15.0, sigma: float = 0.005, mdvar: int = 12, time: float = 50.0, location: float = 50.0, situation: float = 50.0) -> ItmResult`;
  - `pfl` nel formato NTIA: `[n_punti−1, passo_m, z0, z1, …]`.

Il porting segue i file sorgente NTIA (`itm_p2p.cpp`, `LongleyRice.cpp`, `InitializePointToPoint.cpp`, `FindHorizons.cpp`, `ComputeDeltaH.cpp`, `LinearLeastSquaresFit.cpp`, `DiffractionLoss.cpp`, `KnifeEdgeDiffraction.cpp`, `SmoothEarthDiffraction.cpp`, `LineOfSightLoss.cpp`, `TroposcatterLoss.cpp`, `H0Function.cpp`, `FresnelIntegral.cpp`, `FreeSpaceLoss.cpp`, `TerrainRoughness.cpp`, `SigmaHFunction.cpp`, `Variability.cpp`, `InverseComplementaryCumulativeDistributionFunction.cpp`, `ValidateInputs.cpp`) **funzione per funzione, con lo stesso nome in snake_case**. Usa solo `math`, perché le chiamate sono scalari: `numpy` qui rallenterebbe.
- **Intestazione obbligatoria del file:** «Derivato da NTIA ITM (github.com/NTIA/itm, commit `<sha>`). Modificato da MeshLens il 2026-11-21: porting in Python del solo modo punto-punto TLS». È la condizione di licenza.
- I CSV dei test vengono copiati dal repository NTIA durante lo sviluppo, non a runtime: `p2p.csv` → `itm_p2p.csv`, `pfls.csv` → `itm_pfls.csv`.

- [ ] **Step 1: test che falliscono:**
  - `test_ntia_vectors`: per ognuna delle 5 righe di `itm_p2p.csv` (colonne `h_tx__meter,h_rx__meter,epsilon,sigma,N_0,f__mhz,pol,climate,time,location,situation,mdvar,A__db`) con il profilo corrispondente di `itm_pfls.csv` → `abs(loss_db − A__db) ≤ 0.05`;
  - `test_los_flat_close_to_free_space`: profilo piatto da 101 punti con passo 20 m (2 km), altezze 30/30 m, 869,525 MHz → `mode == 1` e `|loss − (32.45 + 20·log10(2) + 20·log10(869.525))| ≤ 6`;
  - `test_obstacle_increases_loss`: lo stesso profilo con un rilievo di 150 m a metà → perdita ≥ quella piana + 10 dB;
  - `test_invalid_inputs`: `h_tx_m = 0.1` → `ItmError`; `f_mhz = 10` → `ItmError`;
  - `test_speed`: 500 chiamate su un profilo da 200 punti → media < 3 ms per chiamata (solo indicativa: `pytest.skip` se la variabile d'ambiente `CI_SLOW` è impostata).
- [ ] **Step 2:** `pytest -q server/tests/test_itm.py` → FAIL.
- [ ] **Step 3:** implementare `itm.py`.
- [ ] **Step 4:** stesso comando → PASS. Se un vettore NTIA non torna, confrontare i valori intermedi con la variante `_Ex` del C++: niente tolleranze allargate.
- [ ] **Step 5: Commit** `feat(server): porting del modello ITM (NTIA) in modo punto-punto`.

### Task 3: Motore di previsione, radiali, bilancio e raster in processi separati  _(modello: opus)_

**Files:**
- Create: `server/meshlens/prediction.py`, `server/tests/test_prediction.py`
- Modify: `packaging/launcher.py` (`multiprocessing.freeze_support()` come prima istruzione sotto `if __name__ == "__main__":`), `server/meshlens/__main__.py` (stessa chiamata in testa a `main()`; non fa nulla se il programma non è congelato)

**Interfaces:**
- Consumes: `Dem.sample`, `bbox_around`, `ElevationCache.mosaic` (Task 1); `itm_p2p_loss`, `ItmError` (Task 2).
- Produces in `prediction.py`:
  - `PRESETS: dict[str, tuple[int, float]]`, coppie spreading factor e banda in kHz:

    | Preset | SF | Banda (kHz) |
    |---|---|---|
    | `SHORT_TURBO` | 7 | 500 |
    | `SHORT_FAST` | 7 | 250 |
    | `SHORT_SLOW` | 8 | 250 |
    | `MEDIUM_FAST` | 9 | 250 |
    | `MEDIUM_SLOW` | 10 | 250 |
    | `LONG_FAST` | 11 | 250 |
    | `LONG_MODERATE` | 11 | 125 |
    | `LONG_SLOW` | 12 | 125 |

  - `SNR_LIMIT = {7: -7.5, 8: -10, 9: -12.5, 10: -15, 11: -17.5, 12: -20}`;
  - `sensitivity_dbm(preset) -> float` = `round(-174 + 10*log10(bw_khz*1000) + 6 + SNR_LIMIT[sf], 1)`, quindi `LONG_FAST` → −131.5;
  - `EU868_MAX_EIRP_DBM = 29.15`;
  - `@dataclass SiteParams` con i campi e i valori predefiniti di `PredictionParams`. `SiteParams.from_dict(d)` solleva `PredictionError(400, "<campo>: valore fuori dall'intervallo a..b")`; `eirp_dbm` è una proprietà;
  - `class PredictionError(Exception)` con `status: int` e `code: str | None`;
  - `N_RADIALS = 360`; `step_m(radius_m) = min(250, max(30, radius_m / 200))`;
  - `compute_radial(args: tuple[list[float], float, tuple]) -> list[float]`, funzione di modulo (si deve poter serializzare):
    - riceve le quote del radiale dal sito al bordo, il passo e i parametri piatti;
    - restituisce l'RSSI previsto per ogni indice; l'indice 0 è `nan`;
    - per `i ≥ 1` usa `pfl = [i, step, *elev[:i+1]]`;
    - in caso di `ItmError` la perdita diventa lo spazio libero `32.45 + 20log10(d_km) + 20log10(f)`;
    - RSSI = `eirp − loss + rx_gain`;
  - `rasterize(lat, lon, radials: ndarray[N_RADIALS, n], step: float, radius_m: float, sens: float) -> Grid`:
    - griglia uniforme in Mercatore sul bbox del cerchio, con lato = `min(400, ceil(2·radius_m / step))`;
    - per ogni cella: distanza e azimut dal sito (vettoriale), interpolazione bilineare tra i due radiali vicini e i due passi vicini;
    - margine `clip(round(rssi − sens), −127, 127)`; `−128` fuori dal raggio o con `nan`;
  - `@dataclass Grid(bbox: list[float], width: int, height: int, values: ndarray[int8])`, righe da nord a sud;
  - `predict(params: SiteParams, dem: Dem, executor_factory: Callable[[], Executor], progress: Callable[[int, int], None], cancel: threading.Event) -> Grid`:
    - campiona i profili nel processo principale con `Dem.sample`;
    - invia i radiali all'esecutore in blocchi da 8;
    - aggiorna `progress(done, N_RADIALS)`;
    - con `cancel` impostato chiude l'esecutore con `cancel_futures=True` e solleva `PredictionError(409, "Calcolo annullato")`;
  - `default_executor() -> ProcessPoolExecutor(max_workers=max(1, min(4, (os.cpu_count() or 2) - 1)))`.

- [ ] **Step 1: test che falliscono** (`test_prediction.py`, con un `Dem` finto: classe con `sample(lats, lons)` programmabile; esecutore `ThreadPoolExecutor(2)`):
  - `test_sensitivity`: `LONG_FAST` → −131.5; `SHORT_TURBO` → −117.0; `LONG_SLOW` → −137.0;
  - `test_params_validation`: `radius_km = 80` → `PredictionError` con status 400 e «radius_km» nel testo; `eirp_dbm` = 22 + 2 − 0 = 24;
  - `test_rasterize_uniform`: tutti i radiali a −100 dBm, sensibilità −131.5 → ogni cella nel raggio vale 32 (−100 + 131,5 = 31,5, arrotondato alla pari con `numpy.round`); gli angoli del bbox valgono −128; lato ≤ 400;
  - `test_flat_terrain_decreasing`: terreno piatto a 100 m, raggio 5 km → il margine medio dell'anello a 1–2 km è maggiore di quello a 4–5 km, e la differenza tra nord ed est sullo stesso anello è ≤ 1 dB;
  - `test_ridge_shadow`: una cresta di 600 m a 3 km verso est (fascia di longitudini) → il margine medio a 4–5 km verso est è almeno 10 dB sotto quello verso ovest;
  - `test_sea_clamp` (Review Focus 5): un `Dem` vero da `Dem.sample` con quote negative → nessun `nan` dentro il raggio;
  - `test_cancel`: `cancel` impostato dal callback di `progress` dopo il primo blocco → `PredictionError` 409;
  - `test_launcher_freeze_support` (Review Focus 1): l'AST di `packaging/launcher.py` mostra che la prima istruzione nel blocco `if __name__ == "__main__":` è la chiamata `multiprocessing.freeze_support()`.
- [ ] **Step 2:** `pytest -q server/tests/test_prediction.py` → FAIL.
- [ ] **Step 3:** implementare `prediction.py` e le due modifiche di `freeze_support`.
- [ ] **Step 4:** stesso comando → PASS. Poi una prova manuale con `default_executor()` su un `Dem` piatto, raggio 15 km → termina in meno di 90 s e non lascia processi `python` figli (`Get-Process python`).
- [ ] **Step 5: Commit** `feat(server): motore di copertura prevista con ITM su radiali in processi separati`.

### Task 4: Servizio della previsione, API e confronto con le prove misurate  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/prediction_service.py`, `server/meshlens/api_prediction.py`, `server/tests/test_prediction_service.py`, `server/tests/test_api_prediction.py`
- Modify:
  - `server/meshlens/api.py` (campo `prediction: object | None = None` in `AppContext`; in fondo a `create_app`, prima del montaggio dei file statici: `api_prediction.register(app, ctx, require_auth, require_json)`);
  - `server/meshlens/app.py` (in `create`: `rt.prediction = PredictionManager(data_dir, bus, ElevationCache(Path(data_dir) / "elevation"))`, passato ad `AppContext`; in `start`: `cleanup_tmp()`; in `stop`: `await rt.prediction.shutdown()`);
  - `THIRD_PARTY_NOTICES.md` (attribuzione dei dati di altitudine).

**Interfaces:**
- Consumes: Task 1–3; `coverage.missing_points`, `store.points`, `store.track`, `store.get_session` (esistenti).
- Produces:
  - `prediction_service.py`:
    - `class PredictionManager(data_dir: Path, bus, cache: ElevationCache, executor_factory=default_executor, clock=time.time)` con i metodi `estimate(params: dict) -> dict`, `async start(params: dict, name: str | None, download: bool) -> dict`, `async cancel(job_id: str) -> dict`, `list() -> list[dict]`, `get(pid: str) -> dict`, `delete(pid: str) -> None`, `compare(pid: str, points: list[dict], missing: list[dict]) -> dict`, `async shutdown() -> None`, `cleanup_tmp() -> None`.
    - **Un solo lavoro alla volta**, con il posto prenotato prima di ogni `await`, come `MapsManager._starting`.
    - Fasi del lavoro, eseguite con `asyncio.to_thread` e pubblicate sul bus con `{"type":"prediction_job","job":…}` al massimo ogni 0,5 s:
      1. «Download dei dati di altitudine», con `done`/`total` in riquadri;
      2. «Calcolo», con `done`/`total` in radiali;
      3. «Salvataggio».
    - **Risultati** in `data_dir/predictions/<id>.json` (meta più `values` in base64), scritti su `.tmp` con `os.replace`; `id = f"p{int(clock())}-{uuid4().hex[:6]}"`. **Nessuna tabella nel database.** `covered_km2` = celle con margine ≥ 0 × area della cella al centro.
    - **Annullamento:** `cancel` imposta l'evento; `shutdown` annulla e attende la chiusura dell'esecutore.
  - `compare_grid(meta: dict, values: ndarray, points: list[dict], missing: list[dict]) -> dict`, funzione pura nello stesso file:
    - per ogni punto cerca la cella Mercatore più vicina; se il punto è fuori dal bbox o su `−128` conta in `outside`;
    - `predicted_rssi = margine + sensitivity_dbm`;
    - bias = media di (previsto − misurato) e RMSE sui punti ricevuti che hanno un `rssi`, con una cifra decimale; `null` se non ce ne sono;
    - restituisce i campi esatti del contratto JSON.
  - `api_prediction.py`: `register(app, ctx, require_auth, require_json) -> None` con le rotte del contratto. `PredictionError` e `ElevationError` diventano JSON `{"detail", "code"}` con lo stato dell'errore, come `MqttSendError` in `/api/mqtt/send`. Per `compare`, i punti si leggono con `ctx.store.points(sid)`; i mancanti con `missing_points(points, s["interval_s"], ctx.store.track(sid))`, solo se `mode == "rangetest"`.

- [ ] **Step 1: test che falliscono** (con un `ElevationCache` finto, con insieme dei riquadri presenti e download che "aggiunge"; esecutore in linea; un `Dem` piatto):
  - `test_estimate_counts`: con 4 riquadri su N in cache → `tiles_missing == N − 4` e `download_bytes == (N − 4) * 90000`;
  - `test_start_requires_download`: con riquadri mancanti e `download` falso → `PredictionError` 409 con `code == "elevation_missing"` e il numero nel testo;
  - `test_job_lifecycle`: `start(..., download=True)` → sul bus, in ordine, i passi «Download dei dati di altitudine», «Calcolo» e «Salvataggio», poi `status == "done"` con `result_id`; il file JSON esiste; `list()[0]["id"] == result_id`; `get()` ha `values` di lunghezza `width*height` dopo la decodifica base64;
  - `test_single_job`: un secondo `start` mentre il primo gira → 409 «C'è già un calcolo in corso»;
  - `test_download_failure_keeps_cache` (Review Focus 2): il download finto solleva `ElevationError` → job `failed` con quel testo; nessun file in `predictions/`;
  - `test_compare_grid`: griglia 10 × 10 con margine +5 nella metà ovest e −5 nella metà est; due ricevuti a ovest (rssi −120, previsto −126,5) e uno a est; un mancante a est → `received_covered == 2`, `received_uncovered == 1`, `missing_uncovered == 1`, `agreement_pct == 75.0`, `rssi_bias_db == −6.5` sui punti a ovest;
  - `test_api_prediction.py`: le rotte con autenticazione (401 senza), 400 per un parametro fuori dall'intervallo, 404 per un id sconosciuto, `DELETE` → 204, `compare` con una sessione creata con lo `store` dei test → 200 con i campi del contratto.
- [ ] **Step 2:** `pytest -q server/tests/test_prediction_service.py server/tests/test_api_prediction.py` → FAIL.
- [ ] **Step 3:** implementare `prediction_service.py`, `api_prediction.py` e il collegamento in `api.py` e `app.py`. In `THIRD_PARTY_NOTICES.md` vanno:
  - la sezione «Dati di altitudine (AWS Terrain Tiles, formato Terrarium)» con le diciture di `tilezen/joerd/docs/attribution.md`, tra cui: «Europe terrain data produced using Copernicus data and information funded by the European Union - EU-DEM layers», «SRTM, GMTED2010 data courtesy of the U.S. Geological Survey», «ETOPO1: U.S. National Oceanic and Atmospheric Administration»;
  - la voce NTIA ITM del Task 2 (se manca).
- [ ] **Step 4:** stesso comando più `pytest -q server/tests/test_app.py` → PASS.
- [ ] **Step 5: Commit** `feat(server): servizio e API della copertura prevista con confronto sulle prove`.

### Task 5: Interfaccia della copertura prevista  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/prediction.ts`, `web/src/lib/prediction.test.ts`, `web/src/lib/prediction.svelte.ts`, `web/src/lib/map/PredictionLayer.ts`, `web/src/components/Prediction.svelte`
- Modify:
  - `web/src/lib/ws.ts`: `WSHandlers.prediction_job?(job: PredictionJob): void` più una riga in `dispatch`;
  - `web/src/App.svelte`: passa `prediction_job: applyPredictionJob` a `connectWS`;
  - `web/src/components/MapView.svelte`: in `setup()`, `addPredictionLayer(m)` dopo `addCoverageLayers`; un `$effect` che legge `prediction.shown` e chiama `setPredictionImage`;
  - `web/src/components/Coverage.svelte`: `<Prediction />` in fondo all'elenco delle sessioni;
  - `web/src/lib/ui/icons.ts`: solo righe aggiunte, se servono icone nuove.

**Interfaces:**
- Consumes: i contratti JSON della previsione (Task 4); `getJSON`, `send`, `ApiError` di `api.ts`; `readTokens` di `lib/map/tokens.ts`.
- Produces:
  - `prediction.ts`:
    - i tipi `PredictionParams`, `PredictionMeta`, `PredictionGrid` (meta più `values: string`, `nodata: number`), `PredictionJob`, `PredictionCompare`, tutti come nel contratto;
    - `PRESET_OPTIONS`, la stessa lista di `PRESETS` lato server;
    - `defaultParams(pos?: {lat: number; lon: number}): PredictionParams`, con i valori d'esempio del contratto;
    - `validateParams(p): string | null`, che restituisce il primo errore in italiano, per esempio «Raggio: tra 1 e 50 km»;
    - `eirpDbm(p)` e `overLegalLimit(p): boolean` (soglia > 29,15);
    - `marginBand(v: number): 'good' | 'mid' | 'weak' | null`: ≥ 10 → `good`, 0..9 → `mid`, −10..−1 → `weak`, altrimenti (compreso −128) `null`;
    - `hexToRgb(hex): [number, number, number]`;
    - `gridToRgba(values: Int8Array, t: MapTokens): Uint8ClampedArray`: `good` → `snrGood` con alpha 140; `mid` → `snrMid` con alpha 115; `weak` → `snrBad` con alpha 80; `null` → trasparente;
    - `decodeValues(b64): Int8Array`;
    - `imageCoordinates(bbox): [[w,n],[e,n],[e,s],[w,s]]`;
    - API: `estimatePrediction`, `startPrediction`, `cancelPrediction`, `listPredictions`, `getPrediction`, `deletePrediction`, `comparePrediction(id, sessionId)`;
  - `prediction.svelte.ts`: `export const prediction = $state({ list: [] as PredictionMeta[], job: null as PredictionJob | null, shown: null as { id: string; url: string; coords: number[][] } | null })` e `applyPredictionJob(job)`, che a `done` ricarica `list`;
  - `PredictionLayer.ts`: `addPredictionLayer(map)`, con sorgente `pred-image` e layer `raster` `pred-raster` inserito prima di `cov-track`, e `setPredictionImage(map, shown | null)`. Con `null` il layer diventa invisibile. Dopo `setStyle`, `setup()` lo ricrea e l'`$effect` riapplica l'immagine.
- **`Prediction.svelte`** (Card «Copertura prevista»):
  - **Sito:** Select «Sito» con i miei nodi e le radio con posizione, più «Coordinate manuali» (campi lat/lon); i campi dei parametri con unità; preset; Banner `warn` se `overLegalLimit`.
  - **Avvio:** «Calcola» chiama `estimate`.
    - Se `tiles_missing > 0` compare un Modal: «Servono N riquadri di altitudine (circa X MB) da AWS Terrain Tiles. Verranno conservati per l'uso offline.» con «Scarica e calcola» e «Annulla».
    - Altrimenti parte subito con `download:false`.
  - **Avanzamento:** `Progress` con passo e `done/total`, più il pulsante «Annulla».
  - **Previsioni salvate:** l'elenco con «Mostra» / «Nascondi» / «Elimina» (con conferma). Il colore viene da `gridToRgba` disegnato su un `<canvas>` → `toDataURL()`.
  - **Legenda:** tre Chip con i colori dei token: «Buono (≥ 10 dB di margine)», «Al limite (0–10 dB)», «Debole (fino a −10 dB)».
  - **Confronto:** Select di una sessione → «Confronta» → riquadro con accordo %, ricevuti dentro/fuori, persi dentro/fuori, scarto medio RSSI e RMSE in dB (formato `signed` di `format.ts`, una cifra decimale).
  - **Attribuzione** in `--ink-muted`: «Altitudine: AWS Terrain Tiles (SRTM, EU-DEM © Copernicus, GMTED2010, ETOPO1). Modello ITM © NTIA.»

- [ ] **Step 1: test che falliscono** (`prediction.test.ts`):
  - `marginBand`: 10 → `good`, 9 → `mid`, 0 → `mid`, −1 → `weak`, −10 → `weak`, −11 → `null`, −128 → `null`;
  - `gridToRgba(Int8Array.from([20, 5, -5, -128]), FALLBACK_TOKENS)` → i quattro pixel con l'RGB di `snrGood`, `snrMid`, `snrBad` e gli alpha 140, 115, 80, 0;
  - `validateParams`: con `radius_km: 0` → testo con «Raggio»; parametri predefiniti → `null`;
  - `overLegalLimit`: potenza 27 + guadagno 3 → `true`; 22 + 2 → `false`;
  - `imageCoordinates([1,2,3,4])` → `[[1,4],[3,4],[3,2],[1,2]]`;
  - `decodeValues` di `btoa(String.fromCharCode(255, 1))` → `[-1, 1]`;
  - in `ws.test.ts`: il messaggio `prediction_job` chiama il gestore; se il gestore manca non solleva.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/prediction.test.ts src/lib/ws.test.ts` → FAIL.
- [ ] **Step 3:** implementare `prediction.ts`, `prediction.svelte.ts`, `PredictionLayer.ts` e il gestore in `ws.ts`.
- [ ] **Step 4:** implementare `Prediction.svelte` e i collegamenti in `MapView`, `Coverage` e `App`.
- [ ] **Step 5:** stesso vitest più `cd web && npm run check` → PASS, 0 errori.
- [ ] **Step 6: Commit** `feat(web): copertura prevista sulla mappa con confronto sulle prove`.

### Task 6: Store & Forward sul server, router, richiesta e rigioco  _(modello: opus)_

**Files:**
- Create: `server/meshlens/storeforward.py`, `server/tests/test_storeforward.py`
- Modify (solo questi punti):
  - `server/meshlens/events.py`: `replayed: bool = False` come ultimo campo di `MeshEvent`, con un commento «S&F: messaggio rigiocato da un router (ora originale)»;
  - `server/meshlens/rf_convert.py`: in `packet_to_event`, prima di `else: return None`, il ramo `elif port == "STORE_FORWARD_APP": kind, payload = "storeforward", parse_sf(packet)` (import da `.storeforward`);
  - `server/meshlens/radio.py`: il metodo nuovo `send_storeforward`, sul modello di `send_traceroute`;
  - `server/meshlens/ingest.py`: in `handle`, i blocchi "heard_by", "last_snr" e `_update_hops` e la chiamata `_record_links` si saltano se `ev.replayed`;
  - `server/meshlens/db.py`: in `SCHEMA`, la tabella `sf_routers(num INTEGER PRIMARY KEY, radio_id TEXT, last_seen REAL, heartbeat_period INTEGER, secondary INTEGER, stats TEXT, last_request REAL)`;
  - `server/meshlens/app.py`: costruzione del servizio; in `on_event`, `if ev.kind == "storeforward": sf.handle(ev); return`, poi `sf.observe_text(ev)` per gli eventi `text`, prima di `ingestor.handle`; `asyncio.create_task(self._every(5, sf.check))` in `start`;
  - `server/tests/test_ingest_rf.py`: un test aggiunto.

**Interfaces:**
- Produces:
  - `storeforward.py`:
    - `@dataclass SfPacket(rr: str, stats: dict | None, history: dict | None, heartbeat: dict | None, text: bytes | None, rx_time: float | None)`;
    - `parse_sf(packet: dict) -> SfPacket | None`:
      - legge `StoreAndForward.FromString(bytes(decoded["payload"]))`; se non riesce ricade su `decoded["storeforward"]` (dict di `MessageToDict`, con `text` in base64);
      - `rr` è il nome dell'enum (`"ROUTER_HEARTBEAT"`, …); `stats`/`history`/`heartbeat` sono dict con chiavi snake_case;
      - `rx_time` viene da `packet.get("rxTime")` (0 → `None`);
      - con dati illeggibili restituisce `None`;
    - testi esatti dei rifiuti: `REFUSED_PUBLIC = "S&F not permitted on the public channel."` e `REFUSED_BUSY = "S&F - Busy. Try again shortly."`;
    - `REQUEST_MIN_INTERVAL_S = 300`; `HISTORY_TIMEOUT_S = 60`; `IDLE_TIMEOUT_S = 30`;
    - `class SfError(Exception)` con `status: int` e `retry_after: int | None`;
    - `class StoreForwardService(store, live, handle_event: Callable[[MeshEvent], None], bus, connector: Callable[[str], Any], clock=time.time)`, con i metodi:
      - `handle(ev: MeshEvent) -> None`:
        - `ROUTER_HEARTBEAT`, `ROUTER_STATS` e `ROUTER_PONG` aggiornano o creano il router `ev.from_node` (`radio_id`, `last_seen`, `heartbeat_period`, `secondary`, `stats` in JSON) e pubblicano `sf_routers`;
        - `ROUTER_HISTORY` porta il lavoro della radio a `receiving` con `expected = history_messages`;
        - `ROUTER_TEXT_BROADCAST` e `ROUTER_TEXT_DIRECT` passano a `_replay`;
        - `ROUTER_BUSY` e `ROUTER_ERROR` portano il lavoro a `failed`;
      - `_replay(ev, sfp)`:
        - chiave `f"{ev.from_node}:{ev.packet_id}"`; se c'è già in `messages` (`SELECT 1 FROM messages WHERE key=?` su `store.conn`) o in `live.messages` → `duplicates += 1`;
        - altrimenti chiama `handle_event` con un `MeshEvent` così fatto:
          - `kind="text"`, `payload=TextData(text.decode("utf-8", "replace"))`;
          - `to_node`: `0xFFFFFFFF` per i broadcast, altrimenti `ev.to_node`;
          - stessi `packet_id`, `channel` e `radio_id`;
          - `rx_time = sfp.rx_time or clock()`;
          - `snr`, `rssi` e `hops` a `None`; `replayed=True`;
        - poi `received += 1`;
        - il pacchetto conta per il lavoro anche se nessun lavoro è attivo, perché un rigioco può arrivare anche da una richiesta di un'altra app;
      - `observe_text(ev) -> None`: se c'è un lavoro `waiting` o `receiving` verso `ev.from_node` e il testo è uno dei due rifiuti, il lavoro va a `failed` con «Il router rifiuta le richieste sul canale pubblico: scegli un canale privato condiviso con il router» oppure «Router occupato: riprova tra poco». L'evento prosegue comunque verso l'ingest;
      - `async request(radio_id, router_num, window_min, channel_index) -> dict`:
        - errori: «Radio non connessa» (409), «C'è già un recupero in corso su questa radio» (409), limite di frequenza (429 con `retry_after`);
        - chiama `connector(radio_id).send_storeforward(router_num, "CLIENT_HISTORY", window_min, channel_index)`, salva `last_request` e pubblica `sf_job`;
      - `async probe(radio_id, router_num, channel_index) -> None`, con `"CLIENT_STATS"`;
      - `check() -> None`:
        - `waiting` da oltre 60 s → `failed` «Nessuna risposta dal router»;
        - `receiving` senza pacchetti da 30 s, oppure con `received + duplicates ≥ expected` → `done`;
        - radio non più `connected` → `failed` «Radio scollegata durante il recupero»;
      - `routers() -> list[dict]` (nome da `live.nodes`) e `jobs() -> list[dict]`;
  - `radio.py`: `async send_storeforward(self, dest_num: int, rr: str, window_min: int | None, channel_index: int) -> int`:
    - costruisce `StoreAndForward(rr=StoreAndForward.RequestResponse.Value(rr))`, più `history.window = window_min` se il valore è dato;
    - chiama `iface.sendData(..., destinationId=dest_num, portNum=portnums_pb2.STORE_FORWARD_APP, wantResponse=False, channelIndex=channel_index)` sotto `_send_lock`, con lo stesso timeout e gli stessi errori di `send_traceroute`.

- [ ] **Step 1: test che falliscono** (`test_storeforward.py`, con lo `store` e il `live` dei test, un connettore finto che registra le chiamate e lo stato `connected`, un orologio finto e un `handle_event` che raccoglie gli eventi). I pacchetti finti sono dict con `decoded.payload = StoreAndForward(...).SerializeToString()` e `portnum "STORE_FORWARD_APP"`:
  - `test_parse_sf`: heartbeat (`period=900`) → `rr == "ROUTER_HEARTBEAT"` e `heartbeat == {"period": 900, "secondary": False}`; payload rotto → `None`; ricaduta su `decoded["storeforward"]` con `text` in base64;
  - `test_rf_convert_branch`: `packet_to_event` su un pacchetto S&F → `kind == "storeforward"`;
  - `test_heartbeat_registers_router`: dopo `handle` la riga esiste in `sf_routers` e il bus ha `sf_routers` con `id "!…"` e `heartbeat_period 900`; un secondo heartbeat aggiorna `last_seen`;
  - `test_request_flow`:
    - `request("r1", 0xA1, 240, 1)` → il connettore riceve `("send_storeforward", 0xA1, "CLIENT_HISTORY", 240, 1)` e il job è `waiting`;
    - `ROUTER_HISTORY(history_messages=3)` → `receiving` con `expected 3`;
    - tre `ROUTER_TEXT_BROADCAST` con `rxTime` = ora − 3600 → `handle_event` riceve 3 eventi con `replayed=True`, `to_node == 0xFFFFFFFF`, `rx_time` originale e testo giusto;
    - `check()` → `done` con `received 3`;
  - `test_replay_dedup` (Review Focus 3): un messaggio con la stessa chiave già nel database e uno già in `live.messages` → `handle_event` non viene chiamato e `duplicates == 2`;
  - `test_refused_public` (Review Focus 4): un evento `text` dal router con `REFUSED_PUBLIC` → `failed` con il testo italiano;
  - `test_timeouts`: `waiting` + 61 s → `failed` «Nessuna risposta dal router»; connettore scollegato → `failed` «Radio scollegata durante il recupero»;
  - `test_rate_limit`: una seconda richiesta allo stesso router dopo 10 s → `SfError` 429 con `retry_after == 290`;
  - `test_radio_send_storeforward`: `RadioConnector` con un'interfaccia finta → `sendData` riceve `portNum == 65` e un payload che, decodificato, ha `rr == CLIENT_HISTORY` e `history.window == 240`;
  - in `test_ingest_rf.py`, `test_replayed_text_does_not_touch_rf_stats`: un evento `text` con `replayed=True` e `radio_id` → il messaggio viene salvato e pubblicato; `heard_by`, `last_snr` e `hops` del nodo restano invariati; nessun collegamento registrato.
- [ ] **Step 2:** `pytest -q server/tests/test_storeforward.py server/tests/test_ingest_rf.py` → FAIL.
- [ ] **Step 3:** implementare `storeforward.py` e le modifiche puntuali elencate.
- [ ] **Step 4:** stesso comando più `pytest -q server/tests/test_rf_convert.py server/tests/test_radio.py server/tests/test_ingest.py server/tests/test_db.py` → PASS.
- [ ] **Step 5: Commit** `feat(server): Store & Forward, router, richiesta dello storico e rigioco senza doppioni`.

### Task 7: API e interfaccia «Recupera messaggi persi»  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/api_storeforward.py`, `server/tests/test_api_storeforward.py`, `web/src/lib/storeforward.ts`, `web/src/lib/storeforward.test.ts`, `web/src/lib/storeforward.svelte.ts`, `web/src/components/StoreForward.svelte`
- Modify:
  - `server/meshlens/api.py`: campo `storeforward: object | None = None` e `api_storeforward.register(...)` accanto a quello del Task 4;
  - `server/meshlens/app.py`: passa il servizio ad `AppContext`;
  - `web/src/lib/ws.ts`: gestori facoltativi `sf_job?(job)` e `sf_routers?(routers)`;
  - `web/src/App.svelte`: passa i due gestori;
  - `web/src/components/Radios.svelte`: pulsante «Recupera messaggi persi» sulla scheda di ogni radio `connected`, che apre `<StoreForward radio={r} />`.

**Interfaces:**
- Consumes: `StoreForwardService` e `SfError` (Task 6); `Radio.channels` (`{index, name, role}`) già nel JSON delle radio.
- Produces:
  - `api_storeforward.py`: `register(app, ctx, require_auth, require_json)` con le rotte del contratto. `SfError` diventa `{"detail"}` con il suo stato e, per il 429, l'intestazione `Retry-After`. Gli id si validano con `_num_from_id` di `api.py`, cioè 400 «Identificativo del nodo non valido».
  - `storeforward.ts`:
    - tipi `SfRouter` e `SfJob`;
    - `WINDOW_OPTIONS = [{min: 60, label: '1 ora'}, {min: 240, label: '4 ore'}, {min: 720, label: '12 ore'}, {min: 1440, label: '24 ore'}]`, con 240 predefinito;
    - `defaultChannel(channels): number`: il primo con `role === 'SECONDARY'`, altrimenti 0;
    - `isLikelyPublic(ch): boolean`: `PRIMARY` con nome uguale a un preset (`LongFast`, `MediumFast`, …) o vuoto;
    - `jobText(job): string`, con i testi esatti:
      - `waiting` → «In attesa del router…»;
      - `receiving` → «Ricevuti {r} di {e}» più «, {d} già presenti» se `d > 0`; senza `expected` → «Ricevuti {r}»;
      - `done` → «Completato: {r} messaggi recuperati» più «, {d} già presenti»; con `r == 0 && d == 0` → «Nessun messaggio da recuperare»;
      - `failed` → `job.error`;
    - API: `sfRouters()`, `sfRequest(body)`, `sfProbe(body)`, `sfJobs()`;
  - `storeforward.svelte.ts`: `export const sf = $state({ routers: [] as SfRouter[], jobs: {} as Record<string, SfJob> })`, `applySfJob(job)` e `setSfRouters(list)`.
- **`StoreForward.svelte`** (Modal):
  - **Router:** Select con i router noti (nome, «visto {ago}», capienza da `stats`) più «Altro nodo…», con un campo id `!xxxxxxxx` e il pulsante «Verifica router» (probe);
  - **Finestra:** Segmented con `WINDOW_OPTIONS`;
  - **Canale:** Select con i canali della radio, che parte da `defaultChannel`; se `isLikelyPublic` compare un Banner `warn`: «I router rifiutano le richieste sul canale pubblico: scegli un canale privato condiviso con il router.»;
  - **Nota** in `--ink-muted`: «Il router manda solo i messaggi che non ti ha già inviato, fino al suo massimo.»;
  - **Avvio:** il pulsante «Recupera» → `jobText`, con `Progress` indeterminato in `waiting` e determinato quando c'è `expected`;
  - **Errori:** un 429 mostra il testo del server;
  - **Toast** a `done`.

- [ ] **Step 1: test che falliscono:**
  - `test_api_storeforward.py`, con un servizio finto:
    - 401 senza autenticazione;
    - `window_min: 2` → 422/400;
    - `router_id: "xyz"` → 400;
    - richiesta valida → 202 con `SfJob`;
    - `SfError(429, retry_after=12)` → 429 con `Retry-After: 12`;
    - `GET /api/storeforward/routers` → elenco;
  - `storeforward.test.ts`:
    - `defaultChannel([{index:0,role:'PRIMARY'},{index:2,role:'SECONDARY'}]) === 2`;
    - `isLikelyPublic({index:0,name:'LongFast',role:'PRIMARY'})` → `true`; `isLikelyPublic({index:1,name:'Club',role:'SECONDARY'})` → `false`;
    - i testi esatti di `jobText` per `receiving` (con e senza `expected`, con e senza duplicati), `done` con zero messaggi e `failed`;
  - `ws.test.ts`: `sf_job` e `sf_routers` chiamano i gestori.
- [ ] **Step 2:** `pytest -q server/tests/test_api_storeforward.py` e `cd web && npx vitest run src/lib/storeforward.test.ts src/lib/ws.test.ts` → FAIL.
- [ ] **Step 3:** implementare l'API e i moduli `lib/`.
- [ ] **Step 4:** implementare `StoreForward.svelte` e il pulsante in `Radios.svelte`.
- [ ] **Step 5:** gli stessi test più `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat: recupero dei messaggi persi da un router Store & Forward`.

### Task 8: Verifica finale — Parte A  _(modello: sonnet)_

**Files:**
- Nessun file nuovo. Correzioni piccole dove la verifica trova problemi, ognuna con il suo commit `fix: …`.

- [ ] **Step 1: suite complete:**
  - `PYTHONPATH=server .venv/Scripts/python -m pytest -q` → tutti verdi;
  - `cd web && npx vitest run` → tutti verdi;
  - `cd web && npm run check` → 0 errori;
  - `cd web && npm run build` → build riuscita.
- [ ] **Step 2: controllo nel browser** (server demo; `.claude/launch.json` se esiste) a **1280×800** e **390×844**, in tema scuro e chiaro:
  - **C1:**
    - previsione da un nodo mio con raggio 10 km → la stima mostra riquadri e MB; «Scarica e calcola» → avanzamento nei tre passi → overlay sulla mappa, legenda, attribuzione;
    - il cambio di tema ricolora l'overlay senza ricalcolo;
    - una seconda previsione nella stessa area parte senza download;
    - con la rete scollegata (Wi-Fi spento) la seconda previsione funziona ancora;
    - confronto con una sessione di prova demo → numeri plausibili;
    - EIRP 30 dBm → Banner del limite di legge.
  - **C2** (con una radio vera e un router S&F, se disponibili; altrimenti con i test e con un pacchetto simulato dal server demo):
    - il router compare dopo un heartbeat o «Verifica router»;
    - «Recupera» su un canale privato → messaggi rigiocati nella conversazione giusta, all'ora originale;
    - una seconda richiesta → «Nessun messaggio da recuperare» oppure solo i «già presenti»;
    - canale pubblico → errore italiano.
- [ ] **Step 3: pacchetto installato** (Review Focus 1):
  - `pyinstaller packaging/meshlens.spec`, poi avvio di `dist/MeshLens/MeshLens.exe`;
  - una previsione da 15 km termina;
  - durante il calcolo `Get-Process MeshLens` mostra al massimo 1 + N processi, una sola icona nel vassoio e nessun secondo server;
  - dopo la fine resta un solo processo.
- [ ] **Step 4: controllo del layout** a 390×844 sui componenti nuovi:
  - testo ≥ 14 px, aree toccabili ≥ 44 px, nessuno scorrimento orizzontale;
  - `grep -nE "#[0-9a-fA-F]{3,8}\b|rgb\(" ` sui file web creati in questa fase → nessun risultato fuori dai test.
- [ ] **Step 5: confini con la fase 12:**
  - `git diff --stat main...HEAD` → i file condivisi toccati sono solo quelli delle Global Constraints;
  - nessun passo di migrazione nuovo (`SCHEMA_VERSION` invariato);
  - nessuna dipendenza nuova;
  - nessun cambio di versione.
- [ ] **Step 6: Commit** delle eventuali correzioni. La Parte A si chiude senza rilascio.

---

# Parte B — da eseguire dopo l'unione di fase 12 e 13

> Prima di iniziare: `git log main` deve contenere i merge delle fasi 12 e 13. I componenti che queste fasi aggiungono (elenco conversazioni, reazioni, waypoint, notifiche, …) rientrano nei blocchi del Task 10 o del Task 11 secondo la cartella; se un file non è elencato, va nel Task 11.

### Task 9: Infrastruttura i18n, lingua salvata, formati e messaggi del server  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/i18n/index.svelte.ts`, `web/src/lib/i18n/it.ts`, `web/src/lib/i18n/en.ts`, `web/src/lib/i18n/server-en.json`, `web/src/lib/i18n/server.ts`, `web/src/lib/i18n/i18n.test.ts`, `web/src/lib/i18n/scan.test.ts`, `server/tests/test_i18n_catalog.py`
- Modify:
  - `web/src/lib/format.ts` e `format.test.ts`: ogni `'it-IT'` diventa `locale()`;
  - `web/src/lib/api.ts`: il messaggio di `ApiError` passa per `translateServer`;
  - `web/src/main.ts`: `initLang()` prima del mount;
  - `web/src/components/Settings.svelte`: Segmented «Lingua / Language» con «Italiano» ed «English»; le etichette delle lingue non si traducono;
  - `App.svelte` e `lib/shell/*` (TopBar, BottomNav, ConnectionBar, AlertsList, Panel, MqttStatusDetail, BrokerPicker, MeshtasticBadge) più `lib/shell/nav.ts`: testi estratti, come primo blocco che fa da modello;
  - `lib/connection.svelte.ts`, `lib/alerts.ts`: testi estratti.

**Interfaces:**
- Produces:
  - `index.svelte.ts`:
    - `export type Lang = 'it' | 'en'` e `export const i18n = $state({ lang: 'it' as Lang })`;
    - `export type MsgKey = keyof typeof it`;
    - `t(key: MsgKey, params?: Record<string, string | number>): string`: legge `i18n.lang`, quindi è reattiva nei template e nei `$derived`; sostituisce `{nome}`; una chiave mancante in `en` ricade su `it`;
    - `tn(base: string, n: number, params?)`: usa `new Intl.PluralRules(locale()).select(n)` per scegliere `${base}.one` / `${base}.other` e passa `n` come parametro;
    - `locale(): 'it-IT' | 'en-GB'`;
    - `setLang(l: Lang)`: salva `meshlens.lang` in localStorage (con try/catch come `theme.ts`) e imposta `document.documentElement.lang`;
    - `initLang()`: legge il valore salvato; il predefinito è `'it'`, anche se il browser è in un'altra lingua;
  - `it.ts`: `export const it = { 'nav.map': 'Mappa', … } as const`, con chiavi piatte a punti per area (`nav.`, `shell.`, `map.`, `nodes.`, `chat.`, `coverage.`, `prediction.`, `sf.`, `radios.`, `config.`, `settings.`, `maps.`, `updates.`, `login.`, `common.`);
  - `en.ts`: `export const en: Record<MsgKey, string>`, così TypeScript segnala ogni chiave mancante;
  - `server-en.json`: `{"exact": {"<testo italiano>": "<English>"}, "patterns": [["^Attendi (\\d+) s", "Wait $1 s"], …]}`;
  - `server.ts`: `translateServer(msg: string): string`. Con `i18n.lang === 'it'` restituisce `msg`; altrimenti prova prima `exact`, poi il primo pattern che corrisponde; se nulla corrisponde restituisce `msg`. Va usata anche nei componenti che mostrano errori arrivati dal WS (`job.error` di mappe, configurazione, aggiornamenti, previsione e S&F), con una sola chiamata dove l'errore viene mostrato.
- **Test di copertura del catalogo del server** (`test_i18n_catalog.py`):
  - scorre con `ast` i file `server/meshlens/*.py` e raccoglie gli argomenti stringa delle chiamate a `HTTPException`, `MapsError`, `AdminError` (secondo argomento), `MqttSendError` (terzo), `PredictionError`, `ElevationError`, `SfError`, più le altre classi d'errore che arrivano all'utente: l'implementatore le trova con `grep -n "class .*Error" server/meshlens/*.py` e le elenca in una costante del test;
  - ogni `Constant` deve stare in `exact`;
  - ogni `JoinedStr`, formattato con `"X"` al posto dei campi, deve corrispondere a un pattern.

- [ ] **Step 1: test che falliscono:**
  - `i18n.test.ts`:
    - `t('nav.map')` → «Mappa»; dopo `setLang('en')` → «Map»; `localStorage['meshlens.lang'] === 'en'` e `document.documentElement.lang === 'en'`;
    - sostituzione di `{n}`;
    - `tn('common.messages', 1)` / `tn(…, 3)` in inglese → «1 message» / «3 messages»;
    - una chiave assente in `en`, forzata con un cast, ricade su `it`;
    - `initLang()` senza valore salvato → `'it'`;
  - `format.test.ts`: gli stessi valori in `en` → «3.59 V», «−3.5 dB» (meno tipografico mantenuto), un orario a 24 h;
  - `server.ts`: `translateServer('Attendi 7 s prima di una nuova richiesta a questo router')` in `en` → testo inglese con 7 (Review Focus B2); un testo sconosciuto resta invariato;
  - `scan.test.ts`:
    - per ogni `.svelte` sotto `src/` che non è in `PENDING`, cerca nel markup (fuori da `<script>` e `<style>`) testo letterale con parole di almeno 3 lettere e negli attributi `aria-label`, `title`, `placeholder`, `label=` letterali;
    - eccezioni ammesse: un `ALLOW` con `MeshLens`, `Meshtastic®`, `MQTT`, `SNR`, `RSSI`, `LoRa`, `PMTiles`, `ITM`, `NTIA`, `USB`, `BLE`, `Italiano`, `English`, unità e sigle;
    - all'inizio `PENDING` = tutti i componenti tranne quelli migrati in questo task;
  - `test_i18n_catalog.py` → FAIL finché `server-en.json` non è completo.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/i18n src/lib/format.test.ts` e `pytest -q server/tests/test_i18n_catalog.py` → FAIL.
- [ ] **Step 3:** implementare `lib/i18n/*` e `format.ts`, compilare `server-en.json` con tutti i messaggi trovati dal test Python, poi applicare `translateServer` in `api.ts`.
- [ ] **Step 4:** estrarre i testi di `App.svelte`, `lib/shell/*`, `nav.ts`, `connection.svelte.ts` e `alerts.ts`; aggiungere il selettore della lingua in Impostazioni e togliere questi file da `PENDING`. Il titolo della scheda del browser segue la lingua (Review Focus B1).
- [ ] **Step 5:** gli stessi test più `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): infrastruttura per la lingua inglese, formati e messaggi del server`.

### Task 10: Estrazione dei testi — mappa, nodi, rete, messaggi  _(modello: sonnet)_

**Files:**
- Modify:
  - `web/src/components/` MapView, NodeList, NodeSortBar, NodeDetail, Network, Filters, ActiveFilters, Traceroute, TelemetryChart, Chat, MessageFeed, più i componenti dei messaggi aggiunti dalla fase 12;
  - `web/src/lib/map/*.svelte` e i testi dei popup e della legenda in `lib/map/*.ts`;
  - i moduli `lib/` con testi visibili: `nodes.ts`, `network.ts`, `nodesort.ts`, `traceroute.ts`, `chat.ts`, `send.ts`, `filters.ts`, `distance.ts`, `chart.ts`, `mqttstatus.ts`, `links.ts`, più quelli della fase 12;
  - `it.ts`, `en.ts`, i test esistenti di questi moduli e `scan.test.ts` (togliere da `PENDING`).

**Interfaces:**
- Consumes: `t`, `tn`, `locale`, `translateServer` (Task 9).
- **Regole di estrazione:**
  - le funzioni pure che oggi restituiscono testo italiano lo producono con `t()`;
  - i loro test confrontano il risultato con `t('chiave')` oppure impostano la lingua all'inizio;
  - i testi dei layer MapLibre (etichette, popup HTML) si ricalcolano al cambio di lingua con un `$effect` che legge `i18n.lang`, senza `setStyle`.

- [ ] **Step 1:** in `i18n.test.ts`, `test_en_complete`: ogni chiave di `it` ha un valore non vuoto in `en` e diverso dall'italiano, salvo un elenco `SAME_OK` (per esempio «MQTT», «SNR»). In `scan.test.ts` togliere da `PENDING` i file di questo task → FAIL.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/i18n` → FAIL.
- [ ] **Step 3:** estrarre i testi dei file elencati in `it.ts` e tradurli in `en.ts`; aggiornare i test esistenti toccati.
- [ ] **Step 4:** `cd web && npx vitest run src/lib/i18n src/lib/map src/lib/nodes.test.ts src/lib/network.test.ts src/lib/chat.test.ts src/lib/send.test.ts src/lib/traceroute.test.ts src/lib/filters.test.ts` più `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): mappa, nodi, rete e messaggi in inglese`.

### Task 11: Estrazione dei testi — copertura, previsione, radio, S&F, configurazione, impostazioni, mappe, aggiornamenti, accesso  _(modello: sonnet)_

**Files:**
- Modify:
  - `web/src/components/`: Coverage, CoverageSetup, CoveragePlanFlow, CoverageRestoreBox, Prediction, Radios, StoreForward, ConfigPanel, ConfigField, ConfigDiff, ConfigAdvanced, Settings, `settings/*`, OfflineMaps, Updates, Login, più ogni altro componente ancora in `PENDING`;
  - `web/src/lib/ui/*.svelte`: testi predefiniti come «Chiudi» o «Annulla»;
  - `lib/`: `coverage.ts`, `prediction.ts`, `storeforward.ts`, `config.ts`, `radios.ts`, `serial.ts`, `maps.ts`, `update.ts`, `maintenance.ts`, `brokers.ts`, `settings.ts`, `clipboard.ts`, `geopos.svelte.ts`;
  - `it.ts`, `en.ts` e i test toccati.
  - **Attenzione:** le etichette dei campi di configurazione che arrivano da `config_model.py` tramite `/api/config/schema` vanno in `server-en.json` (sezione `exact`) e passano per `translateServer` nel punto in cui ConfigField le mostra.
- **Fine del lavoro:** `PENDING` di `scan.test.ts` deve essere vuoto, e `scan.test.ts` controlla che lo sia.

- [ ] **Step 1:** in `scan.test.ts`, `PENDING` diventa `[]` e il test `expect(PENDING).toEqual([])` va aggiunto → FAIL.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/i18n` → FAIL.
- [ ] **Step 3:** estrarre e tradurre i testi; aggiungere a `server-en.json` le etichette dello schema di configurazione. Il test Python va esteso: tutte le `label`/`help` di `config_model.py` devono stare in `exact`.
- [ ] **Step 4:** `cd web && npx vitest run src/lib/i18n src/lib/coverage.test.ts src/lib/prediction.test.ts src/lib/storeforward.test.ts src/lib/config.test.ts src/lib/radios.test.ts src/lib/maps.test.ts src/lib/update.test.ts src/lib/settings.test.ts`, `pytest -q server/tests/test_i18n_catalog.py` e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): copertura, radio, configurazione e impostazioni in inglese`.

### Task 12: Verifica finale — Parte B  _(modello: sonnet)_

**Files:**
- Nessun file nuovo; correzioni con commit `fix: …`. Aggiornare `README.en.md` solo se cita la mancanza dell'interfaccia inglese.

- [ ] **Step 1: suite complete:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q`, `cd web && npx vitest run`, `npm run check` e `npm run build` → tutto verde.
- [ ] **Step 2: controllo nel browser** a 1280×800 e 390×844, nei due temi e nelle due lingue:
  - ogni scheda, ogni Modal e ogni stato vuoto o d'errore è in inglese;
  - nessun testo italiano residuo (ricerca a vista più `get_page_text`, cercando «il », « di », «della»);
  - cambio di lingua con un Modal aperto e un lavoro di previsione in corso (Review Focus B1);
  - errore 429 di S&F e 409 `elevation_missing` in inglese (Review Focus B2);
  - date e numeri `en-GB` in grafici, Rete e popup (Review Focus B3);
  - ricaricando la pagina la lingua resta.
- [ ] **Step 3: layout in inglese** a 390×844: nessun testo tagliato o a capo che rompe pulsanti, BottomNav e TopBar (le parole inglesi sono più corte, ma «Coverage» e «Settings» vanno controllate); testo ≥ 14 px; aree toccabili ≥ 44 px.
- [ ] **Step 4:** nessuna dipendenza nuova, nessun cambio di versione, nessun passo di migrazione.
- [ ] **Step 5: Commit** delle correzioni. La fase si chiude senza rilascio.
