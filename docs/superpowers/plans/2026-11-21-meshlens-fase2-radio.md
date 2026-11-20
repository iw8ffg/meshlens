# MeshLens — Fase 2 (Radio USB e Bluetooth) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collegare a MeshLens più radio Meshtastic contemporaneamente (USB seriale e Bluetooth LE), unire il traffico RF a quello MQTT sulla mappa, e chattare via radio (canali e messaggi diretti) con stato di consegna, da PC e telefono.

**Architecture:** Un `RadioManager` sul server gestisce un `RadioConnector` per radio; ogni connettore crea l'interfaccia della libreria `meshtastic` in un thread (`asyncio.to_thread`) e la ricrea con backoff quando cade. Un unico `PubSubHub` si iscrive una sola volta ai topic globali della libreria e smista i pacchetti al connettore giusto confrontando l'oggetto `interface`; i pacchetti diventano `MeshEvent(source="rf")` tramite `rf_convert` e passano dall'`Ingestor` esistente sul loop asyncio. L'interfaccia web aggiunge un pannello Radio, chat per canale/diretta con scelta della radio, e "sentito da" nel dettaglio nodo.

**Tech Stack:** come fase 1 + `meshtastic` 2.7.11 (`SerialInterface`, `BLEInterface`, pypubsub), `pyserial` (`serial.tools.list_ports`), bleak 3.1 (backend WinRT).

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md` (§5.1 Gestore radio, §6.2, §9 Bluetooth). Note sulla libreria verificate sul sorgente: `docs/superpowers/research/2026-11-20-meshtastic-python-api.md` (**leggerle prima di ogni task server**).

## Global Constraints
- Tutti i vincoli della fase 1 restano validi (porta 8686, PIN, una sola connessione SQLite usata solo dal thread del loop asyncio, mai `publish` su MQTT, UI in italiano, mai `{@html}`).
- Ogni chiamata bloccante della libreria `meshtastic` (costruttori, `close()`, `sendText`, `sendData`, scan BLE) gira in `asyncio.to_thread`; ogni chiamata è protetta da `except BaseException` (la libreria può chiamare `sys.exit`).
- I listener pubsub non fanno lavoro: inoltrano con `loop.call_soon_threadsafe` e basta (il thread di pubblicazione della libreria è unico per tutte le radio).
- `SerialInterface` sempre con `devPath` esplicito. Mai due connettori sulla stessa porta o indirizzo.
- Riconnessione: ricreare l'interfaccia (la libreria non si riconnette); backoff 2, 5, 10, 30, 60 s, poi ogni 60 s; sempre `close()` sull'interfaccia vecchia.
- Id radio: `"r"` + 8 caratteri esadecimali casuali, stabile nel database.
- Su Windows 11 ogni scrittura seriale costa ≥ 1 s (limite della libreria): l'invio è asincrono e l'interfaccia mostra "in invio".
- Le chiavi `raw` e `payload` dei pacchetti della libreria non vanno mai serializzate verso il browser.
- Fonte `"rf"` sempre persistita (regola fase 1: RF si salva sempre).

## Review Focus
1. Radio scollegata (cavo staccato / Bluetooth fuori portata): stato "riconnessione", nessun crash, nessun thread o timer che impedisce la chiusura dell'app → test in Task 3.
2. Due radio che sentono lo stesso pacchetto, e lo stesso pacchetto anche da MQTT: un solo messaggio, "sentito da" con entrambe le radio e SNR di ciascuna → test in Task 5.
3. Invio verso un nodo che non risponde: stato "non consegnato" dopo il timeout, nessun blocco dell'API → test in Task 3 e Task 5.
4. Porta COM occupata da un altro programma (es. app o CLI Meshtastic): errore leggibile in italiano ("porta in uso da un altro programma"), non uno stack trace → test in Task 3.
5. Testo in uscita vuoto, oltre 200 byte UTF-8, o con emoji: rifiutato con messaggio chiaro / inviato correttamente → test in Task 6.

---

## File Structure
```
tools/radio_probe.py              prova rapida da riga di comando (USB/BLE), non usata dall'app
server/meshlens/rf_convert.py     dict pacchetto/nodo della libreria → MeshEvent
server/meshlens/pubsub_hub.py     iscrizione unica ai topic meshtastic, smistamento per interfaccia
server/meshlens/radio.py          RadioConnector: ciclo di vita, riconnessione, invio, ack
server/meshlens/radio_manager.py  RadioManager: elenco radio (DB), porte, scansione BLE
server/meshlens/db.py             + tabella radios, colonne nuove in messages (migrazione)
server/meshlens/store.py          + metodi radios e messaggi in uscita
server/meshlens/ingest.py         + heard_by, messaggi in uscita, stato consegna
server/meshlens/api.py            + endpoint /api/radios..., /api/radios/{id}/send
server/meshlens/app.py            + avvio/arresto RadioManager
web/src/lib/types.ts, api.ts, ws.ts, stores.svelte.ts   + radio, stato messaggi
web/src/components/Radios.svelte  pannello radio (nuova scheda "Radio")
web/src/components/Chat.svelte    chat per radio/canale/diretta con invio (sostituisce MessageFeed come scheda Chat; il feed MQTT diventa la vista "Pubblico" dentro Chat)
web/src/components/NodeDetail.svelte  + "Sentito da", pulsante "Messaggio diretto"
```

## Contratti nuovi
**Radio JSON**: `{"id":"r1a2b3c4d","name":"Heltec base","kind":"usb"|"ble","address":"COM5"|"AA:BB:..","auto_connect":true,"state":"disconnected"|"connecting"|"connected"|"reconnecting"|"error","error":null|"testo italiano","my_node_id":"!a1b2c3d4"|null,"my_node_name":str|null,"channels":[{"index":0,"name":"LongFast","role":"PRIMARY"}]}`
**Nodo JSON** (aggiunte): `"heard_by": {"r1a2b3c4d": {"snr": -7.5, "rssi": -110, "hops": 0, "time": 1763660123}}`; `"sources"` può contenere `"rf"`; `"is_local_radio": true` per i nodi che sono una radio collegata.
**Messaggio JSON** (aggiunte): `"direction":"in"|"out"`, `"radio_id": str|null`, `"channel_index": int|null`, `"packet_id": int|null`, `"status": null|"sending"|"sent"|"acked"|"failed"`, `"to"` = `"!ffffffff"` per broadcast. Chiave messaggi in uscita: `f"out:{radio_id}:{packet_id}"`.
**WebSocket** (aggiunte): `{"type":"radios","radios":[<radio>…]}` a ogni cambio di stato; `{"type":"message_status","key":str,"status":str}`.
**Porta JSON**: `{"device":"COM5","description":"Silicon Labs CP210x","vid":"10C4","pid":"EA60","likely_meshtastic":true,"in_use_by":null|"r1a2b3c4d"}` — `likely_meshtastic` se VID in {239A, 303A, 10C4, 1A86, 2886}.
**BLE JSON**: `{"address":"AA:BB:..","name":"Meshtastic_1a2b"}`.

---

### Task 1: Prova rapida radio (Bluetooth e USB)
**Files:** Create `tools/radio_probe.py`
**Interfaces:** nessuna verso l'app.
- [ ] **Step 1:** CLI: `python tools/radio_probe.py ports` (elenca porte con VID/PID/descrizione), `ble-scan` (`BLEInterface.scan()`, stampa nome e indirizzo), `usb COM5 [--seconds 60]` e `ble <indirizzo|nome> [--seconds 60]`: si collega, stampa nodo locale (id, nome, firmware da `iface.metadata`), numero di nodi in `iface.nodes`, canali (`localNode.channels`), poi per N secondi stampa una riga per pacchetto ricevuto (`fromId`, `decoded.portnum`, `rxSnr`, `rxRssi`, `hopStart-hopLimit`); infine `close()` e stampa il tempo di chiusura. Con `--send "testo"` invia un messaggio sul canale 0 e stampa l'ack (ascoltando `meshtastic.receive.routing` con `requestId`).
- [ ] **Step 2:** Verifica senza hardware: `python tools/radio_probe.py ports` gira senza errori.
- [ ] **Step 3 (con l'utente):** USB Heltec V3 e una radio BLE (abbinata prima da Impostazioni Windows se richiesto). Annotare nel report: tempi di connessione, se il PIN Bluetooth viene chiesto da Windows, comportamento staccando il cavo e spegnendo la radio BLE, se due radio insieme funzionano (avviare due istanze). Questi risultati decidono se il Task 3 usa `BLEInterface` così com'è.
- [ ] **Step 4:** Commit — `git commit -m "feat: strumento di prova radio USB/BLE"`

### Task 2: Conversione pacchetti RF
**Files:** Create `server/meshlens/rf_convert.py` · Test `server/tests/test_rf_convert.py`
**Interfaces:** Produces `packet_to_event(packet: dict, radio_id: str, now: float) -> MeshEvent | None` (source `"rf"`, `radio_id`, `snr=rxSnr`, `rssi=rxRssi`, `hops=max(0, hopStart-hopLimit)` se `hopStart`, `channel` = str(indice canale, 0 se assente), `gateway_id=None`; portnum per nome stringa: TEXT_MESSAGE_APP→text, POSITION_APP→position (da `decoded.position.latitude/longitude`, `precisionBits`; posizione 0/assente/fuori range → None), NODEINFO_APP→nodeinfo, TELEMETRY_APP→telemetry (solo `deviceMetrics`), altri → None; `decoded` assente (pacchetto cifrato non decifrabile dalla radio) → None) e `nodedb_to_events(nodes: dict, radio_id: str, now: float) -> list[MeshEvent]` (per ogni nodo del DB della radio: un nodeinfo se c'è `user`, una position se c'è posizione valida con `time` del nodo, una telemetry se c'è `deviceMetrics`; `rx_time` = `lastHeard` del nodo se presente altrimenti `now`; `packet_id` = 0).
- [ ] **Step 1: Test** con dict nel formato delle note (camelCase, solo campi presenti): testo con emoji → TextData invariato; posizione Milano con `precisionBits` 32 → lat/lon e precision 32; posizione 0,0 → None; nodeinfo con `hwModel:"HELTEC_V3"`, `role` assente → role `"CLIENT"`; telemetria senza deviceMetrics → None; pacchetto senza `decoded` → None; `hopStart` 3 `hopLimit` 1 → hops 2, `hopStart` assente → None; `nodedb_to_events` su 2 nodi (uno senza posizione) → 5 eventi attesi; chiavi `raw`/`payload` ignorate.
- [ ] **Step 2–4:** FAIL → implementare → PASS (`.venv/Scripts/python -m pytest server/tests/test_rf_convert.py -v`).
- [ ] **Step 5:** Commit — `feat: conversione pacchetti RF in MeshEvent`

### Task 3: Hub pubsub e RadioConnector
**Files:** Create `server/meshlens/pubsub_hub.py`, `server/meshlens/radio.py` · Test `server/tests/test_radio.py`
**Interfaces:**
- `PubSubHub(loop)` con `register(iface, connector)`, `unregister(iface)`, `start()` (si iscrive una volta a `meshtastic.receive`, `meshtastic.connection.lost`, `meshtastic.connection.established`, tiene riferimenti forti ai listener), smista via `loop.call_soon_threadsafe(connector.on_packet|on_lost|on_established, ...)`; pacchetti da interfacce non registrate ignorati. `pubsub_module` iniettabile per i test.
- `RadioConnector(cfg: dict, hub: PubSubHub, on_event: Callable[[MeshEvent], None], on_state: Callable[[dict], None], on_ack: Callable[[str, int, bool, str|None], None], iface_factory: Callable[[dict], Any], clock=time.time)` con `async start()`, `async stop()`, `state() -> dict` (Radio JSON senza `name/auto_connect`, che aggiunge il manager), `async send_text(text: str, channel_index: int, dest: str | None) -> int` (packet id; `dest` None = broadcast; `wantAck=True`), `on_packet(packet)`, `on_lost()`, `on_established()`.
- Comportamento: `start()` → stato `connecting`, crea l'interfaccia in thread; successo → `connected`, legge `my_node_id`, nome, canali (solo canali con ruolo diverso da DISABLED), emette `nodedb_to_events`; errore → `error` con messaggio italiano (`PermissionError`/"Access is denied"/"PermissionError(13" → "Porta in uso da un altro programma (chiudi l'app o la CLI Meshtastic)"; `FileNotFoundError`/"could not open port" → "Porta non trovata: radio scollegata?"; `BLEError device_not_found` → "Radio Bluetooth non trovata: è accesa e vicina?"; altro → "Errore di connessione: <tipo>") e poi `reconnecting` con backoff dai Global Constraints. `on_lost()` → `close()` in thread, `reconnecting`, nuovo tentativo. `stop()` interrompe il ciclo e chiude.
- ACK: pacchetti con `decoded.portnum == "ROUTING_APP"` e `decoded.requestId` tra gli id inviati → `on_ack(radio_id, id, ok, reason)` con `ok = errorReason in (None, "NONE")` e mittente diverso dal nodo locale (ack dal nodo locale = solo `sent`, non `acked`); id non confermati entro 60 s → `on_ack(..., False, "TIMEOUT")`. Per i broadcast nessun ack atteso: lo stato resta `sent`.
- [ ] **Step 1: Test** con `FakeIface` (attributi `nodes`, `myInfo.my_node_num`, `localNode.channels`, `sendText` che registra e restituisce un oggetto con `.id`, `close()` che registra) e un pubsub finto: connessione riuscita → stato `connected`, eventi nodedb emessi; factory che solleva `PermissionError` → stato `error` con testo "Porta in uso…" poi `reconnecting`; `on_lost` → `close()` chiamato e nuova creazione dopo il backoff (clock/sleep iniettati: nessuna attesa reale); pacchetto di un'altra interfaccia ignorato; `send_text` restituisce l'id e non blocca il loop (gira in thread); ack positivo, NAK `"NO_RESPONSE"`, ack dal nodo locale, timeout 60 s; `stop()` durante `reconnecting` termina subito.
- [ ] **Step 2–4:** FAIL → implementare → PASS.
- [ ] **Step 5:** Commit — `feat: connettore radio con riconnessione e conferme di consegna`

### Task 4: Ingestione RF, "sentito da" e messaggi in uscita
**Files:** Modify `server/meshlens/db.py`, `store.py`, `ingest.py` · Test `server/tests/test_ingest_rf.py`, `server/tests/test_store.py` (aggiunte)
**Interfaces:**
- DB: tabella `radios(id TEXT PK, name TEXT, kind TEXT, address TEXT, auto_connect INT DEFAULT 1, created REAL)`; colonne aggiunte a `messages` se mancanti (migrazione con `PRAGMA table_info` + `ALTER TABLE ADD COLUMN`): `direction TEXT DEFAULT 'in'`, `radio_id TEXT`, `channel_index INT`, `packet_id INT`, `status TEXT`. Colonna `heard_by TEXT` (JSON) in `nodes`.
- Store: `list_radios() -> list[dict]`, `save_radio(r: dict)`, `delete_radio(id)`, `update_message_status(key, status)`; `messages()` restituisce anche i campi nuovi (vedi contratto).
- Ingestor: per eventi `rf` aggiorna `node["heard_by"][radio_id] = {snr, rssi, hops, time}` (anche sui duplicati, per ogni radio); `sources` include `"rf"`; testo `rf` → messaggio con `direction "in"`, `radio_id`, `channel_index = int(ev.channel)` (per i diretti: `to` = id della radio locale); `record_outgoing(radio_id, my_node_id, packet_id, text, channel_index, to) -> dict` (crea, salva e pubblica il messaggio con `status "sent"` — o `"sending"` prima che arrivi l'id: vedi Task 5); `set_status(key, status)` (salva + chiama un nuovo callback `on_status(key, status)`); `mark_local_radio(node_num)` imposta `is_local_radio` e `is_mine`.
- [ ] **Step 1: Test:** stesso testo sentito da radio A (snr -5) e radio B (snr -9) e da MQTT → un solo messaggio, `heard_by` con A e B e valori di ciascuna; nodo RF in nazione non salvata → comunque persistito; migrazione su DB della fase 1 (creare le tabelle vecchie, poi `connect`) aggiunge le colonne senza perdere righe; `record_outgoing` salva `direction "out"` e chiave `out:<radio>:<id>`; `set_status` aggiorna il DB e chiama `on_status`; `messages()` restituisce i campi nuovi; radio locale marcata `is_mine`.
- [ ] **Step 2–4:** FAIL → implementare → PASS.
- [ ] **Step 5:** Commit — `feat: ingestione RF, sentito da e messaggi in uscita`

### Task 5: RadioManager, API e wiring
**Files:** Create `server/meshlens/radio_manager.py` · Modify `api.py`, `app.py` · Test `server/tests/test_radio_manager.py`, `server/tests/test_api_radios.py`
**Interfaces:**
- `RadioManager(store, ingestor, bus, loop, hub, connector_factory=RadioConnector, iface_factory=default_iface_factory, list_ports_fn=serial.tools.list_ports.comports, ble_scan_fn=default_ble_scan)` con `async start()` (connette le radio con `auto_connect`), `async stop()`, `radios() -> list[dict]` (Radio JSON), `async add(kind, address, name) -> dict` (rifiuta indirizzo già presente con `ValueError("Radio già aggiunta")`), `async remove(id)`, `async connect(id)`, `async disconnect(id)`, `ports() -> list[dict]` (Porta JSON), `async ble_scan() -> list[dict]` (timeout 12 s), `async send(id, text, channel_index, to) -> dict` (messaggio JSON). `default_iface_factory(cfg)` crea `SerialInterface(devPath=address)` o `BLEInterface(address)`.
- Invio: valida testo (vuoto → `ValueError("Messaggio vuoto")`; > 200 byte UTF-8 → `ValueError("Messaggio troppo lungo (max 200 byte)")`), radio non connessa → `ValueError("Radio non connessa")`; crea subito il messaggio con `status "sending"` e chiave provvisoria `out:<radio>:pending-<n>`, poi a `send_text` concluso lo sostituisce con la chiave definitiva e `status "sent"` (pubblicare entrambe le versioni via bus; il client sostituisce per chiave provvisoria → campo `"replaces": "<chiave provvisoria>"` nel secondo messaggio). Ack → `ingestor.set_status(key, "acked"|"failed")`.
- Ogni cambio di stato di un connettore → bus `{"type":"radios","radios":[...]}`; alla connessione `ingestor.mark_local_radio(my_node_num)`.
- API (tutte con PIN, `async def`): `GET /api/radios`; `POST /api/radios {"kind","address","name"}` (400 con messaggio); `DELETE /api/radios/{id}`; `POST /api/radios/{id}/connect`; `POST /api/radios/{id}/disconnect`; `GET /api/radios/ports`; `POST /api/radios/ble-scan`; `POST /api/radios/{id}/send {"text","channel_index":0,"to":null|"!hex"}` → 202 con messaggio JSON; 400 con messaggio italiano. `kind` diverso da usb/ble → 400.
- `app.py`: crea hub + manager in `build`, `start()` nel lifespan dopo MQTT, `stop()` prima di chiudere il DB.
- [ ] **Step 1: Test** con connettore finto: add/remove/duplicato; `ports()` marca `likely_meshtastic` e `in_use_by`; invio: vuoto/lungo/radio non connessa → 400; invio valido → 202 con `status "sending"`, poi bus riceve il messaggio definitivo con `replaces`; ack → `message_status`; stato connettore → bus `radios`; avvio app con una radio `auto_connect` nel DB la connette; arresto chiama `stop` di tutti i connettori.
- [ ] **Step 2–4:** FAIL → implementare → PASS; suite completa verde e senza avvisi.
- [ ] **Step 5:** Commit — `feat: gestore radio, API e avvio`

### Task 6: Interfaccia — pannello Radio
**Files:** Create `web/src/components/Radios.svelte` · Modify `web/src/lib/types.ts`, `api.ts`, `ws.ts`, `stores.svelte.ts`, `web/src/App.svelte`
- Nuova scheda **Radio** (mobile: barra in basso diventa Mappa / Nodi / Chat / Radio / Impostazioni; desktop: scheda nel pannello).
- Elenco radio con stato (pallino: verde connessa, giallo connessione/riconnessione, rosso errore, grigio scollegata), errore in italiano, nodo locale, pulsanti Connetti/Scollega/Rimuovi (rimozione con conferma).
- "Aggiungi radio": USB → elenco da `/api/radios/ports` (prima quelle probabili Meshtastic; quelle già in uso disabilitate) + nome; Bluetooth → pulsante "Cerca" (`/api/radios/ble-scan`, indicatore "ricerca in corso… ~10 s"), elenco trovate + nome; nota: "Se Windows chiede un PIN, inserisci quello mostrato sullo schermo della radio. Se la radio non viene trovata, abbinala prima da Impostazioni Windows → Bluetooth."
- Store: `radios` aggiornato da WS `radios`.
- [ ] **Step 1:** vitest per le funzioni pure aggiunte (ordinamento porte, classe colore dello stato).
- [ ] **Step 2:** `npm test`, `npm run check` (0/0), `npm run build`.
- [ ] **Step 3:** Commit — `feat(web): pannello radio`

### Task 7: Interfaccia — chat radio e "sentito da"
**Files:** Create `web/src/components/Chat.svelte`, `web/src/lib/chat.ts` (+ test) · Modify `MessageFeed.svelte` (diventa la vista "Pubblico (MQTT)" usata dentro Chat), `NodeDetail.svelte`, `MapView.svelte`, `App.svelte`
- Chat: selettore conversazione — per ogni radio connessa i suoi canali ("Heltec base · LongFast") e i messaggi diretti per nodo; più la vista "Pubblico (MQTT)" esistente. Messaggi raggruppati per conversazione con `chat.ts`: `conversationKey(msg, localIds: Set<string>) -> string` (`ch:<radio>:<index>` per canale, `dm:<radio>:<altro nodo>` per diretti in/out), test inclusi.
- Composer: textarea con contatore byte (max 200, avviso oltre), scelta radio di invio (default: la radio della conversazione), invio con Ctrl+Invio/pulsante; messaggi in uscita a destra con icona stato (⏳ in invio, ✓ inviato, ✓✓ consegnato, ⚠ non consegnato); sostituzione via `replaces`; aggiornamento via `message_status`.
- NodeDetail: sezione "Sentito da" (radio, SNR, RSSI, salti, tempo fa; "MQTT" con numero gateway); pulsante "Messaggio diretto" → apre Chat sulla conversazione `dm:` con la prima radio connessa.
- Mappa: colore del bordo per fonte (RF: bordo blu scuro; RF+MQTT: bordo doppio) senza cambiare il riempimento per età.
- [ ] **Step 1:** test vitest per `chat.ts` (conversazioni canale/diretto, ordinamento, contatore byte UTF-8 con emoji).
- [ ] **Step 2:** `npm test`, `npm run check`, `npm run build`. `git grep "@html" web/src` vuoto.
- [ ] **Step 3:** Commit — `feat(web): chat radio, stato consegna e sentito da`

### Task 8: Verifica con le radio reali (con l'utente)
- [ ] Heltec V3 via USB: aggiungi, connetti, nodi RF sulla mappa con "Sentito da"; invio su LongFast e messaggio diretto verso il T-Pager/T-Deck con ✓✓.
- [ ] Seconda radio via Bluetooth insieme alla USB; stesso messaggio ricevuto da entrambe → un solo messaggio, due voci in "Sentito da".
- [ ] Staccare il cavo USB → stato "riconnessione", riattaccare → torna "connessa" da sola; spegnere la radio BLE → idem.
- [ ] Porta occupata (app Meshtastic Desktop/CLI aperta sulla stessa porta) → messaggio "Porta in uso…".
- [ ] Dal telefono: chat e invio funzionano.
- [ ] Suite completa verde; `git tag fase2`.
