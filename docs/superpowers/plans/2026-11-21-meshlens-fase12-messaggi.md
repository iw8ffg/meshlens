# MeshLens Fase 12 — Messaggi: non letti, conversazioni, risposte e reazioni, PKI, waypoint, notifiche esterne: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** completare la parte «comunicare» di MeshLens con le proposte B1, B2, B3, B9, B11 e B12 di `docs/superpowers/research/2026-11-21-proposte-prossima-release.md`:
- **B1:** contatori dei non letti, conversazioni in grassetto, `(n)` nel titolo e notifiche del browser per i messaggi diretti;
- **B2:** elenco delle conversazioni al posto del menu a tendina, con ordine per attività, anteprima, ricerca, bozze e il passaggio lista → conversazione;
- **B3:** risposte e reazioni emoji, ricevute e inviate;
- **B9:** chiave pubblica dei nodi, lucchetto sui DM cifrati PKI, avviso di chiave cambiata ed errori di consegna in italiano;
- **B11:** waypoint ricevuti e mostrati sulla mappa; i propri si inviano solo via radio;
- **B12:** notifiche di Windows dall'icona nell'area di notifica e, se attivato, Telegram.

**Architettura:**
- **Server, dati:** la **migrazione 4** (di proprietà di questa fase) aggiunge:
  - le colonne `reply_id`, `emoji`, `pki` ed `error` a `messages`;
  - le colonne `public_key` e `key_changed` a `nodes`;
  - le tabelle `waypoints` e `conversation_reads`, create *dentro* `_migration_4` e non in `SCHEMA`, per non toccare il blocco che la fase 14 può estendere.
- **Server, decodifica:** i due decoder (MQTT `mqtt_decode.py`, RF `rf_convert.py`) leggono `Data.reply_id`, `Data.emoji`, `MeshPacket.pki_encrypted` e `WAYPOINT_APP`. `ingest.py` cambia solo in punti piccoli e nominati.
- **Server, moduli nuovi:** `conversations.py` (chiave di conversazione e riepiloghi, logica pura) e `notify.py` (notificatore con tre eventi e due canali: toast della tray e Telegram).
- **Interfaccia:** logica pura in moduli nuovi di `web/src/lib/`, ognuno con test vitest: `unread.svelte.ts`, `incoming.ts`, `notify.ts`, `conversations.ts`, `drafts.ts`, `reactions.ts`, `waypoints.ts`. `Chat.svelte` si divide in `components/chat/ConversationList.svelte`, `Thread.svelte` e `Composer.svelte`.
- **Testi:** tutti i testi nuovi visibili all'utente stanno in `web/src/lib/strings/*.ts` e, lato server, in costanti in cima al modulo. Così la fase 14 li estrae per l'inglese senza cercarli nei componenti.

**Tech Stack:** Python 3.12, FastAPI, sqlite3, protobuf `meshtastic` 2.7.11, `pystray` (`Icon.notify`), `urllib.request` per Telegram; Svelte 5 (runes), Vite, vitest, MapLibre GL (`map.addImage` per le icone dei waypoint), API del browser `Notification` e `document.visibilityState`.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md`. Proposte: `docs/superpowers/research/2026-11-21-proposte-prossima-release.md` (B1, B2, B3, B9, B11, B12). Restano valide le Global Constraints della fase 8 (`docs/superpowers/plans/2026-11-21-meshlens-fase8-design-invio.md`).

## Global Constraints

- **Valgono le Global Constraints della fase 8:**
  - italiano; `Intl` `it-IT`; il meno tipografico «−»;
  - **nessun colore fuori dai token** (`var(--…)`; per i layer MapLibre `readDocumentTokens()`);
  - testo ≥ 14 px e aree toccabili ≥ 44 px su telefono (`.vp-phone`); focus sempre visibile;
  - **nessuna risorsa esterna a runtime** (icone da `@lucide/svelte` in `lib/ui/icons.ts`; emoji disegnate dal font di sistema su canvas);
  - marker e waypoint come layer, nessun elemento HTML per punto.
- **Invio MQTT:** si pubblica **solo `TEXT_MESSAGE_APP` a nome del proprio nodo**, con limite di frequenza, conferma della prima volta e 200 byte, come nella fase 8. Risposte e reazioni via MQTT sono ammesse perché restano `TEXT_MESSAGE_APP`: cambiano solo i campi `reply_id` ed `emoji` di `Data`. **Waypoint, posizioni e nodeinfo non si pubblicano mai su MQTT.**
- **Svelte 5:**
  - nessun `$effect` legge e scrive lo stesso `$state`;
  - un effetto legge tutte le sue dipendenze `$state` **prima** di qualunque controllo su variabili semplici;
  - timer e listener vanno puliti;
  - l'effetto WebSocket e dati di `App.svelte` non segue stati nuovi (leggere con `untrack`).
- **Testi estraibili (per la fase 14):**
  - ogni testo nuovo dell'interfaccia è una proprietà di un oggetto esportato in `web/src/lib/strings/messaggi.ts`, `strings/waypoint.ts` o `strings/notifiche.ts`;
  - un testo con valori è una funzione che restituisce **la frase intera**, per esempio `unreadAria: (n: number) => n === 1 ? '1 messaggio non letto' : \`${n} messaggi non letti\``;
  - niente frasi composte concatenando pezzi nei componenti;
  - lato server, i testi delle notifiche e i nuovi `detail` d'errore sono costanti o dizionari in cima a `notify.py` e `api.py`.
- **Database:**
  - questa fase possiede **solo il passo 4** (`SCHEMA_VERSION = 4`); il 5 è della fase 13 e la fase 14 non aggiunge migrazioni;
  - il backup prima della migrazione avviene già tramite `before_migrate` e non va toccato.
- **Segreti:**
  - il token Telegram si aggiunge a `secretbox.SECRET_KEYS` (DPAPI) e si maschera con `mask_secrets`;
  - non compare mai in log, eccezioni o risposte: si usa `scrub_text`.
- **Fase 14 in parallelo** (copertura prevista, Store & Forward). Tocca `radio.py`, `rf_convert.py` e `ingest.py`. Qui quei file cambiano **solo** nei punti elencati nei task:
  - `radio.py`: `send_text` e il nuovo `send_waypoint`;
  - `rf_convert.py`: il ramo `TEXT_MESSAGE_APP`, il ramo nuovo `WAYPOINT_APP` e il parametro `pki` di `_event`;
  - `ingest.py`: `_build_message`, `_update_identity`, un ramo `waypoint`, `set_status`, `record_outgoing*` e il costruttore (parametro facoltativo `on_waypoint`).
  
  Nessuna rifattorizzazione di quei file.
- **Nessuna dipendenza nuova** in `pyproject.toml` né in `web/package.json`. **Nessun cambio di versione.**
- **Contratti JSON solo additivi.**
- **Test:**
  - server: `PYTHONPATH=server .venv/Scripts/python -m pytest -q`;
  - web: `cd web && npx vitest run`;
  - **ogni task esegue solo i propri test mirati** (e, se tocca file Svelte, `cd web && npm run check`); le suite complete si eseguono solo nel Task 12.
- Commit in italiano, stile `feat(server): …` / `feat(web): …` / `fix: …`.

## Contratti JSON (aggiunte)

- **Message:**
  - `reply_id?: number | null`: `packet_id` del messaggio a cui risponde o reagisce;
  - `emoji?: boolean`: vero se è una reazione; il testo è l'emoji;
  - `pki?: boolean`: DM ricevuto cifrato con la chiave pubblica;
  - `error?: string | null`: codice `Routing.Error`, come `"NO_ROUTE"` o `"TIMEOUT"`, per lo stato `failed`.
- **WS `message_status`:** guadagna `error?: string | null`.
- **Node:**
  - `public_key?: string | null`: base64;
  - `key_changed?: number | null`: secondi epoch dell'ultimo cambio di chiave.
- **Alert:** il nuovo `kind` `"key_changed"`:
  - chiave `pki:<id>`, `value` 0, `since` = `key_changed`;
  - resta 7 giorni e vale per i nodi miei **o** preferiti;
  - ordine: `battery_low`, `silent`, `key_changed`, `chutil_high`, `firmware_old`, `back_online`.
- **Waypoint:**

  ```json
  {"id": 123456, "from": "!a1b2c3d4", "from_name": "Base", "lat": 45.1, "lon": 9.2,
   "name": "Ritrovo", "description": "", "icon": "📍", "expire": null, "locked_to": "!a1b2c3d4",
   "time": 1763700000, "source": "rf", "radio_id": "r1a2b3c4", "channel": "0", "mine": true}
  ```

  - `icon` è il carattere del codepoint, oppure `""` se manca o non è valido;
  - `expire` vale `null` se non scade mai;
  - `mine` è vero se `from` è il nodo di una radio collegata.
- **Rotte dei waypoint:**
  - `GET /api/waypoints` → i waypoint attivi (non scaduti né eliminati), al massimo 500, i più recenti prima;
  - `POST /api/radios/{radio_id}/waypoint`
    - body `{name, description:"", icon:"📍", lat, lon, expire_h: int|null, channel_index:0}`;
    - risposta 202 con il Waypoint;
    - 400 nei casi: nome vuoto o oltre 30 byte, descrizione oltre 100 byte, icona che non è un solo codepoint ≥ U+0020, coordinate non valide, `expire_h` fuori da 1–720, radio non connessa;
  - `DELETE /api/waypoints/{id}` → 200 `{ok:true}`; 403 «Puoi eliminare solo i tuoi waypoint»; 404 se sconosciuto.
- **WS dei waypoint:** `{"type":"waypoint","waypoint":Waypoint}` e `{"type":"waypoint_deleted","id":int}`.
- **Conversazioni:**
  - `GET /api/conversations` → `[{key, last_time, last_text, last_from, last_emoji, unread, read_time}]`, solo conversazioni radio;
  - `POST /api/conversations/read` body `{key, time}` → `{key, read_time}`, più il WS `{"type":"conv_read","key":…,"time":…}`.
- **Invio:** `SendBody` e `MqttSendBody` guadagnano `reply_id: int|null` (1 … 2³²−1) ed `emoji: bool = false`.
  - `emoji` vero senza `reply_id` → 400;
  - con `emoji` il testo deve avere al massimo 16 byte e non contenere spazi.
- **Impostazioni (server):**
  - `notify_toast: true`, `notify_telegram: false`;
  - `telegram_token: ""` (segreto);
  - `telegram_chat_id: ""`, che deve essere vuoto oppure corrispondere a `^-?\d{1,20}$`;
  - `notify_mine_status: true`, `notify_new_node: false`;
  - `notify_keywords: []`: al massimo 20 parole, ciascuna di 2–32 caratteri senza spazi agli estremi.
- **Rotte delle notifiche:**
  - `GET /api/notify/status` → `{toast_available, telegram_last_ok, telegram_last_error}`;
  - `POST /api/notify/test` body `{channel:"toast"|"telegram"}` → `{ok:true}`; 400 se il canale non è configurato; 502 con il motivo (senza token) se Telegram fallisce;
  - `POST /api/notify/telegram/chat` → `{chat_id, title}`; 404 «Scrivi un messaggio al bot su Telegram e riprova».
- **localStorage (per dispositivo):**
  - `meshlens.drafts` (`{"v":1,"drafts":{"<conv>":"testo"}}`, al massimo 50 voci);
  - `meshlens.notify` (`{"v":1,"dm":false}`).

## Review Focus

1. **Reazione o risposta a un messaggio che non è caricato** (più vecchio della finestra di 200, oppure in un'altra conversazione). Niente eccezioni. La reazione compare come riga compatta «👍 a un messaggio precedente», la citazione come «Messaggio non disponibile». Le reazioni non contano tra i non letti e non generano notifiche. → Task 9 (`reactions.test.ts`) e Task 7 (`unread.test.ts`).
2. **Primo avvio dopo l'aggiornamento e messaggi propri.**
   - Lo storico esistente **non** diventa tutto «non letto»: la migrazione 4 salva `conv_read_baseline` = ora della migrazione.
   - I messaggi in uscita e quelli di una radio locale sentiti da un'altra radio locale non contano mai.
   - Aprire una conversazione sul telefono azzera il contatore sul PC (WS `conv_read`).
   
   → Task 1, Task 5 e Task 7.
3. **Collegamento di una radio con il suo database nodi.** Non deve partire una raffica di «nodo nuovo»:
   - per 300 s dall'avvio e dopo ogni cambio dell'insieme delle radio connesse, il notificatore sta in silenzio;
   - le parole chiave hanno un limite;
   - Telegram irraggiungibile non blocca il loop e l'errore compare nello stato senza il token.
   
   → Task 6.
4. **Chiave pubblica.** Non è un cambio, e non dà avviso:
   - la prima chiave vista;
   - una chiave vuota (firmware vecchio);
   - la stessa chiave ripetuta da MQTT e da RF.
   
   Una chiave diversa imposta `key_changed` una volta, e l'avviso resta 7 giorni. → Task 3.
5. **Waypoint scaduti o eliminati.** Un waypoint ricevuto con `expire` nel passato (anche `expire = 1`, cioè l'eliminazione delle app ufficiali) sparisce dalla mappa. Restano escluse anche:
   - le coordinate `(0, 0)` o fuori intervallo, ignorate;
   - un codepoint dell'icona non valido, che diventa `""` (la mappa usa il segnaposto);
   - un waypoint MQTT fuori dalle nazioni salvate, che compare in diretta ma non si salva.
   
   → Task 2, Task 3 e Task 10.

---

### Task 1: Schema 4 e Store  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/db.py` (`SCHEMA_VERSION = 4`, `_migration_4`, `_STEPS`), `server/meshlens/store.py`
- Test: `server/tests/test_db.py`, `server/tests/test_store.py`

**Interfaces:**
- Produces:
  - `_migration_4(conn)`:
    - colonne `messages.reply_id INTEGER`, `messages.emoji INTEGER DEFAULT 0`, `messages.pki INTEGER DEFAULT 0`, `messages.error TEXT`, `nodes.public_key TEXT`, `nodes.key_changed REAL`, tutte con `_add_missing_columns`;
    - tabella `waypoints(id INTEGER PRIMARY KEY, from_num INTEGER, lat REAL, lon REAL, name TEXT, description TEXT, icon INTEGER, expire INTEGER, locked_to INTEGER, time REAL, source TEXT, radio_id TEXT, channel TEXT, country TEXT, deleted INTEGER DEFAULT 0)`;
    - indice `idx_waypoints_time ON waypoints(time)`;
    - tabella `conversation_reads(conv TEXT PRIMARY KEY, read_time REAL NOT NULL)`;
    - `INSERT OR IGNORE INTO settings(key,value) VALUES('conv_read_baseline', <time.time()>)`;
    - tutto idempotente: `CREATE … IF NOT EXISTS`.
  - `Store`:
    - `add_message` scrive anche `reply_id`, `emoji` (0/1), `pki` (0/1) ed `error`;
    - `messages()` restituisce `reply_id`, `emoji: bool`, `pki: bool`, `error`;
    - `update_message_status(key, status, error: str | None = None)`;
    - `_NODE_FIELDS` aggiunge `public_key` e `key_changed`;
    - `upsert_waypoint(wp: dict) -> None`, dove il dict usa le chiavi delle colonne con `from_num` intero;
    - `delete_waypoint(wid: int) -> None`, che imposta `deleted=1`;
    - `get_waypoint(wid: int) -> dict | None`;
    - `active_waypoints(now: float, limit: int = 500) -> list[dict]`, con `deleted=0 AND (expire IS NULL OR expire=0 OR expire>now)`, i più recenti prima;
    - `mark_read(conv: str, t: float) -> float`: upsert con `MAX(read_time, t)`; restituisce il valore salvato;
    - `read_times() -> dict[str, float]`;
    - `read_baseline() -> float`: legge `conv_read_baseline`, 0 se manca;
    - `recent_radio_messages(limit: int = 5000) -> list[dict]`: messaggi con `radio_id` non nullo, stesse chiavi di `messages()`, i più recenti prima;
    - `purge_step`: cancella anche, a blocchi, i waypoint con `expire>0 AND expire<now` o con `time < pos_cutoff`, e le righe di `conversation_reads` più vecchie di `retention_messages_days`.

- [ ] **Step 1: test che falliscono.**
  - `test_db.py::test_migration_4_columns_and_tables`: un database a schema 3 (creato come in `test_migration_3_adds_broker_column`) dopo `connect` ha `user_version == 4`, le sei colonne, le due tabelle e la riga `conv_read_baseline`; il hook `before_migrate` è chiamato con `(conn, 3, 4)`.
  - `test_db.py::test_new_db_runs_migration_4`: un database nuovo ha le tabelle e `user_version == 4`.
  - `test_store.py::test_message_reply_emoji_pki_roundtrip`: `add_message({... "reply_id": 77, "emoji": True, "pki": True})` → `messages(None, None, 10)[0]` ha `reply_id == 77`, `emoji is True`, `pki is True`, `error is None`; `update_message_status(key, "failed", "NO_ROUTE")` → `error == "NO_ROUTE"`.
  - `test_store.py::test_waypoints_active_and_purge`: tre waypoint (`expire=None`; `expire = now-10`; `deleted` dopo `delete_waypoint`) → `active_waypoints(now)` ne restituisce uno solo; `purge_step` rimuove quello scaduto.
  - `test_store.py::test_mark_read_keeps_max`: `mark_read("ch:r1:0", 100)` poi `mark_read("ch:r1:0", 50)` → restituisce 100 e `read_times() == {"ch:r1:0": 100}`.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_db.py server/tests/test_store.py` → FAIL.
- [ ] **Step 3:** implementare `_migration_4` e i metodi di `Store` elencati.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): schema 4 con risposte, reazioni, PKI, waypoint e letture delle conversazioni`.

### Task 2: Decodifica di risposte, reazioni, PKI e waypoint  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/events.py`, `server/meshlens/mqtt_decode.py`, `server/meshlens/rf_convert.py` (solo il ramo `TEXT_MESSAGE_APP`, il ramo nuovo `WAYPOINT_APP` e il parametro `pki` di `_event`)
- Test: `server/tests/test_mqtt_decode.py`, `server/tests/test_rf_convert.py`

**Interfaces:**
- Produces, in `events.py`:
  - `TextData(text: str, reply_id: int | None = None, emoji: bool = False)`;
  - `WaypointData(id: int, lat: float | None, lon: float | None, name: str, description: str, icon: int, expire: int, locked_to: int)`: `lat`/`lon` valgono None se `(0,0)` o fuori intervallo; `expire` 0 = mai;
  - `MeshEvent.pki: bool = False`, aggiunto in fondo, dopo `broker`.
- `mqtt_decode`:
  - `TEXT_MESSAGE_APP` → `TextData(text, reply_id=data.reply_id or None, emoji=bool(data.emoji))`;
  - `WAYPOINT_APP` → `("waypoint", WaypointData(...))`;
  - `MeshEvent(pki=packet.pki_encrypted)`;
  - un pacchetto con `pki_encrypted` che non si decifra conta in `stats["pki_encrypted"]` invece di `undecodable`.
- `rf_convert`:
  - `TEXT_MESSAGE_APP` legge `decoded.get("replyId")` e `decoded.get("emoji")`;
  - `"WAYPOINT_APP"` legge `decoded["waypoint"]` (`id`, `latitudeI`, `longitudeI`, `name`, `description`, `icon`, `expire`, `lockedTo`);
  - `_event(..., pki=False)` riceve `bool(packet.get("pkiEncrypted"))`.
  - Un waypoint senza coordinate valide resta un evento (serve per le eliminazioni) con `lat`/`lon` None.

- [ ] **Step 1: test che falliscono.**
  - `test_mqtt_decode.py::test_text_reply_and_emoji`: `make_envelope(TEXT_MESSAGE_APP, …)` con `Data(reply_id=42, emoji=1, payload="👍".encode())` (estendere `helpers.make_envelope` con `reply_id`/`emoji` facoltativi) → `ev.payload.reply_id == 42`, `ev.payload.emoji is True`.
  - `test_mqtt_decode.py::test_waypoint_decoded`: `Waypoint(id=7, latitude_i=451000000, longitude_i=92000000, name="Ritrovo", icon=0x1F4CD, expire=0)` → `kind == "waypoint"`, `lat == pytest.approx(45.1)`, `icon == 0x1F4CD`.
  - `test_mqtt_decode.py::test_pki_flag_and_stat`: un pacchetto in chiaro con `pki_encrypted=True` → `ev.pki is True`; uno cifrato non decifrabile con `pki_encrypted=True` → `decode` restituisce None e `stats["pki_encrypted"] == 1`.
  - `test_rf_convert.py::test_text_reply_emoji_pki`: `{"decoded": {"portnum": "TEXT_MESSAGE_APP", "text": "ok", "replyId": 9, "emoji": 1}, "pkiEncrypted": True, …}` → `reply_id == 9`, `emoji is True`, `ev.pki is True`.
  - `test_rf_convert.py::test_waypoint_zero_coords`: un waypoint con `latitudeI: 0, longitudeI: 0, expire: 1` → evento con `lat is None` ed `expire == 1`.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_mqtt_decode.py server/tests/test_rf_convert.py` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): decodifica di risposte, reazioni, PKI e waypoint da MQTT e radio`.

### Task 3: Ingestione — campi dei messaggi, chiave pubblica, waypoint, avviso di chiave cambiata  _(modello: opus)_

**Files:**
- Modify: `server/meshlens/ingest.py` (solo `_build_message`, `_update_identity`, un ramo `waypoint` in `handle`, `set_status`, `record_outgoing`, `record_outgoing_mqtt` e il costruttore), `server/meshlens/alerts.py`, `server/meshlens/app.py` (`on_waypoint` e `on_status` con `error`)
- Test: `server/tests/test_ingest.py`, `server/tests/test_ingest_rf.py`, `server/tests/test_alerts.py`

**Interfaces:**
- Consumes: Task 1 (`Store`), Task 2 (`TextData`, `WaypointData`, `MeshEvent.pki`).
- Produces:
  - **Messaggi:** `_build_message` aggiunge `reply_id`, `emoji` e `pki` da evento e payload, ed `error: None`.
  - **Uscita:**
    - `record_outgoing(..., reply_id: int | None = None, emoji: bool = False)`;
    - `record_outgoing_mqtt(..., reply_id: int | None = None, emoji: bool = False)`;
    - il messaggio registrato porta i due campi e `pki: False`.
  - **Stato:**
    - `set_status(key, status, error: str | None = None)` aggiorna store e memoria;
    - chiama `on_status(key, status, error)`;
    - in `app.py` la lambda (`lambda key, status, error=None: …`) pubblica `{"type":"message_status","key","status","error"}`;
    - la chiamata diretta `on_status(key, "failed")` in `radio_manager._finish_send` resta valida fino al Task 4.
  - **Chiave pubblica:** `_update_identity(node, p, t)` con `t = ev.rx_time or time.time()`. Se `p` ha `public_key`:
    1. si calcola `b64 = base64.b64encode(key).decode()`;
    2. se `node["public_key"]` esiste ed è diverso da `b64`, allora `node["key_changed"] = t`;
    3. infine `node["public_key"] = b64`.
    
    Chiave vuota o None: nulla cambia. `_new_node` aggiunge `public_key: None, key_changed: None`. `mapreport` resta senza chiave.
  - **Waypoint:**
    - nel ramo `kind == "waypoint"` si costruisce il dict Waypoint del contratto (con `mine` da `self._radio_nodes`);
    - se `expire` non è 0 ed è minore o uguale a `ev.rx_time`, oppure le coordinate sono None: `store.delete_waypoint(id)` e `on_waypoint({"deleted": id})`;
    - altrimenti, si salva se `ev.source == "rf"` oppure se `locator.locate(lat, lon)` è nelle nazioni salvate, e si chiama sempre `on_waypoint(wp)`.
  - **Costruttore e app:**
    - `Ingestor.__init__(..., on_waypoint: Callable[[dict], None] | None = None)`;
    - in `app.py`, `on_waypoint` pubblica `{"type":"waypoint_deleted","id":…}` se il dict ha `deleted`, altrimenti `{"type":"waypoint","waypoint":…}`.
  - **Avvisi:** `compute_alerts` aggiunge `key_changed` per i nodi con `is_mine` **o** `is_favorite` e `now - key_changed < KEY_CHANGED_KEEP_S` (= 7·86400).
    - Il controllo «solo miei» degli altri tipi resta invariato: si ristruttura il `continue` iniziale in modo che i preferiti non-miei ricevano solo `key_changed`.
    - `KIND_ORDER` diventa `battery_low 0, silent 1, key_changed 2, chutil_high 3, firmware_old 4, back_online 5`.

- [ ] **Step 1: test che falliscono.**
  - `test_ingest.py::test_message_carries_reply_emoji_pki`: un evento di testo MQTT con `TextData("👍", reply_id=5, emoji=True)` e `pki=True` → il messaggio pubblicato e quello salvato hanno `reply_id == 5`, `emoji is True`, `pki is True`.
  - `test_ingest.py::test_public_key_change_detection` (Review Focus 4):
    - prima chiave `b"A"*32` → `key_changed is None`;
    - stessa chiave da RF → ancora None;
    - nodeinfo con `public_key=None` → la chiave resta;
    - chiave `b"B"*32` con `rx_time = 1000` → `key_changed == 1000` e `public_key` aggiornata;
    - il nodo salvato nello store ha gli stessi valori.
  - `test_ingest.py::test_waypoint_store_and_delete` (Review Focus 5):
    - waypoint RF valido → `on_waypoint` riceve il dict con `icon == "📍"` e `store.active_waypoints` lo contiene;
    - lo stesso id con `expire=1` → `on_waypoint({"deleted": id})` e lista vuota;
    - waypoint MQTT con coordinate in Francia e `saved_countries=["IT"]` → `on_waypoint` chiamato, store vuoto;
    - icona `0xD800` (surrogato) → `icon == ""`.
  - `test_ingest.py::test_set_status_with_error`: `set_status(key, "failed", "NO_ROUTE")` → `on_status` riceve `(key, "failed", "NO_ROUTE")` e il messaggio in memoria ha `error == "NO_ROUTE"`.
  - `test_ingest_rf.py::test_rf_reaction_dedup_keeps_fields`: la copia RF duplicata di una reazione arrivata prima da MQTT non perde `reply_id`/`emoji` dopo `_adopt_rf_copy`.
  - `test_alerts.py::test_key_changed_for_mine_and_favorite`:
    - un preferito non mio con `key_changed = now-3600` → un solo avviso `key_changed` con `since == now-3600`;
    - lo stesso con `key_changed = now-8*86400` → nessun avviso;
    - un nodo né mio né preferito → nessun avviso;
    - ordine `silent` prima di `key_changed` prima di `chutil_high`.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_ingest.py server/tests/test_ingest_rf.py server/tests/test_alerts.py` → FAIL.
- [ ] **Step 3:** implementare `ingest.py`, `alerts.py` e il collegamento in `app.py`.
- [ ] **Step 4:** stesso comando più `server/tests/test_app.py` → PASS (i test esistenti di `on_status` vanno adattati al terzo argomento).
- [ ] **Step 5: Commit** `feat(server): risposte, reazioni, chiave pubblica e waypoint nell'ingestione`.

### Task 4: Invio di risposte e reazioni, errori di consegna  _(modello: opus)_

**Files:**
- Modify: `server/meshlens/radio.py` (solo `send_text`), `server/meshlens/radio_manager.py` (`send`, `_finish_send`, `_on_ack`, `_early_acks`, `ROUTING_ERRORS`), `server/meshlens/mqtt_publish.py`, `server/meshlens/api.py` (`SendBody`, `MqttSendBody`, `send_radio`, `mqtt_send`)
- Test: `server/tests/test_radio.py`, `server/tests/test_radio_manager.py`, `server/tests/test_mqtt_publish.py`, `server/tests/test_api_radios.py`

**Interfaces:**
- Consumes: Task 3 (`record_outgoing(..., reply_id, emoji)`, `set_status(key, status, error)`).
- Produces:
  - `RadioConnector.send_text(text, channel_index, dest, reply_id: int | None = None, emoji: bool = False) -> int`:
    - **senza emoji:** `iface.sendText(text, destinationId=dest or BROADCAST, wantAck=True, channelIndex=channel_index, replyId=reply_id)`;
    - **con emoji:** la libreria non espone il campo, quindi si costruisce `mesh_pb2.MeshPacket(channel=channel_index)` con `decoded.portnum=TEXT_MESSAGE_APP`, `decoded.payload=text.encode()`, `decoded.reply_id=reply_id`, `decoded.emoji=1`, `id=iface._generatePacketId()`; poi `iface._sendPacket(pkt, dest or BROADCAST, wantAck=True)`, nel `_call` sotto `_send_lock`, come oggi. Commento: API privata della libreria 2.7.11.
  - `RadioManager.send(radio_id, text, channel_index=0, to=None, reply_id: int | None = None, emoji: bool = False)`:
    - valida: `emoji` senza `reply_id` → `ValueError("La reazione richiede il messaggio a cui reagire")`; con `emoji`, testo oltre 16 byte o con spazi → `ValueError("Reazione non valida")`; `reply_id` fuori da 1…2³²−1 → `ValueError("Messaggio di riferimento non valido")`;
    - il provvisorio porta `reply_id`, `emoji` e `pki: False`.
  - Gli errori di consegna arrivano fino al messaggio:
    - `_on_ack` passa `reason` (o `"TIMEOUT"`) a `set_status(msg_key, "failed", reason)`;
    - `_early_acks` salva `(status, reason)`;
    - `_finish_send` fallito usa `error="SEND_FAILED"`.
  - `ROUTING_ERRORS` copre tutti i codici di `mesh_pb2.Routing.Error` (tabella qui sotto), per i testi dei traceroute.
  - `mqtt_publish`:
    - `build_envelope(..., reply_id: int | None = None, emoji: bool = False)` imposta `Data.reply_id`/`Data.emoji`, sempre con `portnum=TEXT_MESSAGE_APP`;
    - `MqttSender.send(..., reply_id=None, emoji=False)` applica le stesse validazioni (`MqttSendError(400, "invalid_reaction", …)`), lo stesso limite e la stessa conferma, e passa i campi a `record`.
  - `api.py`:
    - `SendBody.reply_id: int | None = Field(None, ge=1, le=4294967295)` ed `emoji: bool = False`, uguali in `MqttSendBody`;
    - li inoltrano;
    - `ValueError` → 400, come oggi.

Tabella dei testi (copia esatta; la stessa va in `web/src/lib/strings/messaggi.ts` nel Task 9):

| Codice | Testo |
|---|---|
| NO_ROUTE | Nessun percorso verso il nodo |
| GOT_NAK | Rifiutato da un nodo lungo il percorso |
| TIMEOUT | Nessuna conferma entro il tempo massimo |
| NO_INTERFACE | Nessuna interfaccia disponibile per l'invio |
| MAX_RETRANSMIT | Nessuna conferma dopo i tentativi |
| NO_CHANNEL | Canale non disponibile sul destinatario |
| TOO_LARGE | Messaggio troppo grande |
| NO_RESPONSE | Nessuna risposta dal nodo |
| DUTY_CYCLE_LIMIT | Limite di tempo di trasmissione raggiunto: riprova più tardi |
| BAD_REQUEST | Richiesta non valida |
| NOT_AUTHORIZED | Non autorizzato |
| PKI_FAILED | Cifratura a chiave pubblica non riuscita |
| PKI_UNKNOWN_PUBKEY | Il destinatario non conosce ancora la tua chiave pubblica: attendi che riceva le info del tuo nodo |
| ADMIN_BAD_SESSION_KEY | Sessione di amministrazione scaduta |
| ADMIN_PUBLIC_KEY_UNAUTHORIZED | Chiave admin non autorizzata sul nodo |
| RATE_LIMIT_EXCEEDED | Troppi messaggi: il nodo ha applicato un limite, riprova più tardi |
| PKI_SEND_FAIL_PUBLIC_KEY | La tua radio non conosce la chiave pubblica del destinatario |
| SEND_FAILED | Invio alla radio non riuscito |
| (altro) | Errore di consegna (CODICE) |

Lato server, `TIMEOUT` per i traceroute resta `MSG_TRACE_TIMEOUT`.

- [ ] **Step 1: test che falliscono.**
  - `test_radio.py::test_send_text_reply_uses_reply_id`: con il finto iface, `send_text("ok", 0, "!0000abcd", reply_id=42)` → `sendText` chiamato con `replyId=42`.
  - `test_radio.py::test_send_reaction_builds_emoji_packet`: `send_text("👍", 1, None, reply_id=42, emoji=True)` → `_sendPacket` riceve un `MeshPacket` con `decoded.emoji == 1`, `decoded.reply_id == 42`, `channel == 1`, `decoded.portnum == TEXT_MESSAGE_APP`; il valore restituito è l'id generato.
  - `test_radio_manager.py::test_failed_ack_carries_reason`:
    - ack con `ok=False, reason="NO_ROUTE"` per un messaggio registrato → stato `failed`, `error == "NO_ROUTE"` in store e nell'evento `message_status`;
    - lo stesso arrivato in anticipo (`_early_acks`) → stesso risultato.
  - `test_radio_manager.py::test_reaction_validation`: `emoji=True` senza `reply_id` → `ValueError`; `emoji=True, text="ciao a tutti"` → `ValueError`.
  - `test_mqtt_publish.py::test_reply_roundtrip`: `build_envelope(..., reply_id=99, emoji=True)` decodificato da `EnvelopeDecoder` → `reply_id == 99`, `emoji is True`, `portnum == TEXT_MESSAGE_APP`.
  - `test_mqtt_publish.py::test_reaction_counts_for_rate_limit`: una reazione seguita entro 10 s da un testo → 429.
  - `test_api_radios.py::test_send_body_reply_fields`: `POST /api/radios/{id}/send` con `reply_id: 0` → 422; con `emoji: true` e senza `reply_id` → 400.
  - Un test sull'insieme dei codici: `set(ROUTING_ERRORS) >= set(mesh_pb2.Routing.Error.keys()) - {"NONE"}`.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_radio.py server/tests/test_radio_manager.py server/tests/test_mqtt_publish.py server/tests/test_api_radios.py` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): invio di risposte e reazioni via radio e MQTT, motivi degli errori di consegna`.

### Task 5: Waypoint via radio e API delle conversazioni  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/conversations.py`
- Modify: `server/meshlens/radio.py` (solo il metodo nuovo `send_waypoint`), `server/meshlens/radio_manager.py` (`send_waypoint`, `delete_waypoint`), `server/meshlens/api.py` (rotte dei waypoint e delle conversazioni)
- Test: `server/tests/test_conversations.py` (nuovo), `server/tests/test_radio.py`, `server/tests/test_api.py`

**Interfaces:**
- Consumes:
  - Task 1: `upsert_waypoint`, `get_waypoint`, `delete_waypoint`, `active_waypoints`, `mark_read`, `read_times`, `read_baseline`, `recent_radio_messages`;
  - Task 3: forma del dict Waypoint e `on_waypoint`, che vanno riusati per pubblicare.
- Produces:
  - `conversations.py`:
    - `BROADCAST_ID = "!ffffffff"`;
    - `conversation_key(msg: dict, local_ids: set[str]) -> str | None`: None senza `radio_id`; `ch:<radio>:<channel_index or 0>` se `to == BROADCAST_ID`; altrimenti `dm:<radio>:<peer>`, con `peer = to` se `direction == "out"` o `from in local_ids`, e `peer = from` negli altri casi. Identica a `conversationKey` di `web/src/lib/chat.ts`;
    - `summaries(msgs: list[dict], local_ids: set[str], reads: dict[str, float], baseline: float) -> list[dict]`:
      - per ogni chiave: `last_time`, `last_text`, `last_from`, `last_emoji` dell'ultimo messaggio, più `read_time` (`reads.get(key)`);
      - `unread` = numero di messaggi con `direction == "in"`, `from` non tra i `local_ids`, `emoji` falso e `time > max(read_time or 0, baseline)`;
      - ordine per `last_time` decrescente.
  - `RadioConnector.send_waypoint(wp: mesh_pb2.Waypoint, channel_index: int) -> int`: `iface.sendData(wp, destinationId=BROADCAST, portNum=WAYPOINT_APP, wantAck=False, channelIndex=channel_index)` sotto `_send_lock`, con gli stessi timeout ed errori di `send_text`.
  - `RadioManager.send_waypoint(radio_id, name, description, icon, lat, lon, expire_h, channel_index) -> dict`:
    - valida come nel contratto;
    - id casuale a 32 bit diverso da 0;
    - `locked_to` = nodo della radio;
    - `expire = int(time.time()) + expire_h*3600`, oppure 0;
    - dopo l'invio registra il waypoint (`source "rf"`, `mine True`) con lo stesso percorso di `on_waypoint`, così compare subito.
  - `RadioManager.delete_waypoint(wid) -> None`:
    - waypoint sconosciuto → `KeyError`;
    - `from` diverso dal nodo di ogni radio connessa → `PermissionError`;
    - altrimenti ri-invia lo stesso id con `expire=1` dalla radio del proprietario (o dalla prima connessa), poi `delete_waypoint` e pubblica `waypoint_deleted`.
  - Rotte API: `GET /api/waypoints`, `POST /api/radios/{radio_id}/waypoint`, `DELETE /api/waypoints/{id}`, `GET /api/conversations`, `POST /api/conversations/read`.
    - `local_ids` = gli id dei nodi delle radio (`ingestor.radio_node`) più i nodi con `is_local_radio`;
    - `key` di `read` valida se corrisponde a `^(ch|dm):r[0-9a-f]{8}:(\d|!?[0-9a-f]{8})$`, altrimenti 400;
    - `time` non può superare `time.time() + 60`.

- [ ] **Step 1: test che falliscono.**
  - `test_conversations.py::test_key_matches_web_rules`: i quattro casi (nessuna radio, broadcast con `channel_index` None → `ch:r…:0`, DM in uscita, DM in entrata da un nodo locale).
  - `test_conversations.py::test_unread_rules` (Review Focus 2):
    - con `baseline=100`, i messaggi a `time` 50 non contano;
    - un messaggio `out` non conta;
    - uno con `from` locale non conta;
    - una reazione non conta;
    - dopo `read_time=200` contano solo quelli con `time > 200`.
  - `test_radio.py::test_send_waypoint_uses_waypoint_port`: `sendData` chiamato con `portNum == WAYPOINT_APP`, `wantAck=False` e il protobuf con `locked_to`.
  - `test_api.py::test_waypoint_routes`:
    - nome di 31 byte → 400; icona `"ab"` → 400; `expire_h=0` → 400;
    - con una radio finta connessa → 202 e il WS riceve `waypoint`;
    - `DELETE` di un waypoint di un altro nodo → 403; del proprio → 200 e WS `waypoint_deleted`.
  - `test_api.py::test_conversations_read_broadcasts`:
    - `POST /api/conversations/read {"key":"ch:r1a2b3c4:0","time":500}` → `read_time == 500` e WS `conv_read`;
    - `GET /api/conversations` riflette `unread`;
    - una chiave malformata → 400.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_conversations.py server/tests/test_radio.py server/tests/test_api.py -k "waypoint or conversation or key_matches or unread"` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): invio ed eliminazione dei propri waypoint via radio, riepilogo e letture delle conversazioni`.

### Task 6: Notifiche esterne — toast di Windows e Telegram  _(modello: opus)_

**Files:**
- Create: `server/meshlens/notify.py`
- Modify:
  - `server/meshlens/secretbox.py`: `SECRET_KEYS = ("update_token", "telegram_token")`;
  - `server/meshlens/settings.py`: chiavi nuove in `DEFAULTS` e `_validate`; la gestione di `MASK` in `prepare_import` copre tutti i `SECRET_KEYS`;
  - `server/meshlens/api.py`: `put_settings` usa la maschera per ogni chiave di `SECRET_KEYS`; `AppContext.toast`; `AppContext.notifier`; rotte `/api/notify/*`; `AppContext.alerts()` chiama `notifier.on_alerts(old, new)`;
  - `server/meshlens/app.py`: creazione del notificatore; `_publish_changed` chiama `notifier.on_nodes(changed)`; la lambda di `on_message` chiama anche `notifier.on_message(msg)`;
  - `server/meshlens/tray.py`: `rt.ctx.toast = lambda title, body: icon.notify(body, title)`, impostato dopo la creazione dell'icona e protetto da `try` (un errore di `notify` non deve mai arrivare al server).
- Test: `server/tests/test_notify.py` (nuovo), `server/tests/test_settings.py`, `server/tests/test_api.py`, `server/tests/test_tray.py`

**Interfaces:**
- Consumes: gli avvisi `silent` e `back_online` (`compute_alerts`); i nodi cambiati (`live.take_changed()`); `rt.radios.radios()`; `scrub_text` da `settings.py`.
- Produces, in `notify.py`:
  - **Testi:** `TEXTS: dict[str, tuple[str, str]]`, titolo e corpo con segnaposto `str.format` (copia esatta):
    - `mine_offline`: («{name} non risponde», «Nessun pacchetto da {hours} h»);
    - `mine_online`: («{name} è tornato online», «Di nuovo sentito dopo {hours} h di silenzio»);
    - `new_node`: («Nodo nuovo: {name}», «Sentito via radio per la prima volta»);
    - `keyword`: (««{word}» in chat», «{name}: {text}»);
    - `test`: («Prova di MeshLens», «Le notifiche funzionano»).
  - **Errori:**
    - `class NotifyError(Exception)`, con un messaggio già ripulito dal token;
    - `TELEGRAM_NO_CHAT = "Scrivi un messaggio al bot su Telegram e riprova"`;
    - `TOAST_UNAVAILABLE = "Notifiche di Windows disponibili solo con MeshLens avviato dall'icona nell'area di notifica"`.
  - `telegram_send(token: str, chat_id: str, text: str, opener=urllib.request.urlopen, timeout: float = 10) -> None`: `POST https://api.telegram.org/bot{token}/sendMessage` con JSON `{chat_id, text, disable_web_page_preview: true}`; ogni errore diventa `NotifyError(scrub_text(str(e), token))`.
  - `telegram_find_chat(token, opener=...) -> tuple[str, str]`: `getUpdates`; restituisce l'id e il titolo (o il `first_name`) della chat dell'ultimo messaggio; nessun messaggio → `NotifyError(TELEGRAM_NO_CHAT)`.
  - `fold(text: str) -> str`: `casefold` più NFKD senza segni combinanti.
  - `class Notifier(get_settings, get_toast: Callable[[], Callable[[str,str],None] | None], get_radios: Callable[[], list[dict]], clock: Callable[[], float], send_telegram=telegram_send, run_bg: Callable[[Callable[[], None]], None] = <thread daemon>)`:
    - `seed(nodes: Iterable[dict]) -> None`: memorizza i `num` con `"rf"` in `sources` e imposta `quiet_until = clock() + QUIET_S` (= 300);
    - `on_nodes(changed: list[dict]) -> None`:
      1. se l'insieme degli id delle radio con `state == "connected"` è cambiato dall'ultima chiamata, si prolunga `quiet_until` di `QUIET_S`;
      2. un nodo con `"rf"` in `sources` e non ancora noto entra fra i noti;
      3. genera `new_node` solo se `notify_new_node` è attivo, `clock() >= quiet_until` e `last_heard` è entro 600 s;
    - `on_alerts(old: list[dict], new: list[dict]) -> None`: con `notify_mine_status` attivo, le chiavi `silent:*` e `online:*` presenti in `new` e non in `old` generano `mine_offline`/`mine_online` (con `value` come ore);
    - `on_message(msg: dict) -> str | None`:
      - considera solo `direction == "in"` e reazioni escluse;
      - la prima parola di `notify_keywords` contenuta in `fold(text)` genera `keyword`, con il testo tagliato a 120 caratteri;
      - restituisce la parola trovata;
    - `send(kind: str, dedup_key: str, **fmt) -> None`:
      - salta se la stessa `(kind, dedup_key)` è già partita negli ultimi `DEDUP_S` (= 600);
      - salta oltre `MAX_PER_HOUR` (= 30);
      - poi il toast, se `notify_toast` è attivo e il toast è disponibile;
      - poi Telegram, se `notify_telegram` è attivo con token e `chat_id`: in background tramite `run_bg`, mai nel loop;
      - registra `last_ok`/`last_error`;
    - `test(channel: str) -> None`: invio sincrono, solleva `NotifyError`;
    - `status() -> dict` con `toast_available`, `telegram_last_ok`, `telegram_last_error`.
- **Rotte:**
  - `GET /api/notify/status`;
  - `POST /api/notify/test`, che gira in `asyncio.to_thread` per Telegram;
  - `POST /api/notify/telegram/chat`, che usa il token salvato e risponde 400 se manca.

- [ ] **Step 1: test che falliscono** (`test_notify.py`, con orologio finto, `run_bg=lambda f: f()` e un finto `send_telegram` che registra le chiamate).
  - `test_quiet_after_start_and_radio_change` (Review Focus 3):
    - dopo `seed`, un nodo RF nuovo entro 300 s → nessuna notifica, ma il nodo diventa noto;
    - dopo 300 s, un nodo RF nuovo con `last_heard` recente → `new_node`;
    - un cambio delle radio connesse → altri 300 s di silenzio.
  - `test_new_node_needs_setting_and_recent_heard`: con `notify_new_node` falso → niente; con `last_heard` vecchio di 700 s → niente.
  - `test_mine_status_transitions`: `on_alerts([], [silent])` → `mine_offline` con le ore; la stessa coppia ripetuta → nessun doppione; `on_alerts([silent], [back_online])` → `mine_online`.
  - `test_keyword_folding`: `notify_keywords=["perche"]`, testo «Perché no?» → trovata; reazione o messaggio `out` → None.
  - `test_rate_and_dedup`: 31 parole chiave diverse in un'ora → 30 invii.
  - `test_telegram_error_scrubbed`: un `opener` che solleva `HTTPError` con l'URL contenente il token → il `NotifyError` e `status()["telegram_last_error"]` non contengono il token.
  - `test_find_chat`: `getUpdates` finto con due update → id dell'ultimo; con lista vuota → `NotifyError(TELEGRAM_NO_CHAT)`.
  - `test_settings.py::test_notify_settings_validation`:
    - `telegram_chat_id="abc"` → `ValueError`;
    - 21 parole chiave → `ValueError`;
    - `telegram_token` salvato si rilegge in chiaro con `load_settings` ed esce `MASK` da `mask_secrets`;
    - `prepare_import` con `telegram_token == MASK` lo salta.
  - `test_api.py::test_put_settings_keeps_masked_telegram_token`: `PUT` con `telegram_token: "••••"` non cambia il valore salvato.
  - `test_api.py::test_notify_test_without_config`: `POST /api/notify/test {"channel":"telegram"}` senza token → 400; `{"channel":"toast"}` con `ctx.toast` None → 400 `TOAST_UNAVAILABLE`.
  - `test_tray.py`: dopo l'avvio con `pystray` finto, `rt.ctx.toast("T","B")` chiama `icon.notify("B","T")`; un'eccezione di `notify` viene inghiottita.
- [ ] **Step 2:** `PYTHONPATH=server .venv/Scripts/python -m pytest -q server/tests/test_notify.py server/tests/test_settings.py server/tests/test_tray.py server/tests/test_api.py -k "notify or telegram or tray"` → FAIL.
- [ ] **Step 3:** implementare `notify.py`, le impostazioni, le rotte e il collegamento in `app.py` e `tray.py`.
- [ ] **Step 4:** stesso comando → PASS.
- [ ] **Step 5: Commit** `feat(server): notifiche esterne con toast di Windows e Telegram`.

### Task 7: Interfaccia — tipi, WebSocket, non letti, titolo e notifiche del browser (B1)  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/strings/messaggi.ts`, `web/src/lib/unread.svelte.ts`, `web/src/lib/unread.test.ts`, `web/src/lib/notify.ts`, `web/src/lib/notify.test.ts`, `web/src/lib/incoming.ts`
- Modify:
  - `web/src/lib/types.ts`: Message, Node, Alert e i nuovi `Waypoint` e `ConvSummary`;
  - `web/src/lib/api.ts`: `conversations()`, `markConversationRead(key, time)`, `waypoints()`, `sendWaypoint(radioId, body)`, `deleteWaypoint(id)`;
  - `web/src/lib/ws.ts` e `ws.test.ts`: `waypoint`, `waypointDeleted`, `convRead`, e `messageStatus(key, status, error)`;
  - `web/src/lib/stores.svelte.ts`: `setMessageStatus(key, status, error?)` e, in fondo, `app.waypoints` come `SvelteMap<number, Waypoint>` con `upsertWaypoint` e `removeWaypoint`;
  - `web/src/App.svelte`: carica `conversations()` e `waypoints()` nel loader, collega i nuovi handler WS, chiama `onIncoming(m)` nell'handler `message` e imposta `document.title` in un effetto;
  - `web/src/lib/shell/TopBar.svelte` e `BottomNav.svelte`: contatore sulla scheda Messaggi.

**Interfaces:**
- Consumes: i contratti JSON (Task 3–5).
- Produces:
  - `unread.svelte.ts`:
    - `export const unread = $state({ counts: {} as Record<string, number>, reads: {} as Record<string, number> })`;
    - `applySummaries(list: ConvSummary[]): void`, che sostituisce entrambi;
    - `noteIncoming(m: Message, localIds: Set<string>, activeConv: string | null, visible: boolean): string | null`: restituisce la chiave contata, oppure null se non conta (uscita, mittente locale, reazione, senza `radio_id`, conversazione attiva e visibile, `m.time <= reads[key]`);
    - `applyRead(key: string, time: number): void`: azzera `counts[key]` e alza `reads[key]` (mai abbassa);
    - `markRead(key: string, time: number): Promise<void>`: `applyRead` subito, poi la POST; un errore viene ignorato;
    - `totalUnread(counts: Record<string, number>): number`;
    - `setActiveConv(key: string | null): void` e `getActiveConv(): string | null`, una variabile **semplice**, non reattiva.
  - `notify.ts`:
    - `NOTIFY_KEY = 'meshlens.notify'`;
    - `loadNotifyPrefs(storage): { dm: boolean }` e `saveNotifyPrefs(storage, p)`;
    - `notifySupported(win): boolean`, cioè `'Notification' in win && win.isSecureContext`;
    - `shouldNotify(m: Message, key: string, prefs, permission: NotificationPermission, hidden: boolean): boolean`: solo DM (`key` che inizia con `dm:`), niente reazioni, `permission === 'granted'`, `hidden`;
    - `titleFor(base: string, n: number): string`: `"MeshLens"`, poi `"(3) MeshLens"`, oltre 99 `"(99+) MeshLens"`.
  - `incoming.ts`: `onIncoming(m: Message): void`.
    - Chiama `noteIncoming` con `localNodeIds(app.radios)`, `getActiveConv()` e `document.visibilityState === 'visible'`.
    - Se `shouldNotify` è vero, crea `new Notification(T.dmNotifyTitle(name), { body: m.text, tag: key })`. `onclick` porta la finestra in primo piano (`window.focus()`), poi `openChat(key)` e `navigate('chat')`.
  - `strings/messaggi.ts`: `export const T = {...}`, con almeno:
    - `unreadAria(n)`;
    - `dmNotifyTitle(name)` → «Messaggio da {name}»;
    - `notifyUnsupported` → «Le notifiche del browser richiedono HTTPS o l'accesso da questo PC»;
    - più i testi dei Task 8 e 9 man mano che servono.
  - `App.svelte`: `$effect(() => { document.title = titleFor('MeshLens', totalUnread(unread.counts)) })` (legge lo stato e scrive solo il DOM).
  - Contatore delle schede:
    - `TopBar` mostra `num(n)` accanto a «Messaggi» con `aria-label={T.unreadAria(n)}` quando `n > 0`;
    - `BottomNav` riceve la prop `unread = 0` e la mostra sulla voce `chat`, come gli avvisi su `more`.

- [ ] **Step 1: test che falliscono.**
  - `unread.test.ts`:
    - `applySummaries([{key:'dm:r1:!b', unread:2, read_time:10, …}])` → `counts['dm:r1:!b'] === 2`;
    - `noteIncoming` di un messaggio `in` nuovo → la chiave, e il contatore passa a 3;
    - lo stesso con `direction:'out'` → null; con `emoji:true` → null; con `from` locale → null;
    - con `activeConv` uguale e `visible` vero → null; con `visible` falso → contato;
    - `applyRead(key, 50)` → `counts` 0; poi `applyRead(key, 20)` → `reads` resta 50;
    - `totalUnread({a:2,b:3}) === 5`.
  - `notify.test.ts`:
    - `titleFor` nei tre casi;
    - `shouldNotify` vero solo per DM, `granted`, `hidden`, non reazione (quattro casi falsi);
    - `loadNotifyPrefs` con JSON rotto → `{dm:false}`;
    - `notifySupported({ isSecureContext:false, Notification: … })` → false.
  - `ws.test.ts`:
    - `dispatch({type:'waypoint', waypoint})` → `waypoint`;
    - `{type:'waypoint_deleted', id:7}` → `waypointDeleted(7)`;
    - `{type:'conv_read', key, time}` → `convRead`;
    - `{type:'message_status', key, status:'failed', error:'NO_ROUTE'}` → `messageStatus(key,'failed','NO_ROUTE')`.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/unread.test.ts src/lib/notify.test.ts src/lib/ws.test.ts` → FAIL.
- [ ] **Step 3:** implementare i moduli, poi i collegamenti in `App.svelte`, `TopBar` e `BottomNav`.
- [ ] **Step 4:** stesso comando e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): messaggi non letti, contatore nel titolo e notifiche del browser per i DM`.

### Task 8: Interfaccia — elenco conversazioni, ricerca, bozze, lista → conversazione (B2)  _(modello: opus)_

**Files:**
- Create: `web/src/lib/conversations.ts`, `web/src/lib/conversations.test.ts`, `web/src/lib/drafts.ts`, `web/src/lib/drafts.test.ts`, `web/src/components/chat/ConversationList.svelte`, `web/src/components/chat/Thread.svelte`, `web/src/components/chat/Composer.svelte`
- Modify:
  - `web/src/components/Chat.svelte`, che diventa il contenitore: stato `conv` più `view: 'list' | 'thread'`;
  - `web/src/lib/strings/messaggi.ts`.

**Interfaces:**
- Consumes: Task 7 (`unread`, `markRead`, `setActiveConv`); `groupMessages`, `conversationKey`, `splitKey` e `localNodeIds` da `chat.ts`; `attachChat` e `rememberConv`.
- Produces:
  - `conversations.ts`:
    - `export interface ConvItem { key: string; label: string; lastTime: number; preview: string; unread: number; kind: 'mqtt' | 'ch' | 'dm' }`;
    - `buildConversations(args: { radios: Radio[]; groups: Map<string, Message[]>; summaries: Record<string, ConvSummary>; counts: Record<string, number>; label: (key: string) => string; previewOf: (m: Message) => string }): ConvItem[]`:
      - `mqtt` sempre per primo;
      - poi tutte le conversazioni radio (canali delle radio anche senza messaggi, gruppi locali, riepiloghi del server), ordinate per `lastTime` decrescente, che è il massimo tra l'ultimo messaggio locale e `last_time` del riepilogo;
      - a parità, per etichetta (`localeCompare` `it`);
    - `filterConversations(items: ConvItem[], query: string, groups: Map<string, Message[]>): ConvItem[]`: confronto senza maiuscole né accenti (NFD) su etichetta, anteprima e testo dei messaggi caricati; la query vuota restituisce tutto;
    - `previewText(m: Message, nodeName: (id: string) => string, localIds: Set<string>): string`: «Tu: …» per i propri; per le reazioni `T.reactionPreview(nome, emoji)`; tagliato a 80 caratteri con «…».
  - `drafts.ts`:
    - `DRAFTS_KEY = 'meshlens.drafts'`;
    - `loadDraft(storage, conv): string`;
    - `saveDraft(storage, conv, text): void`: il testo vuoto rimuove la voce; oltre 50 voci si tolgono le più vecchie (ordine di inserimento);
    - JSON rotto → nessuna bozza e nessuna eccezione.
  - `ConversationList.svelte`, con props `{ items: ConvItem[]; active: string; onopen: (key: string) => void }`:
    - campo di ricerca (`type="search"`, `aria-label`);
    - righe `button` di almeno 44 px con etichetta, anteprima, orario relativo (`ago`) e contatore;
    - riga in grassetto quando `unread > 0`;
    - stato vuoto della ricerca `T.noConversationMatch`.
  - `Thread.svelte`, con props `{ conv: string; msgs: Message[]; now: number; onpick; onback: () => void }`:
    - contiene la lista dei messaggi, «Carica precedenti» e lo scorrimento in fondo, spostati da `Chat.svelte` senza cambiarne il comportamento;
    - testata con «‹ Conversazioni» (`onback`) ed etichetta;
    - per `mqtt` mostra `MessageFeed`.
  - `Composer.svelte`: il compositore attuale spostato da `Chat.svelte` con la stessa logica di «Invia via».
    - Props `{ conv: string; replyTo: Message | null; oncancelreply: () => void; onsent: (m: Message) => void }`.
    - Il testo si inizializza con `loadDraft` al cambio di `conv` e si salva con `saveDraft` in `oninput` (non in un effetto).
    - Dopo l'invio riuscito: `saveDraft(conv, '')`.
  - `Chat.svelte`:
    - `view` parte da `'thread'` se c'è una conversazione chiesta (`attachChat`, link, vista ricordata), altrimenti da `'list'`; vale uguale su telefono e desktop;
    - all'apertura di una conversazione: `setActiveConv(key)`, `rememberConv(key)` e `view = 'thread'`;
    - al ritorno alla lista e allo smontaggio: `setActiveConv(null)`.
    - **Segnare letto** (in `Thread.svelte` o `Chat.svelte`): un `$effect` legge prima `msgs` (tempo dell'ultimo messaggio) e uno stato `$state` di visibilità aggiornato da `visibilitychange`, poi confronta con la variabile semplice `lastMarked`; se c'è un messaggio più nuovo e la pagina è visibile, chiama `markRead(conv, t)`. Lo stato `unread` non si legge in quell'effetto.

- [ ] **Step 1: test che falliscono.**
  - `conversations.test.ts`:
    - con due radio, un DM recente e un canale vuoto → ordine `mqtt`, DM, canale vuoto;
    - un riepilogo del server più recente dei messaggi caricati sposta la sua conversazione in alto;
    - `filterConversations(items, 'perche', groups)` trova una conversazione il cui messaggio caricato contiene «Perché»;
    - `previewText` di un proprio messaggio inizia con «Tu: »;
    - una reazione dà `T.reactionPreview`;
    - 100 caratteri → 80 più «…».
  - `drafts.test.ts`:
    - salva e rilegge;
    - testo vuoto → voce rimossa;
    - 51 conversazioni → la prima scompare;
    - `localStorage` con `"{"` → `loadDraft` restituisce `''`.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/conversations.test.ts src/lib/drafts.test.ts` → FAIL.
- [ ] **Step 3:** implementare `conversations.ts` e `drafts.ts`.
- [ ] **Step 4:** dividere `Chat.svelte` nei tre componenti e collegare elenco, bozze e lettura; i test esistenti `chat.test.ts` e `send.test.ts` restano verdi: `npx vitest run src/lib/chat.test.ts src/lib/send.test.ts src/lib/conversations.test.ts src/lib/drafts.test.ts` e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): elenco delle conversazioni con ricerca, bozze e passaggio lista-conversazione`.

### Task 9: Interfaccia — risposte, reazioni, lucchetto PKI, errori di consegna, chiave cambiata (B3, B9)  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/reactions.ts`, `web/src/lib/reactions.test.ts`, `web/src/components/chat/MessageActions.svelte`
- Modify:
  - `web/src/components/chat/Thread.svelte`, `web/src/components/chat/Composer.svelte`, `web/src/components/MessageFeed.svelte`;
  - `web/src/components/NodeDetail.svelte` (solo una riga «Chiave pubblica» e il banner di chiave cambiata);
  - `web/src/lib/shell/AlertsList.svelte` e `web/src/lib/alerts.ts` (il tipo `key_changed`);
  - `web/src/lib/send.ts` (`mqttBody` con `reply_id` ed `emoji`);
  - `web/src/lib/strings/messaggi.ts`; `web/src/lib/ui/icons.ts` (`lock`, `reply`, `smile`, `key`).

**Interfaces:**
- Consumes: i campi `reply_id`, `emoji`, `pki` ed `error` di Message; `public_key`/`key_changed` di Node; `Composer.replyTo` (Task 8).
- Produces:
  - `reactions.ts`:
    - `export const REACTIONS = ['👍', '❤️', '😂', '😮', '😢', '🙏'] as const`;
    - `export interface ThreadItem { msg: Message; replyTo: Message | null; replyMissing: boolean; reactions: { emoji: string; count: number; names: string[]; mine: boolean }[]; orphan: boolean }`;
    - `threadItems(msgs: Message[], nodeName: (id: string) => string, localIds: Set<string>): ThreadItem[]`:
      - le reazioni con target trovato (`packet_id === reply_id` nella stessa lista) si raggruppano sul target, per emoji e nell'ordine di arrivo, e non compaiono come riga propria;
      - una reazione senza target diventa `orphan: true` (Review Focus 1);
      - una risposta con target assente ha `replyMissing: true`;
    - `routingErrorText(code: string | null | undefined): string`: la tabella del Task 4, letta da `T.routingErrors`; un codice ignoto dà `T.routingErrorUnknown(code)`;
    - `keyChangedRecently(node: Node | undefined, nowS: number): boolean`: vero entro 7 giorni.
  - `MessageActions.svelte`: pulsante «Azioni messaggio» (≥ 44 px su telefono) che apre un menu con «Rispondi» e le sei reazioni.
    - `onreply(m)` imposta `replyTo` nel compositore;
    - `onreact(m, emoji)` invia subito: `POST /radios/{id}/send` con `{text: emoji, emoji: true, reply_id: m.packet_id, channel_index, to}`, oppure via MQTT con `mqttBody`, secondo la scelta «Invia via» corrente e con la stessa conferma della prima volta.
    - Un messaggio senza `packet_id` (provvisorio) non mostra le azioni.
  - **`Thread.svelte` e `MessageFeed.svelte`:**
    - sopra il testo, la citazione «nome · anteprima»; cliccandola si scorre al messaggio, oppure si legge `T.replyMissing`;
    - sotto la bolla, le chip delle reazioni con `title` dei nomi;
    - le righe orfane compatte `T.orphanReaction(emoji, name)`;
    - il lucchetto (`Icon lock`, `aria-label={T.pkiAria}`) se `m.pki`;
    - per `status === 'failed'`, il testo `routingErrorText(m.error)` sotto la bolla.
  - **Banner nel DM** (`kind="warn"`): se `keyChangedRecently(nodo del DM)`, il testo è `T.keyChangedBanner(name, data)`, «La chiave pubblica di {name} è cambiata il {data}: può essere un reset del nodo o un nodo falso. Verifica prima di fidarti.».
  - **`Composer.svelte`:** quando `replyTo` non è null mostra la chip `T.replyingTo(name)`, con anteprima e «✕»; l'invio aggiunge `reply_id: replyTo.packet_id`.
  - **`NodeDetail.svelte`:** riga «Chiave pubblica: presente / assente» e lo stesso banner di chiave cambiata.
  - **`alerts.ts`:** `key_changed` ha tono `warn`, icona `key` e testo `T.alertKeyChanged(name)`.

- [ ] **Step 1: test che falliscono** (`reactions.test.ts`).
  - Messaggio A (`packet_id` 10) più due 👍 (`reply_id` 10) da due nodi diversi → un solo `ThreadItem` con `reactions[0].count === 2` e due nomi.
  - Reazione con `reply_id` 999 → un item `orphan: true` (Review Focus 1).
  - Risposta con `reply_id` 999 → `replyMissing: true`.
  - Risposta a 10 → `replyTo.packet_id === 10`.
  - Una reazione propria → `mine: true`.
  - `routingErrorText('PKI_UNKNOWN_PUBKEY')` è uguale al testo della tabella; `routingErrorText('XYZ')` contiene «XYZ».
  - `keyChangedRecently` con 6 giorni → true; con 8 giorni → false; con `undefined` → false.
  - Nel test esistente `send.test.ts`, `mqttBody` con `reply_id` lo include, e senza non aggiunge chiavi nuove.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/reactions.test.ts src/lib/send.test.ts src/lib/alerts.test.ts` → FAIL.
- [ ] **Step 3:** implementare `reactions.ts`, poi i componenti.
- [ ] **Step 4:** stesso comando e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): risposte e reazioni, lucchetto PKI, motivi degli errori e avviso di chiave cambiata`.

### Task 10: Interfaccia — waypoint sulla mappa e creazione dei propri (B11)  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/waypoints.ts`, `web/src/lib/waypoints.test.ts`, `web/src/lib/map/WaypointLayer.ts`, `web/src/lib/map/WaypointPopup.svelte`, `web/src/components/WaypointForm.svelte`, `web/src/lib/strings/waypoint.ts`
- Modify:
  - `web/src/components/MapView.svelte`: `addWaypointLayers` in `setup()` dopo i nodi; il clic sul layer apre il popup; il menu contestuale (tasto destro o pressione lunga di 600 ms) mostra «Aggiungi waypoint qui»;
  - `web/src/lib/map/MapControls.svelte`: pulsante «Waypoint» che mostra o nasconde il layer, salvato in `meshlens.view` come `waypoints: boolean` (default true);
  - `web/src/lib/viewstate.ts` e il suo test.

**Interfaces:**
- Consumes: Task 7 (`app.waypoints`, `sendWaypoint`, `deleteWaypoint`); `readDocumentTokens()`.
- Produces:
  - `waypoints.ts`:
    - `export const WP_ICONS = ['📍','🏠','⛺','🚗','🚩','📡','🏥','⛽','🔥','💧','🍴','⭐'] as const`, tutti di un solo codepoint;
    - `waypointData(list: Waypoint[], nowS: number): FeatureCollection`: esclude gli scaduti; le proprietà sono `id`, `name`, `img` (`'wp-' + codepoint esadecimale`, oppure `'wp-default'` se `icon` è vuota) e `mine`;
    - `validateWaypoint(f: { name: string; description: string; lat: number; lon: number; expireH: number | null }): string | null`: restituisce `T` (strings/waypoint) per nome vuoto, nome oltre 30 byte, descrizione oltre 100 byte o coordinate fuori intervallo, null se valido;
    - `expiryLabel(expire: number | null, nowS: number): string`: `T.noExpiry` oppure `T.expiresAt(data)` con `Intl` `it-IT`.
  - `WaypointLayer.ts`:
    - `addWaypointLayers(map, tk)`: sorgente `waypoints` e layer `symbol` `wp-icons` (`icon-image: ['get','img']`, `text-field` del nome solo se ci sono glifi, come per i nodi);
    - `ensureWaypointImage(map, name)`: disegna l'emoji su un canvas 48×48 con il font di sistema (cerchio di sfondo `tk.surface`, bordo `tk.accent` se `mine`) e chiama `map.addImage(name, imageData, { pixelRatio: 2 })`;
    - è registrato sull'evento `styleimagemissing` per i nomi `wp-*`.
  - `WaypointForm.svelte`, in una `Modal`:
    - nome, descrizione, griglia di `WP_ICONS` (pulsanti ≥ 44 px con `aria-pressed`), scadenza (`Segmented`: Mai / 1 h / 24 h / 7 giorni → `null`, 1, 24, 168), radio e canale (solo radio connesse);
    - errori da `validateWaypoint`;
    - invio con `sendWaypoint`.
    - Senza radio connesse: `Banner` `T.needRadio`, «Collega una radio per inviare waypoint: via MQTT non si pubblicano».
  - `WaypointPopup.svelte`: icona, nome, descrizione, autore (`from_name` o id), `expiryLabel`, «Copia coordinate» (`clipboard.ts`); «Elimina per tutti» solo se `mine`, con conferma `Modal`.

- [ ] **Step 1: test che falliscono.**
  - `waypoints.test.ts`:
    - `waypointData` con uno scaduto e uno valido → una feature con `img === 'wp-1f4cd'`; con icona `""` → `'wp-default'`;
    - `validateWaypoint` con un nome di 31 byte («à» × 16) → errore; con nome vuoto → errore; con `lat: 91` → errore; un caso valido → null;
    - `expiryLabel(null, …) === T.noExpiry`.
  - `viewstate.test.ts`: `waypoints` assente → `true`; `false` salvato → `false`.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/waypoints.test.ts src/lib/viewstate.test.ts` → FAIL.
- [ ] **Step 3:** implementare `waypoints.ts` e `WaypointLayer.ts`.
- [ ] **Step 4:** componenti e collegamento in `MapView` (`pushWaypoints()` dopo ogni `setup` e a ogni cambio di `app.waypoints`, come `pushNodes`); stesso comando e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): waypoint sulla mappa e invio dei propri via radio`.

### Task 11: Interfaccia — sezione «Notifiche» delle Impostazioni (B12, B1)  _(modello: haiku)_

**Files:**
- Create: `web/src/components/settings/Notifications.svelte`, `web/src/lib/strings/notifiche.ts`
- Modify: `web/src/components/Settings.svelte` (solo l'import e una `<Card>` in più, dopo «Avvisi»), `web/src/lib/settings.ts` (campi nuovi di `AppSettings` e `parseKeywords(text: string): string[]`), `web/src/lib/settings.test.ts`, `web/src/lib/api.ts` (`notifyStatus()`, `notifyTest(channel)`, `telegramFindChat()`)

**Interfaces:**
- Consumes: Task 6 (impostazioni e rotte), Task 7 (`loadNotifyPrefs`, `saveNotifyPrefs`, `notifySupported`).
- Produces:
  - `parseKeywords(text)`: divide su virgole e a capo, toglie gli spazi agli estremi e scarta le voci sotto i 2 caratteri e i doppioni (senza maiuscole); al massimo 20 voci.
  - **`Notifications.svelte`, gruppo «Su questo dispositivo»:** `Switch` «Notifica i messaggi diretti quando MeshLens non è in primo piano».
    - Al passaggio a vero chiama `Notification.requestPermission()`.
    - Se il permesso viene negato, mostra `T.permissionDenied` e lo switch torna falso.
    - Se `!notifySupported(window)`, lo switch è disattivato con `T.notifyUnsupported` (Task 7).
  - **`Notifications.svelte`, gruppo «Notifiche esterne»:**
    - `Switch` «Notifiche di Windows», disattivato con `TOAST_UNAVAILABLE` se `notifyStatus().toast_available` è falso;
    - `Switch` «Telegram»;
    - campo del token come in `Updates.svelte`: si mostra «Impostato» con «Cambia» e «Rimuovi», e non si rilegge mai il valore;
    - campo «Id chat» con il pulsante «Trova chat» (`telegramFindChat`, che compila l'id e mostra il titolo);
    - pulsanti «Invia prova» per Windows e per Telegram, con l'esito in un `Toast`;
    - eventi: `Check` «Un mio nodo si spegne o torna online», `Check` «Un nodo nuovo sentito via radio», area di testo «Parole chiave in chat (separate da virgola)»;
    - ultimo errore di Telegram, se presente, in un `Banner` `warn`.
  - Il salvataggio usa la stessa `PUT /api/settings` delle altre sezioni.

- [ ] **Step 1: test che falliscono.** `settings.test.ts::parseKeywords`: `" Ciao, ciao,\nx, soccorso "` → `['Ciao', 'soccorso']`; 25 voci → 20.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/settings.test.ts` → FAIL.
- [ ] **Step 3:** implementare `parseKeywords`, le funzioni di `api.ts` e il componente.
- [ ] **Step 4:** stesso comando e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): impostazioni delle notifiche del browser, di Windows e di Telegram`.

### Task 12: Verifica finale  _(modello: sonnet)_

**Files:**
- Nessun file nuovo. Correzioni piccole dove la verifica trova problemi, ognuna con il suo commit `fix: …`.

- [ ] **Step 1: suite complete.**
  - `PYTHONPATH=server .venv/Scripts/python -m pytest -q` → tutti verdi;
  - `cd web && npx vitest run` → tutti verdi;
  - `cd web && npm run check` → 0 errori;
  - `cd web && npm run build` → build riuscita.
- [ ] **Step 2: migrazione reale.**
  - Copiare un database a schema 3 (quello di `tools/demo_seed.py` prima della fase) e avviare il server.
  - Deve comparire il backup `pre-migrazione` e `user_version` deve valere 4.
  - `GET /api/conversations` → `unread` 0 ovunque (Review Focus 2).
- [ ] **Step 3: controllo nel browser** (server demo, dati inseriti con richieste API o SQL sulla copia) a **1280×800** e **390×844**, con il tema scuro e con quello chiaro.
  - **B1:**
    - un DM che arriva con la scheda Mappa aperta → contatore su «Messaggi» e `(1) MeshLens` nel titolo;
    - aprendo la conversazione il contatore si azzera anche in una seconda scheda del browser;
    - notifica del browser con la pagina nascosta su `127.0.0.1`;
    - da LAN in HTTP lo switch è disattivato con il motivo.
  - **B2:**
    - ordine per attività con «Pubblico (MQTT)» in cima;
    - la ricerca trova per nome e per testo;
    - la bozza resta cambiando conversazione e ricaricando;
    - sul telefono si passa da lista a conversazione e si torna indietro;
    - la tastiera non copre il compositore.
  - **B3:**
    - una reazione ricevuta compare come chip sotto il messaggio e non come bolla;
    - «Rispondi» mostra la citazione; l'invio via radio porta `reply_id`;
    - la reazione via MQTT chiede la conferma della prima volta e rispetta i 10 s;
    - la reazione a un messaggio non caricato è una riga compatta.
  - **B9:**
    - lucchetto su un DM con `pki`;
    - un errore `NO_ROUTE` simulato mostra il testo italiano;
    - un cambio di chiave su un preferito → avviso nel popover, banner nel DM e nel dettaglio nodo.
  - **B11:**
    - waypoint ricevuto sulla mappa con l'emoji, anche dopo il cambio di tema e con la mappa offline (immagine ricreata da `styleimagemissing`);
    - creazione dal menu contestuale con una radio finta;
    - «Elimina per tutti» lo toglie;
    - un waypoint con `expire = 1` scompare.
  - **B12:**
    - «Invia prova» di Windows dall'eseguibile con la tray;
    - Telegram con un bot di prova dell'utente, **solo se l'utente fornisce token e chat in chat**: altrimenti si verifica il percorso d'errore (token finto → messaggio senza token);
    - nel log nessuna traccia del token.
- [ ] **Step 4: controllo automatico del layout** a 390×844 su Messaggi, mappa con popup di waypoint, modulo del waypoint e Impostazioni → Notifiche:
  - nessun testo nuovo sotto i 14 px;
  - nessun elemento cliccabile nuovo sotto i 44×44 px;
  - nessuno scorrimento orizzontale;
  - `grep -nE "#[0-9a-fA-F]{3,8}\b|rgb\(" ` sui file creati da questa fase → nessun risultato fuori dai test.
- [ ] **Step 5: confini.**
  - `git diff --stat main...HEAD` deve confermare:
    - in `radio.py`, `rf_convert.py` e `ingest.py` solo i punti elencati nelle Global Constraints;
    - `SCHEMA` di `db.py` invariato (tabelle nuove solo in `_migration_4`);
    - nessuna pubblicazione MQTT di tipi diversi da `TEXT_MESSAGE_APP`: `grep -n "portnum" server/meshlens/mqtt_publish.py`;
    - nessun cambio di versione.
  - `grep -rn "'[A-ZÀ-Ú][a-zà-ú ]\{12,\}'" web/src/components/chat web/src/components/WaypointForm.svelte web/src/components/settings/Notifications.svelte` → nessun testo italiano scritto direttamente nei componenti nuovi, fuori da `strings/`.
- [ ] **Step 6: Commit** delle eventuali correzioni (`fix: …`). La fase si chiude senza rilascio.
