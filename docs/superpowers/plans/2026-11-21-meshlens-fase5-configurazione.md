# MeshLens Fase 5 — Configurazione dei nodi: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** leggere e modificare da MeshLens la configurazione sia delle radio collegate sia dei nodi remoti, questi con le chiavi admin PKI. Ogni modifica passa da un riepilogo delle differenze, una conferma esplicita e una copia di sicurezza ripristinabile. Nella scheda Copertura arrivano i pulsanti "Prepara le radio" e "Ripristina".

**Architettura:**
- `config_model.py`: funzioni pure per convertire protobuf ↔ dict, calcolare le differenze, classificare il rischio e mascherare i segreti.
- `RadioConnector`: guadagna le operazioni admin (lettura, scrittura in transazione, riavvio, posizione fissa). Girano in un thread e sotto lo stesso lock degli invii.
- `config_service.py`: orchestra le operazioni come "lavori" asincroni, perché le letture remote via LoRa richiedono decine di richieste. I lavori pubblicano l'avanzamento su WebSocket e salvano letture e copie nel database.
- Interfaccia: un pannello "Configura" con schede semplici in italiano più "Avanzate", generate da uno schema che il server ricava dai descrittori protobuf.

**Tecnologie:** quelle delle fasi precedenti; `google.protobuf.json_format` (già installato con `meshtastic`).

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md` (§6.5, §9 "Configurazione", §2 anti-obiettivi). Ricerca: `docs/superpowers/research/2026-11-21-admin-config.md` e `docs/superpowers/research/2026-11-20-meshtastic-python-api.md`.

## Global Constraints

- Testi in italiano.
- **Mai una modifica senza conferma esplicita** (anti-obiettivo della spec).
  - Ogni scrittura richiede un passo di anteprima (diff) e poi un passo di applicazione che porta lo stesso `preview_id`.
  - Una modifica **a rischio** richiede in più `confirm_risky: true`.
- **Copia di sicurezza obbligatoria:** prima di scrivere, si salva in `config_backups` la configurazione attuale delle sezioni toccate. Le copie non scadono. Il ripristino passa dallo stesso flusso di anteprima e conferma.
- **Modifiche a rischio** (possono isolare il nodo):
  - `lora.region`, `lora.modem_preset`, `lora.use_preset`, `lora.bandwidth`, `lora.spread_factor`, `lora.coding_rate`, `lora.channel_num`, `lora.override_frequency`, `lora.tx_enabled`, `lora.frequency_offset`;
  - qualsiasi campo del canale 0 (nome, psk, ruolo, precisione);
  - qualsiasi campo di `security`;
  - `bluetooth.enabled` portato a false su una radio collegata via Bluetooth;
  - `device.role` impostato a `REPEATER`;
  - `network.*` su una radio collegata via rete. Oggi non esistono radio di rete, ma la regola va tenuta.
- **Segreti mai mostrati né scritti nei log:**
  - `security.private_key`, `network.wifi_psk`, `module_config.mqtt.password`, `bluetooth.fixed_pin`;
  - le psk dei canali, salvo richiesta esplicita "Mostra chiave" per un canale (rotta dedicata).
  - Nei dict verso il client questi campi valgono `"••••"`. Un valore `"••••"` in ingresso significa "invariato".
- **Operazioni admin serializzate per radio:** usano il `_send_lock` del connettore, perché la libreria ha un solo `_acknowledgment` e un solo `_timeout` per interfaccia. Girano in un thread con `try/except BaseException`, perché la libreria chiama `sys.exit` e `print`. Ogni attesa remota ha un **timeout di 60 s** per richiesta. Non si usano mai i 300 s di default della libreria.
- **Una sola transazione per scrittura:** `beginSettingsTransaction`, poi le singole `writeConfig`/`writeChannel`/`setOwner`, poi `commitSettingsTransaction`. La radio si riavvia una volta sola. Dopo la scrittura locale si attende il riavvio, che la fase 2 gestisce con connessione persa e ristabilita. Poi si rilegge la configurazione e si segna il lavoro `verified` o `mismatch`.
- **Remoto:**
  - prima di scrivere si chiama `ensureSessionKey`; la chiave di sessione dura 300 s, quindi se la lettura ha più di 240 s se ne richiede una nuova;
  - gli errori di instradamento `ADMIN_PUBLIC_KEY_UNAUTHORIZED` (37) e `NOT_AUTHORIZED` (33) diventano "Il nodo non ha la chiave admin di questa radio: aggiungila seguendo la guida";
  - il timeout diventa "Nessuna risposta dal nodo entro 60 s".
- **Chiave admin:** la chiave pubblica della radio (`localConfig.security.public_key`, 32 byte) si mostra in base64, con una guida per inserirla nel campo "Admin key" del nodo da gestire. Il nodo remoto ha al massimo 3 slot.
- MeshLens non scrive mai la configurazione da solo: nessuna azione automatica.

## Contratti JSON

- **Config (dict):**
  ```
  {owner:{long_name, short_name, is_licensed},
   config:{device:{...}, position:{...}, power:{...}, network:{...}, display:{...},
           lora:{...}, bluetooth:{...}, security:{...}},
   module_config:{mqtt:{...}, telemetry:{...}, range_test:{...}, neighbor_info:{...}, ...},
   channels:[{index, role, name, psk, position_precision, uplink_enabled, downlink_enabled}]}
  ```
  - I nomi dei campi sono quelli del protobuf in snake_case. Gli enum sono stringhe (nomi), i bytes sono base64 e i segreti sono mascherati.
  - Si generano con `MessageToDict(preserving_proto_field_name=True, always_print_fields_with_no_presence=True)`.
- **Schema:** `GET /api/config/schema` restituisce `{config:{section:{field:{type:"bool"|"int"|"float"|"string"|"enum"|"bytes"|"repeated", enum?:[names], secret?:bool}}}, module_config:{...}, channel:{...}, owner:{...}}`, ricavato dai descrittori protobuf.
- **Lavoro:** `{id, node_id:"!hex", radio_id, kind:"read"|"apply"|"reboot"|"fixed_position", status:"running"|"done"|"failed", step:string, progress:[done,total], error:string|null, result_id:int|null, verify:"verified"|"mismatch"|null, started, ended}`.
  - WebSocket: `{"type":"config_job","job":{...}}` a ogni passo.
- **Lettura salvata:** `{id, node_id, radio_id, time, config:<Config>, sections:[nomi letti]}`.
- **Anteprima:** `{preview_id, node_id, radio_id, changes:[{path:"config.lora.hop_limit", old, new, risky:bool, reason:string|null}], risky:bool, backup_sections:[...]}`.
- **Copia:** `{id, node_id, time, reason:"before_apply"|"coverage_prepare"|"manual", label, sections:[...]}`. Il contenuto si ottiene con la rotta di dettaglio.
- **Rotte**, tutte con `require_auth`, quelle POST con JSON:
  - `GET /api/config/schema`;
  - `GET /api/radios/{id}/admin-key` → `{public_key_b64}`;
  - `POST /api/config/{node_id}/read` body `{radio_id?, sections?:[...]}` → 202 Lavoro. Senza `sections` legge tutto.
    - Per una radio locale la lettura è immediata dalla memoria, ma risponde lo stesso con un lavoro, che finisce subito.
    - Per un nodo remoto la radio di default è quella collegata che lo sente con meno hop.
  - `GET /api/config/{node_id}` → ultima Lettura salvata, oppure 404;
  - `POST /api/config/{node_id}/preview` body `{changes:{"config.lora.hop_limit":4, "channels.1.name":"prova", "owner.long_name":"..."}}` → Anteprima.
    - Risponde 409 "Leggi prima la configurazione" se l'ultima lettura delle sezioni toccate ha più di 10 minuti.
    - Le chiavi sono percorsi puntati; per i canali si usa `channels.<index>.<campo>`.
  - `POST /api/config/{node_id}/apply` body `{preview_id, confirm_risky?:bool}` → 202 Lavoro.
    - Errori: 400 se il `preview_id` è sconosciuto o scaduto (10 min); 400 "Conferma richiesta per modifiche a rischio".
  - `POST /api/config/{node_id}/reboot` body `{radio_id?, confirm:true}` → 202 Lavoro;
  - `POST /api/config/{node_id}/fixed-position` body `{lat, lon, alt?, confirm:true}`, oppure `{remove:true, confirm:true}` → 202 Lavoro;
  - `GET /api/config/{node_id}/backups` → `[Copia]`; `GET /api/config/backups/{id}` → Copia più `config`;
  - `POST /api/config/backups/{id}/preview-restore` → Anteprima, che si applica poi con `apply`;
  - `POST /api/config/{node_id}/channels/{index}/reveal-psk` → `{psk}` in base64;
  - `GET /api/config/jobs/{id}` → Lavoro.
- **Prova di copertura:**
  - `POST /api/coverage/prepare` body `{radio_id, mobile_id, interval_s:30, private_channel:bool}` → `{plan_id, steps:[{node_id, preview:<Anteprima>}]}`. L'ordine degli step è il mobile prima e la base dopo.
  - `POST /api/coverage/prepare/{plan_id}/apply` body `{confirm_risky?:bool}` → 202 `{jobs:[...]}`. I lavori si eseguono in sequenza: il mobile prima e la base dopo.
  - `POST /api/coverage/restore` body `{plan_id}` → stessa forma di `prepare`, con le Anteprime che rimettono le copie salvate dal prepare. L'ordine resta mobile prima e base dopo, perché la base deve raggiungere il mobile sul canale ancora attivo.
  - `GET /api/coverage/prepare/last` → l'ultimo piano applicato e non ripristinato, oppure null.

## Review Focus

1. **Nodo remoto senza la nostra chiave admin:** la lettura deve fallire in pochi secondi con il messaggio sulla chiave e un link alla guida. Non deve restare `running` per 300 s né far cadere il server (SystemExit).
2. **Riavvio dopo una scrittura locale:** la connessione cade e si ristabilisce, oppure la porta USB cambia. Il lavoro passa a `verified` o `mismatch` dopo la rilettura, e non resta appeso se la radio non torna entro 90 s (`failed` con "La radio non è tornata dopo il riavvio").
3. **Segreti:** `private_key`, wifi psk, password MQTT, PIN Bluetooth e psk dei canali non compaiono mai in risposte, messaggi WebSocket o log. Riscrivere una sezione che contiene un segreto mascherato non lo cancella.
4. **Anteprima vecchia o già applicata:** applicare due volte lo stesso `preview_id`, oppure dopo 10 minuti, viene rifiutato. Una lettura più recente cambiata nel frattempo invalida l'anteprima.
5. **"Prepara le radio" a metà:** se il mobile riesce e la base fallisce, lo stato resta chiaro ("Mobile preparato, base no") e "Ripristina" rimette solo ciò che è stato cambiato.

---

### Task 1: Server, modello della configurazione (funzioni pure) e tabelle

**File:**
- Crea: `server/meshlens/config_model.py`
- Modifica: `server/meshlens/db.py`, `server/meshlens/store.py`
- Test: `server/tests/test_config_model.py`, `server/tests/test_store.py`

**Interfacce prodotte:**
- `node_to_dict(local_config, module_config, channels, owner: dict) -> dict`: costruisce il Config del contratto con i segreti mascherati. Gli argomenti sono i protobuf `LocalConfig` e `LocalModuleConfig`, più la lista dei `Channel`.
- `schema() -> dict`: lo Schema del contratto, ricavato dai descrittori.
- `parse_changes(changes: dict[str, object], schema) -> list[tuple[str, object]]`: valida percorsi e tipi (enum per nome, int, bool, float, stringa, bytes in base64); in caso di errore solleva `ValueError` con un messaggio in italiano.
- `diff(current: dict, changes: list[tuple[str, object]], context: dict) -> list[dict]`:
  - ignora i valori uguali e quelli mascherati;
  - marca `risky` e `reason` secondo le regole delle Global Constraints;
  - `context` contiene `{radio_kind:"usb"|"ble"|None, is_local:bool}`, che serve per la regola sul Bluetooth.
- `apply_to_protos(protos, changes)`: applica i cambi a copie dei protobuf. I segreti mascherati restano quelli attuali.
- `touched_sections(changes) -> list[str]`: per esempio `["config.lora", "channels.1", "owner"]`.
- Schema del database:
  - `config_reads(id, node_num, radio_id, time, sections TEXT, data TEXT)`;
  - `config_backups(id, node_num, time, reason, label, sections TEXT, data TEXT)`;
  - `config_jobs(id, node_num, radio_id, kind, status, step, done, total, error, result_id, verify, started, ended)`.
  - Nessuna di queste tabelle scade.
- `Store`: CRUD minimo per le tre tabelle, cioè `add_read`, `last_read(node_num)`, `add_backup`, `backups(node_num)`, `get_backup`, `add_job`, `update_job` e `get_job`.
  - I `data` salvati contengono i segreti **non mascherati** solo nelle copie, perché servono a ripristinare.
  - I segreti non escono mai da `GET /backups/{id}`, che maschera.

- [ ] **Step 1: Test che falliscono**
  - `test_node_to_dict_masks_secrets`: `security.private_key`, `network.wifi_psk`, `bluetooth.fixed_pin` e la psk del canale valgono `"••••"`; `security.public_key` resta in base64 visibile.
  - `test_schema_has_enum_names`: `config.lora.modem_preset.enum` contiene `"LONG_FAST"`; `config.device.role.enum` contiene `"CLIENT"`.
  - `test_parse_changes_validates`:
    - percorso sconosciuto → `ValueError`;
    - `"config.lora.hop_limit": "x"` → `ValueError`;
    - un nome di enum valido viene accettato;
    - `"channels.9.name"` → `ValueError` (indici 0–7).
  - `test_diff_marks_risky`:
    - `lora.modem_preset` → risky;
    - `channels.0.name` → risky;
    - `channels.1.name` → non risky;
    - `bluetooth.enabled` false con `radio_kind` "ble" e locale → risky; con "usb" → no;
    - un valore uguale non compare nel diff.
  - `test_apply_keeps_masked_secret`: un cambio a `network.wifi_ssid` con `wifi_psk` mascherato lascia invariata la psk originale nel protobuf.
  - `test_store_config_tables_roundtrip`.
- [ ] **Step 2: Esegui** `.venv/Scripts/python -m pytest server/tests -q`. Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): modello configurazione, diff, rischio, segreti, tabelle`.

### Task 2: Server, operazioni admin nel connettore radio

**File:**
- Modifica: `server/meshlens/radio.py`
- Test: `server/tests/test_radio.py`, con FakeIface e FakeNode estesi

**Interfacce:**
- Usa: `node_to_dict`, `apply_to_protos` (Task 1).
- Produce (metodi async di `RadioConnector`, tutti sotto `_send_lock`, ciascuno con una chiamata in thread protetta da `BaseException`):
  - `admin_public_key() -> str | None`, in base64;
  - `read_local() -> dict` (Config dalla memoria di `localNode`);
  - `read_remote(node_num: int, sections: list[str] | None, on_step) -> dict`:
    - prima `getNode(node_id, requestChannels=True, timeout=60)`, poi `requestConfig(...)` per sezione;
    - `iface._timeout` va impostato a 60 durante l'operazione e poi ripristinato;
    - `on_step(step_text, done, total)` informa del progresso;
    - solleva `AdminError(code, message)` con i codici `"unauthorized"`, `"timeout"` e `"error"`. Il caso unauthorized si riconosce da un pacchetto ROUTING con `errorReason` 33 o 37 per la nostra richiesta, oppure da `receivedNak` sull'acknowledgment.
  - `write(node_num: int | None, protos_changed: dict, on_step) -> None`:
    - `node_num` None significa locale;
    - esegue begin, le scritture per sezione e il commit;
    - per il remoto chiama `ensureSessionKey` prima e attende ack/nak con `iface._acknowledgment.reset()` e poi `waitForAckNak` (60 s) dopo il commit;
    - errori come `AdminError`.
  - `reboot(node_num: int | None, secs: int = 5)`;
  - `set_fixed_position(node_num, lat: float, lon: float, alt: int = 0)` e `remove_fixed_position(node_num)`, con float in gradi;
  - `wait_reconnected(timeout: float = 90) -> bool`: attende lo stato `connected` dopo un riavvio locale.
- I protobuf modificati si ottengono così: locale → `localNode.localConfig`, `localNode.moduleConfig`, `localNode.channels`; remoto → l'oggetto `Node` restituito da `getNode`, dopo la lettura.

- [ ] **Step 1: Test che falliscono**, con un FakeNode che registra le chiamate:
  - `test_read_local_returns_masked_dict`.
  - `test_read_remote_unauthorized_fails_fast` (Review Focus 1): il FakeNode simula un ROUTING con `errorReason` 37 → `AdminError("unauthorized")` in meno di 1 s di tempo finto, e `SystemExit` dentro la libreria viene catturato.
  - `test_read_remote_timeout`.
  - `test_write_uses_single_transaction`: l'ordine delle chiamate è begin, `writeConfig("lora")`, `writeChannel(1)`, `setOwner`, commit.
  - `test_write_remote_calls_ensure_session_key`.
  - `test_admin_ops_hold_send_lock`: durante un `write` un `send_text` concorrente attende.
  - `test_wait_reconnected_times_out` (Review Focus 2).
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): operazioni admin locali e remote nel connettore`.

### Task 3: Server, servizio di configurazione, lavori e rotte

**File:**
- Crea: `server/meshlens/config_service.py`
- Modifica: `server/meshlens/api.py`, `server/meshlens/app.py`, `server/meshlens/radio_manager.py` (accesso al connettore per id e scelta della radio, come nel traceroute)
- Test: `server/tests/test_config_service.py`, `server/tests/test_api_config.py`

**Interfacce:**
- Usa: i Task 1 e 2.
- Produce: `ConfigService(store, radios, live, bus, clock)`, con i metodi
  - `start_read(node_id, radio_id, sections) -> job`;
  - `preview(node_id, changes) -> dict`;
  - `apply(preview_id, confirm_risky) -> job`;
  - `reboot(...)`;
  - `fixed_position(...)`;
  - `preview_restore(backup_id)`;
  - `reveal_psk(node_id, index)`.
- I lavori girano come task asyncio, uno alla volta per radio. Pubblicano `config_job` a ogni passo e restano salvati in `config_jobs`.
- Flusso di `apply`:
  1. controlla `preview_id` (esistente, non usato, non più vecchio di 10 min, lettura di base non superata da una più recente) — Review Focus 4;
  2. salva la copia delle sezioni toccate con `reason="before_apply"`, ricavata dai protobuf attuali (non dal dict mascherato);
  3. scrive;
  4. in locale attende la riconnessione, oppure fallisce dopo 90 s;
  5. rilegge le sezioni toccate e confronta: `verify` vale `verified` o `mismatch`;
  6. salva la nuova lettura.
- Le anteprime vivono in memoria, scadono dopo 10 min e sono monouso.
- Rotte del contratto, con gli errori in italiano.

- [ ] **Step 1: Test che falliscono**, con un connettore finto:
  - `test_read_job_local_finishes_and_saves_read`.
  - `test_read_job_remote_progress_published`: ci sono messaggi `config_job` con `progress` crescente.
  - `test_preview_requires_fresh_read`: 409 dopo 10 min.
  - `test_apply_requires_confirm_risky`.
  - `test_apply_creates_backup_then_writes_then_verifies`.
  - `test_preview_single_use_and_expiry` (Review Focus 4).
  - `test_restore_preview_from_backup`: il diff riporta i valori della copia.
  - `test_secrets_never_in_responses` (Review Focus 3): grep su tutte le risposte e su tutti i messaggi del bus di un flusso completo → nessuna occorrenza dei valori segreti finti.
  - `test_local_reboot_not_back_fails_after_90s` (Review Focus 2).
  - `test_admin_key_route`.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): servizio configurazione con anteprima, copie e lavori`.

### Task 4: Server, "Prepara le radio" e "Ripristina" per la copertura

**File:**
- Modifica: `server/meshlens/coverage.py` (funzioni pure del piano), `server/meshlens/config_service.py`, `server/meshlens/api.py`
- Test: `server/tests/test_coverage_prepare.py`

**Interfacce:**
- Usa: `ConfigService.preview/apply`, `config_backups`.
- Produce la funzione pura `prepare_changes(role: "mobile"|"base", interval_s: int, private_channel: dict | None) -> dict[path, value]`:
  - **mobile:**
    - `module_config.range_test.enabled=true`, `module_config.range_test.sender=interval_s`;
    - `config.position.position_broadcast_secs=interval_s`, `config.position.position_broadcast_smart_enabled=true`, `config.position.broadcast_smart_minimum_interval_secs=interval_s`;
    - `config.position.gps_mode="ENABLED"`.
  - **base:** `module_config.range_test.enabled=true`, `module_config.range_test.sender=0`.
  - **con `private_channel`:** su entrambe `channels.0.name`, `channels.0.psk` (la stessa per le due, 32 byte casuali generati una volta per piano) e `channels.0.position_precision=32`.
  - Il canale privato temporaneo diventa il primario, quindi la modifica è a rischio e va confermata. L'interfaccia avvisa che durante la prova le due radio sono isolate dalla rete pubblica.
- Piani in memoria e nel database. Si aggiunge la tabella `coverage_prepare(id, radio_id, mobile_num, created, applied, restored, steps TEXT)`, che salva gli id delle copie per nodo.
- Esecuzione in sequenza: prima il mobile (remoto tramite la radio di base, oppure locale se il mobile è collegato a MeshLens), poi la base.
  - Se il primo passo fallisce, il secondo non parte.
  - Lo stato per nodo viene salvato (Review Focus 5).
- `restore` costruisce le anteprime dalle copie dei soli nodi effettivamente modificati, sempre nell'ordine mobile → base.

- [ ] **Step 1: Test che falliscono**
  - `test_prepare_changes_mobile_and_base`: valori esatti come sopra.
  - `test_private_channel_same_psk_both_and_risky`.
  - `test_prepare_order_mobile_first_and_stop_on_failure` (Review Focus 5).
  - `test_restore_only_changed_nodes`.
  - `test_prepare_last_route`.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): prepara e ripristina radio per la prova di copertura`.

### Task 5: Interfaccia, pannello "Configura"

**File:**
- Crea: `web/src/components/ConfigPanel.svelte`, `web/src/components/ConfigDiff.svelte`, `web/src/components/ConfigAdvanced.svelte`, `web/src/lib/config.ts`, `web/src/lib/config.test.ts`
- Modifica: `web/src/lib/types.ts`, `web/src/lib/api.ts`, `web/src/lib/stores.svelte.ts`, `web/src/lib/ws.ts`, `web/src/components/NodeDetail.svelte` (pulsante "Configura"), `web/src/components/Radios.svelte` (pulsante "Configura" e "Chiave admin" per ogni radio collegata)

**Interfacce:**
- Usa: i contratti JSON.
- Produce:
  - tipi `ConfigDict`, `ConfigSchema`, `ConfigJob`, `ConfigPreview`, `ConfigBackup`;
  - funzioni API per tutte le rotte `/api/config/*`;
  - store `configJobs` (SvelteMap da id a Lavoro), aggiornato dal WS;
  - in `config.ts`:
    - `formChanges(original: ConfigDict, edited: ConfigDict) -> Record<string, unknown>`: solo i percorsi cambiati, mai i segreti mascherati invariati;
    - `SIMPLE_TABS`: la definizione delle schede semplici, cioè etichette italiane e campi;
    - `fieldInput(schemaField)`: il tipo di controllo da usare.

**Comportamento:**
- Il pannello si apre da NodeDetail o da Radio e mostra il nodo e la radio usata (con una scelta se ce n'è più di una).
- Pulsante **"Leggi configurazione"**:
  - avanzamento in diretta, per esempio "Lettura LoRa (3/25)…";
  - in caso d'errore mostra il messaggio; per la chiave mancante ci sono un link "Come aggiungere la chiave admin" e la chiave della radio copiabile;
  - mostra l'età dell'ultima lettura salvata.
- **Schede semplici** (`SIMPLE_TABS`), con etichette italiane, spiegazioni brevi e valori enum tradotti per i più comuni:
  - **Generale:** `owner.long_name`, `owner.short_name`, `config.device.role`;
  - **Posizione:** `gps_mode`, `position_broadcast_secs`, smart attivo e intervallo minimo, posizione fissa (imposta da mappa o coordinate, oppure rimuovi);
  - **Telemetria:** `module_config.telemetry.device_update_interval`, `environment_update_interval`;
  - **LoRa:** `region`, `use_preset`, `modem_preset`, `hop_limit`, `tx_power`, `tx_enabled`;
  - **Canali:** 8 righe con ruolo, nome, precisione della posizione, uplink e downlink, la psk mascherata con "Mostra" e "Genera nuova" (32 byte casuali, a rischio sul canale 0);
  - **Moduli:** Range Test (`enabled`, `sender`, `save`), NeighborInfo (`enabled`, `update_interval`, `transmit_over_lora`).
- **Avanzate:** tutte le altre sezioni e campi generati dallo schema (checkbox, numero, testo, select per gli enum), raggruppati per sezione e ripiegabili. I segreti si possono solo sostituire, mai leggere.
- **"Rivedi modifiche"** chiama `preview` e mostra ConfigDiff:
  - tabella con campo (etichetta italiana se nota, altrimenti il percorso), valore attuale e nuovo valore;
  - le righe a rischio sono evidenziate in rosso con il motivo;
  - se ci sono modifiche a rischio, compare la casella obbligatoria "Ho capito che questa modifica può isolare il nodo";
  - il pulsante "Applica" porta all'avanzamento del lavoro e all'esito ("Applicato e verificato", "Applicato ma la verifica non coincide", errore).
- **Copie:** elenco con data e motivo; "Ripristina" porta all'anteprima di ripristino e poi allo stesso flusso.
- **Riavvia nodo:** con conferma.
- **Chiave admin della radio:** testo base64 con il pulsante "Copia" e una guida in 3 passi:
  1. aprire l'app Meshtastic sul nodo da gestire;
  2. Sicurezza → Admin key: incollare la chiave;
  3. salvare.

- [ ] **Step 1: Test vitest che falliscono** in `config.test.ts`:
  - `formChanges` riporta solo il campo cambiato;
  - ignora `"••••"` invariato;
  - riporta la psk sostituita;
  - gestisce `channels.<i>.<campo>`;
  - `fieldInput` restituisce select per enum e checkbox per bool;
  - ogni campo di `SIMPLE_TABS` esiste in uno schema di esempio.
- [ ] **Step 2: Esegui** `cd web; npx vitest run`. Atteso: falliscono.
- [ ] **Step 3: Implementa.** Nessun `$effect` deve leggere e scrivere lo stesso `$state`.
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): pannello Configura con schede, avanzate, diff e copie`.

### Task 6: Interfaccia, "Prepara le radio" e "Ripristina" nella Copertura

**File:**
- Modifica: `web/src/components/CoverageSetup.svelte`, `web/src/components/Coverage.svelte`, `web/src/lib/api.ts`, `web/src/lib/types.ts`
- Usa: `ConfigDiff.svelte` (Task 5), le rotte `/api/coverage/prepare*` e `/api/coverage/restore`.

**Comportamento:**
- Nella guida della nuova prova c'è il pulsante **"Prepara le radio"**, con una casella "Usa un canale privato temporaneo a precisione piena (le due radio saranno isolate dalla rete pubblica durante la prova)", spenta di default.
- Il pulsante mostra le due anteprime (mobile, base) con ConfigDiff e la conferma per le modifiche a rischio, poi "Applica". L'avanzamento dei due lavori compare in sequenza, con l'esito per nodo.
- Se esiste un piano applicato e non ripristinato (`GET /api/coverage/prepare/last`), nella scheda Copertura e alla fine di ogni prova compare il riquadro "Radio preparate per la prova: Ripristina configurazione", che porta alle anteprime di ripristino e poi all'applicazione.
- Errori parziali: "Mobile preparato, base no: riprova o ripristina" (Review Focus 5).

- [ ] **Step 1:** test vitest per la funzione pura `prepareStatus(plan)`, che produce il testo di stato per nodo dagli esiti dei lavori.
- [ ] **Step 2: Esegui vitest.** Atteso: fallisce.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): prepara e ripristina radio dalla Copertura`.

### Task 7: Prova con le radio vere (rimandata alla fine di tutte le fasi, scelta dell'utente)

- [ ] Leggi e modifica la configurazione dell'Heltec via USB, per esempio `hop_limit`: anteprima, conferma, riavvio, "verificato".
- [ ] Prova un nodo remoto senza la chiave admin: messaggio rapido. Poi aggiungi la chiave dall'app, leggi e modifica.
- [ ] Ripristina una copia.
- [ ] Usa "Prepara le radio" con e senza canale privato, fai una prova breve e poi "Ripristina".

---

**Esecuzione in parallelo:** i Task 1→4 (server) e 5→6 (interfaccia, in un worktree) si parlano solo tramite i contratti JSON. Ramo `fase5`, creato da `fase4`.
