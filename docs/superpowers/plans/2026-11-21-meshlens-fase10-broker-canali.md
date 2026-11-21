# MeshLens Fase 10 — Più broker MQTT, canali personalizzati, favicon: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** ascoltare più broker MQTT insieme (il predefinito mqtt.meshtastic.org diventa il primo, disattivabile ma non eliminabile), con canali personalizzati legati a ogni broker (a mano, dalla radio collegata o da un link `https://meshtastic.org/e/#…`), invio dal composer sul broker scelto, stato per broker e il logo di MeshLens come favicon.

**Architettura:**
- **Impostazioni:** nuova chiave `mqtt_brokers` (lista di broker, ognuno con i suoi `channels` e `extra_keys`). La vecchia chiave `mqtt` resta come **vista di compatibilità** del broker predefinito: si legge sempre, e se viene scritta (vecchi client, vecchie esportazioni) aggiorna il broker predefinito. Una migrazione all'avvio scrive `mqtt_brokers` dal vecchio `mqtt`. Password, PSK dei canali e chiavi extra sono cifrate con DPAPI e mascherate come nella fase 9.
- **Runtime:** `connectors: dict[id, MqttConnector]`, uno per broker attivo, ognuno con il suo `EnvelopeDecoder` (chiavi del broker + chiavi imparate da quel broker). Al cambio delle impostazioni si riavviano solo i broker con parametri di connessione cambiati; se cambiano solo le chiavi si aggiorna il decoder senza ricollegarsi. Watchdog e ritentativi per broker. Lo stato è il totale (stessi campi di oggi) più `brokers: [...]`.
- **Eventi:** `MeshEvent.broker` (id del broker, facoltativo) arriva fino al messaggio salvato (colonna nuova `messages.broker`, schema 3) e al feed. La deduplica per (from, packet_id) resta unica tra tutte le fonti.
- **Invio:** `POST /api/mqtt/send` accetta `broker`; radice del topic, cifratura (accesa/spenta), limite di frequenza e conferma della prima volta sono per broker.
- **Interfaccia:** componenti nuovi `web/src/components/settings/Brokers.svelte`, `web/src/lib/shell/BrokerPicker.svelte`, `web/src/lib/ui/BrokerBadge.svelte` e funzioni pure in `web/src/lib/brokers.ts`, per limitare i conflitti con la fase 11 (in parallelo su `Settings.svelte`, `App.svelte`, `TopBar.svelte`). `TopBar.svelte` e `App.svelte` **non** si toccano.

**Tech Stack:** Python 3 + FastAPI, sqlite3, paho-mqtt (`tls_set_context` con `ssl.create_default_context()`), protobuf `meshtastic.protobuf.apponly_pb2.ChannelSet`, ctypes (DPAPI, già in `secretbox.py`); Svelte 5 + Vite + vitest; Pillow (già nell'extra `tray`) solo per generare una volta le icone.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md`. Requisiti e **decisioni dell'utente (vincolanti)**: `docs/superpowers/research/2026-11-21-canali-custom-e-piu-broker.md`. Le Global Constraints della fase 8 (`docs/superpowers/plans/2026-11-21-meshlens-fase8-design-invio.md`) e della fase 9 (`docs/superpowers/plans/2026-11-21-meshlens-fase9-fondamenta.md`) restano valide.

## Global Constraints

- Valgono tutte le Global Constraints delle fasi 8 e 9 (italiano, `Intl` `it-IT`, token di colore, ≥ 14 px e ≥ 44 px su telefono, nessuna risorsa esterna, regole Svelte 5, connessione SQLite principale solo dal loop, nessun blocco lungo del loop, messaggi di commit in italiano `feat(server): …` / `feat(web): …`).
- **Nessuna dipendenza nuova** in `pyproject.toml` né in `web/package.json`. Nessun cambio di versione.
- **Contratti JSON solo additivi:** `GET /api/settings` continua a contenere `mqtt` (vista del broker predefinito); `/api/mqtt/status`, `/api/status` e il WS `status.mqtt` mantengono tutti i campi attuali (ora totali su tutti i broker) e aggiungono `brokers`; `/api/mqtt/send` senza `broker` usa il primo broker attivo; l'esportazione resta `"format": 1`.
- **Broker predefinito:** id fisso `"default"`, nome `"mqtt.meshtastic.org (predefinito)"`; si può disattivare e modificare, **non eliminare**. Dopo la migrazione ha **Crittografia accesa** e TLS spento. Un broker nuovo parte con **Crittografia spenta e TLS spento**.
- **Crittografia spenta** = il testo si pubblica in chiaro (MeshPacket `decoded`); accesa = cifrato con la PSK del canale. In ricezione si decodificano sempre sia i cifrati sia i pacchetti in chiaro.
- **Limiti:** `MAX_BROKERS = 8`; `MAX_BROKER_CHANNELS = 16` per broker; nome del canale da 1 a 11 byte UTF-8, senza `/ # +`, unico nel broker; PSK base64 accettata da `expand_psk` (0, 1, 16 o 32 byte); nome del broker da 1 a 40 caratteri; id `^[a-z0-9-]{1,24}$`, assegnato dal server se manca.
- **Segreti:** password dei broker, PSK dei canali e voci di `extra_keys` non escono mai in chiaro da API (salvo la rotta esplicita "mostra PSK"), esportazione predefinita, pacchetto diagnostico o log; nel database sono cifrati con il protector di `secretbox` (DPAPI su Windows). Maschera `MASK = "••••"`; i riferimenti `"••••#n"` indicano la n-esima voce salvata.
- **Invio MQTT (fase 8) invariato nel resto:** solo `TEXT_MESSAGE_APP`, 200 byte, un messaggio ogni 10 s e 30 all'ora **per broker**, conferma della prima volta **per broker** con il testo `f"Il messaggio sarà pubblico sul broker {host} e potrà essere ritrasmesso via radio dai gateway"` (per mqtt.meshtastic.org è identico al testo di oggi).
- **Fase 11 in parallelo:** in `Settings.svelte` si cambia solo la scheda MQTT (campi del broker sostituiti da `<Brokers>`) e la funzione `save`; `Chat.svelte` e `MessageFeed.svelte` ricevono solo poche righe; niente modifiche a `App.svelte` e `TopBar.svelte`.
- I test esistenti restano verdi (oggi 657 pytest e tutti i vitest), aggiornando solo quelli che usano `rt.connector` o il costruttore di `MqttSender`. Comandi: `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q` dalla radice del worktree; `cd web && npx vitest run`.

## Contratti JSON (aggiunte)

- Impostazioni:
  - `mqtt_brokers: [{id, name, enabled, host, port, tls, encryption, username, password, topics: [str], channels: [{name, psk}], extra_keys: [str]}]` (in uscita `password`, ogni `psk` e ogni voce di `extra_keys` mascherati).
  - `mqtt_send_confirmed_brokers: [id]` (conferma della prima volta già data, per broker; `mqtt_send_confirmed: true` resta valida per `"default"`).
  - In `PUT /api/settings` e nell'importazione: se c'è `mqtt_brokers`, `mqtt` viene ignorato; se c'è solo `mqtt`, aggiorna il broker predefinito.
- `GET /api/mqtt/status` (e `/api/status`, WS `status.mqtt`): campi attuali come **totali** + `brokers: [{id, name, enabled, host, tls, encryption, connected, msgs_per_s, undecodable, connected_since, last_msg_age_s, reconnects, watchdog_restarts, last_error, last_error_at, decoded, drops, queue_dropped, queue_size}]` (anche i disattivati, con `connected: false` e contatori a 0).
- `POST /api/mqtt/send` aggiunge `broker: str | null`; nuovo errore `400 unknown_broker`.
- `GET /api/mqtt/channels?broker=<id>` (facoltativo): righe `{name, count_1h, enabled, custom: bool, brokers: [id]}`; i canali personalizzati compaiono sempre, anche con 0 messaggi.
- `POST /api/mqtt/brokers/{id}/channels/import-link` `{url}` e `POST /api/mqtt/brokers/{id}/channels/import-radio` `{radio_id}` → `{settings: <mascherate>, added: [nome], skipped: [{name, reason}]}`.
- `POST /api/mqtt/brokers/{id}/channels/{index}/reveal` → `{psk}`, **solo da loopback** (403 dalla rete locale, come l'esportazione con segreti).
- Messaggi (REST e WS): campo nuovo `broker: str | null`.

## Review Focus

1. **Aggiornamento da una versione con un solo broker personalizzato** (host, utente, password, `extra_keys` e `mqtt_send_confirmed: true` già salvati): dopo l'avvio il broker `"default"` ha gli stessi valori, la password si decifra, Crittografia accesa, nessuna nuova richiesta di conferma; un secondo avvio non rifà la migrazione. → Task 1.
2. **Salvataggio con segreti mascherati**: password `MASK`, PSK `"••••#n"`, un canale rinominato e uno in mezzo eliminato → nessuna PSK persa o scambiata tra canali o broker; un riferimento senza corrispondenza dà 400 e non salva nulla. → Task 1 (e `fromServer` del Task 7).
3. **Un broker irraggiungibile o con TLS sbagliato** (porta 8883 con certificato non valido) non blocca gli altri né il loop: errore leggibile solo su quel broker; il watchdog riavvia solo quel connettore. → Task 3 e Task 4.
4. **Invio su un canale personalizzato appena aggiunto**, senza traffico precedente: con Crittografia accesa il pacchetto è cifrato con quella PSK e il nostro decoder lo rilegge; con Crittografia spenta esce `decoded`; il broker scelto non connesso → 503 senza consumare il limite di frequenza degli altri broker. → Task 5.
5. **Lo stesso pacchetto da due broker** (stesso gateway): un solo messaggio nel feed, `mqtt_gateways` non gonfiato, il messaggio porta l'id del primo broker che l'ha consegnato. → Task 2.

---

### Task 1: Impostazioni — broker multipli, migrazione, segreti  _(modello: opus)_

**Files:**
- Modify: `server/meshlens/settings.py`, `server/meshlens/api.py` (solo `put_settings` e `import_settings`), `server/meshlens/app.py` (solo la chiamata a `migrate_brokers` in `build()`)
- Test: `server/tests/test_brokers_settings.py` (nuovo), `server/tests/test_settings.py`, `server/tests/test_api.py`

**Interfaces:**
- Produces (in `settings.py`):
  - Costanti: `DEFAULT_BROKER_ID = "default"`, `DEFAULT_BROKER_NAME = "mqtt.meshtastic.org (predefinito)"`, `MAX_BROKERS = 8`, `MAX_BROKER_CHANNELS = 16`, `MAX_CHANNEL_NAME_BYTES = 11`, `BROKER_KEYS = ("id", "name", "enabled", "host", "port", "tls", "encryption", "username", "password", "topics", "channels", "extra_keys")`, `CONNECT_KEYS = ("host", "port", "tls", "username", "password", "topics")`.
  - `default_broker(mqtt: dict | None = None) -> dict` — dal vecchio oggetto `mqtt` (fuso con `DEFAULTS["mqtt"]`): `id="default"`, nome predefinito, `enabled=True`, `tls=False`, **`encryption=True`**, `channels=[]`, `extra_keys` del vecchio oggetto.
  - `DEFAULTS["mqtt_brokers"] = [default_broker()]`, `DEFAULTS["mqtt_send_confirmed_brokers"] = []`; `DEFAULTS["mqtt"]` resta.
  - `find_broker(settings: dict, broker_id: str) -> dict | None`; `enabled_brokers(settings: dict) -> list[dict]` (nell'ordine della lista).
  - `mqtt_view(brokers: list[dict]) -> dict` — `{host, port, username, password, topics, extra_keys}` del broker `"default"`.
  - Validazione `_validate_brokers(value) -> None` (modifica la lista sul posto): completa le voci con `enabled=True, tls=False, encryption=False, port=1883, username="", password="", channels=[], extra_keys=[]`; assegna `id = "b" + secrets.token_hex(3)` a chi non lo ha; normalizza i topic con `normalize_topic`; errori (testi esatti): `"Il broker predefinito non si può eliminare: puoi disattivarlo"`, `f"Al massimo {MAX_BROKERS} broker"`, `f"Broker {name}: indica almeno un topic"`, `f"Broker {name}: host vuoto"`, `f"Broker {name}: porta non valida"`, `f"Broker {name}: al massimo {MAX_BROKER_CHANNELS} canali"`, `f"Canale {nome}: il nome deve avere da 1 a 11 caratteri"`, `f"Canale {nome}: il nome non può contenere / # +"`, `f"Canale {nome}: nome già usato in questo broker"`, `f"Canale {nome}: chiave PSK non valida ({e})"`; id duplicati o non conformi → errore; chiavi sconosciute nel broker o nel canale → errore.
  - `load_settings`: se la riga `mqtt_brokers` esiste la usa (decifrando `password`, ogni `psk` e ogni `extra_keys`), altrimenti `[default_broker(<mqtt salvato>)]`; poi `result["mqtt"] = mqtt_view(...)`.
  - `save_settings`: se `mqtt_brokers` è tra le modifiche, `mqtt` è ignorato; se c'è solo `mqtt`, diventa `mqtt_brokers` con il broker `"default"` aggiornato (`{**default, **mqtt}`). I segreti dei broker si cifrano prima di scrivere; la riga `mqtt` non si scrive più.
  - `migrate_brokers(conn) -> bool` — se manca la riga `mqtt_brokers`: la scrive (cifrata) dal vecchio `mqtt` e cancella la riga `mqtt`; ritorna `True` solo se ha migrato. `migrate_secrets` cifra anche i segreti in chiaro dentro `mqtt_brokers`.
  - `_DECRYPT_CACHE_MAX = 256` (ora i segreti sono molti).
  - `mask_secrets` maschera anche `password`, ogni `psk` ed ogni voce `extra_keys` di ogni broker.
  - `resolve_broker_secrets(new: list, existing: list) -> list` — per broker con lo stesso id: `password == MASK` → quella salvata; `psk == MASK` → quella del canale salvato con lo stesso nome; `psk == "••••#n"` → quella dell'n-esimo canale salvato di quel broker; `extra_keys` con `resolve_extra_keys`. Broker nuovo (id assente o sconosciuto) con un valore mascherato, o riferimento fuori intervallo → `ValueError("Chiave mascherata senza corrispondenza: reinseriscila")`.
  - `prepare_import(data: dict, current: dict | None = None) -> tuple[dict, list[str]]` — come oggi; in più: se c'è `mqtt_brokers` si toglie `mqtt`; si toglie `mqtt_send_confirmed_brokers` (in `skipped`); i segreti mascherati si risolvono contro `current["mqtt_brokers"]`; quelli senza corrispondenza diventano `""` (password) o fanno scartare il canale, e finiscono in `skipped` come `f"mqtt_brokers.{id}.password"` / `f"mqtt_brokers.{id}.channels.{nome}"`.
  - `put_settings` chiama `resolve_broker_secrets(changes["mqtt_brokers"], load_settings(conn)["mqtt_brokers"])` (400 su `ValueError`); `import_settings` passa `load_settings(ctx.conn)` a `prepare_import`; `build()` chiama `migrate_brokers(conn)` subito dopo `migrate_secrets` e scrive `log.info("Impostazioni MQTT migrate a più broker")` se ha migrato.

- [ ] **Step 1: test che falliscono** (`test_brokers_settings.py`, con il protector finto dei test di `test_secretbox.py`):
  - `test_fresh_install_has_default_broker`: `load_settings` su database vuoto → un broker, `id == "default"`, `encryption is True`, `tls is False`, `mqtt["host"] == "mqtt.meshtastic.org"`.
  - `test_migrate_legacy_mqtt` (Review Focus 1): riga `mqtt` con host `"mio.example"`, password `"segreta"`, `extra_keys: ["AQ=="]` e riga `mqtt_send_confirmed: true` → `migrate_brokers` ritorna `True`; il broker `"default"` ha quei valori, `encryption is True`; la riga grezza `mqtt_brokers` non contiene `"segreta"`; la riga `mqtt` non esiste più; seconda chiamata → `False`; `load_settings()["mqtt"]["host"] == "mio.example"`.
  - `test_put_legacy_mqtt_updates_default_broker`: `save_settings(conn, {"mqtt": {"host": "altro.example"}})` → `mqtt_brokers[0]["host"] == "altro.example"`, gli altri broker invariati.
  - `test_brokers_take_precedence_over_mqtt`: modifiche con entrambe le chiavi → vale `mqtt_brokers`.
  - `test_new_broker_defaults_and_id`: voce `{name, host, topics}` → `enabled True`, `tls False`, `encryption False`, `port 1883`, `id` conforme a `^b[0-9a-f]{6}$`.
  - `test_cannot_delete_default_broker`, `test_max_brokers`, `test_channel_name_rules` (12 byte, `"a/b"`, duplicato → `ValueError` coi testi sopra; `"Città"` di 6 byte → ok), `test_bad_psk_rejected`, `test_empty_topics_rejected`.
  - `test_secrets_masked_and_encrypted`: password, due PSK ed una extra key → `mask_secrets` li rende `MASK`; nessuno compare in chiaro nella riga grezza del database.
  - `test_resolve_masked_secrets` (Review Focus 2): canali salvati `[A:k1, B:k2, C:k3]`; nuova lista `[A:"••••#0", C2:"••••#2"]` (B eliminato, C rinominato) → `[A:k1, C2:k3]`; password `MASK` → quella salvata; `"••••#7"` → `ValueError`; broker senza id con `MASK` → `ValueError`.
  - `test_prepare_import_resolves_and_skips`: esportazione mascherata reimportata sullo stesso database → segreti invariati; reimportata su database vuoto → `skipped` contiene `mqtt_brokers.default.password`.
  - `test_api.py`: `test_put_settings_brokers_masked_roundtrip` (GET → PUT dello stesso corpo → i segreti salvati non cambiano; risposta mascherata); `test_put_settings_bad_mask_400_and_nothing_saved`.
- [ ] **Step 2:** `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q server/tests/test_brokers_settings.py` → FAIL.
- [ ] **Step 3:** implementare come sopra.
- [ ] **Step 4:** stesso comando → PASS; poi suite intera verde (i test esistenti su `mqtt` passano grazie alla vista di compatibilità).
- [ ] **Step 5: Commit** `feat(server): impostazioni con più broker MQTT, migrazione e segreti cifrati`.

### Task 2: Origine dei messaggi — `MeshEvent.broker`, schema 3, conteggi per broker  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/events.py`, `server/meshlens/db.py`, `server/meshlens/store.py`, `server/meshlens/ingest.py`, `server/meshlens/dedup.py`
- Test: `server/tests/test_db.py`, `server/tests/test_ingest.py`, `server/tests/test_dedup.py`, `server/tests/test_store.py`

**Interfaces:**
- Produces:
  - `MeshEvent.broker: str | None = None` (ultimo campo, con default: i costruttori esistenti non cambiano).
  - `SCHEMA_VERSION = 3`; migrazione 3 = colonna `messages.broker TEXT` (anche in `SCHEMA` per i database nuovi; `_add_missing_columns` la rende idempotente). Il backup "pre-migrazione" della fase 9 scatta da solo.
  - Messaggi: `_build_message` aggiunge `"broker": ev.broker`; `record_outgoing_mqtt(from_num, to_num, packet_id, text, channel, now=None, broker: str | None = None)` aggiunge `"broker": broker`; `record_outgoing` (radio) `"broker": None`; `Store.add_message` salva `broker`; `Store.messages` lo restituisce già (`m.*`).
  - `Ingestor._note_mqtt_channel(name, t, broker: str | None)`: contatori per `(broker or "", name)`; `Ingestor.mqtt_channel_counts(now=None, broker: str | None = None) -> dict[str, int]` (`None` = somma su tutti i broker, firma compatibile); `Ingestor.mqtt_channel_brokers(now=None) -> dict[str, list[str]]` (canale → broker che l'hanno visto nell'ultima ora).
  - `Deduplicator.note_gateway(from_node: int, packet_id: int, gateway: str) -> bool` — `True` se quel gateway non era ancora stato visto per quel pacchetto (insieme di gateway nella voce della chiave; sparisce con la chiave in `prune`). In `Ingestor.handle`, ramo MQTT duplicato: se `ev.gateway_id` e `not dedup.note_gateway(...)` → `return` senza incrementare `mqtt_gateways`; il primo arrivo MQTT chiama anch'esso `note_gateway`.

- [ ] **Step 1: test che falliscono:**
  - `test_migration_3_adds_broker_column` (`test_db.py`): database con `user_version` 2 → dopo `connect` versione 3, colonna presente, righe intatte; `test_indexes_exist` e gli altri invariati.
  - `test_message_carries_broker` (`test_ingest.py`): evento testo con `broker="b1a2b3c"` → il messaggio pubblicato e quello salvato hanno `broker == "b1a2b3c"`; `record_outgoing_mqtt(..., broker="default")` idem.
  - `test_same_packet_two_brokers_one_message` (Review Focus 5): stesso (from, id), stesso `gateway_id`, broker `"default"` poi `"b1"` → un solo messaggio con `broker == "default"`; `mqtt_gateways == 1`; terzo arrivo da un gateway diverso → `mqtt_gateways == 2`.
  - `test_note_gateway` (`test_dedup.py`): primo `True`, stesso gateway `False`, altro gateway `True`; dopo `prune` oltre la finestra la chiave è dimenticata.
  - `test_channel_counts_per_broker`: 2 eventi `LongFast` da `"default"` e 1 da `"b1"` → `mqtt_channel_counts() == {"LongFast": 3}`, `mqtt_channel_counts(broker="b1") == {"LongFast": 1}`, `mqtt_channel_brokers()["LongFast"] == ["default", "b1"]` (ordine di primo arrivo).
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** suite intera → PASS.
- [ ] **Step 5: Commit** `feat(server): origine del broker nei messaggi e conteggi dei canali per broker`.

### Task 3: Decoder e connettore per broker — chiavi del broker, TLS  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/mqtt_decode.py`, `server/meshlens/mqtt_client.py`
- Test: `server/tests/test_mqtt_decode.py`, `server/tests/test_mqtt_client.py`

**Interfaces:**
- Consumes: `MeshEvent.broker` (Task 2); forma del broker (Task 1).
- Produces:
  - `EnvelopeDecoder(keys: list[bytes], channel_keys: dict[str, bytes] | None = None, broker: str | None = None)`; ogni evento prodotto ha `broker=self.broker`. `channel_keys` iniziali = quelle date (canali personalizzati). Prima del giro su tutte le chiavi si prova la chiave di `channel_keys[channel_id]` se presente.
  - `EnvelopeDecoder.set_keys(keys: list[bytes], custom: dict[str, bytes]) -> None` — sostituisce `self.keys` con un'unica assegnazione (il thread paho legge la lista vecchia o la nuova, mai una a metà) e fa `self.channel_keys = {**self.channel_keys, **custom}` (le personalizzate vincono sulle imparate).
  - `MqttConnector`: `cfg` è un broker di `mqtt_brokers`. Se `cfg.get("tls")`: `client.tls_set_context(ssl.create_default_context())` prima di `connect_async`. `self.label = cfg.get("name") or cfg.get("host")` usato in ogni riga di log (`"MQTT %s: connesso a %s:%s"` ecc.). Registra `client.on_connect_fail` → `set_error("Connessione non riuscita: controlla host, porta e TLS")`. Un `ssl.SSLError` o `OSError` sincrono in `connect_async` → `"Broker non raggiungibile: …"` come oggi. Costruttore invariato (i `FakeConnector` dei test non cambiano).

- [ ] **Step 1: test che falliscono:**
  - `test_custom_channel_key_decodes_and_preloads`: pacchetto cifrato con una PSK di 32 byte sul canale `"Squadra"`; decoder con `channel_keys={"Squadra": k}` e `keys=[DEFAULT_KEY, k]` → evento testo; `channel_keys["Squadra"] == k` prima ancora del primo pacchetto.
  - `test_decoded_packet_has_broker`: pacchetto `decoded` (in chiaro) con decoder `broker="b1"` → evento con `broker == "b1"`.
  - `test_set_keys_keeps_learned_and_custom_wins`: chiave imparata per `"A"` e `"B"`; `set_keys(..., {"A": k2})` → `channel_keys == {"A": k2, "B": <imparata>}`.
  - `test_tls_context_set_only_when_enabled` (`FakeClient` che registra `tls_set_context`): `tls=True` → chiamato una volta prima di `connect_async`; `tls=False` → mai.
  - `test_connect_fail_sets_error`: invocare `on_connect_fail` → `status()["last_error"]` col testo sopra; nessuna password nel testo (cfg con password `"segreta"`).
  - `test_log_lines_use_broker_label` (`caplog`): connessione riuscita → la riga contiene il nome del broker.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** pytest → PASS.
- [ ] **Step 5: Commit** `feat(server): decoder con le chiavi del broker e TLS facoltativo per il connettore`.

### Task 4: Runtime con più connettori, stato totale e per broker  _(modello: opus)_

**Files:**
- Modify: `server/meshlens/app.py`, `server/meshlens/diagnostics.py`
- Test: `server/tests/test_app.py`, `server/tests/test_diagnostics.py`, `server/tests/test_api.py`

**Interfaces:**
- Consumes: `enabled_brokers`, `find_broker`, `CONNECT_KEYS` (Task 1); `EnvelopeDecoder(keys, channel_keys, broker)`, `set_keys` (Task 3).
- Produces (in `app.py`):
  - `broker_keys(broker: dict) -> tuple[list[bytes], dict[str, bytes]]` — `[DEFAULT_KEY] + PSK dei canali + extra_keys` (espanse, senza vuoti né doppioni) e `{nome: chiave}` dei canali personalizzati.
  - `Runtime.connectors: dict[str, object]` sostituisce `connector`; `Runtime.learned_keys: dict[str, dict[str, bytes]]` (broker → canale → chiave); `Runtime.watchdog_restarts: dict[str, int]`; `Runtime._last_start_attempt: dict[str, float]`; `_connector_lock` resta unico.
  - `Runtime.start_connector(broker: dict) -> None` (decoder con `broker_keys` + `learned_keys[id]`, poi le personalizzate sopra); `Runtime.start_connectors() -> None` (tutti gli attivi; l'errore di uno non ferma gli altri, `log.exception` e si prosegue).
  - `Runtime._retire_connector(broker_id: str) -> None` (async; salva le chiavi imparate in `learned_keys[broker_id]`, `stop` in thread, accumula `queue_dropped_retired`).
  - `Runtime.restart_connector(broker_id: str, reason: str) -> None` (async, sotto lock; incrementa `watchdog_restarts[broker_id]`).
  - `Runtime._on_settings_changed(saved)`: per ogni broker → disattivato o rimosso: ritirato; attivo senza connettore: avviato; connettore con `CONNECT_KEYS` diversi: ritirato e riavviato; solo chiavi diverse: `decoder.set_keys(*broker_keys(b))` senza ricollegarsi; resto (nome, crittografia): `connector.cfg = b` e nient'altro. Le chiavi imparate di un broker rimosso si dimenticano.
  - `Runtime.mqtt_watchdog()`: la regola di oggi applicata a ogni connettore; per ogni broker attivo senza connettore il ritentativo al massimo ogni `MQTT_RETRY_START_S`, per broker.
  - `Runtime.mqtt_status() -> dict` — `brokers` con una voce per ogni broker delle impostazioni (campi del contratto: `status()` del connettore se c'è, altrimenti il dizionario di riserva di oggi; più `id, name, enabled, host, tls, encryption, watchdog_restarts`). Totali: `connected` = almeno un attivo connesso; somma di `msgs_per_s`, `undecodable`, `decoded`, `reconnects`, `queue_size`, `queue_dropped` (+ ritirati), di ogni voce di `drops` e di `watchdog_restarts`; `connected_since` = il più vecchio tra i connessi; `last_msg_age_s` = il minimo; `last_error`/`last_error_at` = l'errore più recente, con prefisso `f"{nome}: "` se i broker attivi sono più di uno; `filtered_channel` come oggi.
  - Fino al Task 5 `ctx.mqtt_sender` resta con la firma di oggi, puntato al broker `"default"` (`lambda: rt.connectors.get("default")`, chiavi dal suo decoder): il Task 5 lo passa alla firma per broker.
  - `Runtime.stop` ferma tutti i connettori.
  - `diagnostics._scrub_mqtt(info, settings)`: toglie utente e password di **tutti** i broker da `last_error` totale e da quello di ogni voce di `brokers`.

- [ ] **Step 1: test che falliscono** (`test_app.py`, `FakeConnector` invariato):
  - Aggiornare i test che usano `rt.connector` a `rt.connectors["default"]` (stesso significato).
  - `test_one_connector_per_enabled_broker`: due broker attivi e uno disattivato → due `FakeConnector` avviati, `cfg["id"]` corrispondenti.
  - `test_settings_change_restarts_only_changed_broker`: cambio dell'host di `"b1"` → solo il connettore di `"b1"` fermato e ricreato; quello di `"default"` è lo stesso oggetto.
  - `test_channel_change_updates_keys_without_reconnect`: aggiungere un canale a `"b1"` → stesso connettore, il suo decoder ha la chiave nuova in `channel_keys`.
  - `test_disable_and_remove_broker_stops_connector`.
  - `test_failed_start_of_one_broker_keeps_others` (Review Focus 3): factory che solleva solo per `"b1"` → `"default"` avviato; dopo `MQTT_RETRY_START_S` (monotonic finto) il watchdog ritenta solo `"b1"`.
  - `test_watchdog_restarts_only_silent_broker`: `"b1"` connesso e muto da 301 s, `"default"` attivo → solo `"b1"` riavviato; `mqtt_status()["brokers"]` di `"b1"` ha `watchdog_restarts == 1`, totale 1.
  - `test_learned_keys_survive_restart_per_broker`: chiave imparata dal decoder di `"b1"` → dopo il riavvio è nel nuovo decoder di `"b1"`, non in quello di `"default"`.
  - `test_status_totals_and_brokers`: due connettori finti con `msgs_per_s` 1.0 e 2.5, uno non connesso con `last_error` → totale `msgs_per_s == 3.5`, `connected is True`, `last_error` inizia col nome del broker; `brokers` ha 3 voci (incluso il disattivato con `connected False`); tutti i campi del contratto della fase 9 presenti nel totale.
  - `test_bundle_scrubs_all_broker_credentials` (`test_diagnostics.py`): password `"pw-b1"` di un secondo broker presente nel `last_error` di quel broker → assente dallo zip.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** suite intera → PASS.
- [ ] **Step 5: Commit** `feat(server): un connettore per ogni broker attivo, stato totale e per broker`.

- [ ] **Extra (dalla revisione finale della fase 9):** `Runtime.stop()` deve interrompere il controllo d'integrità ancora in corso (`conn.interrupt()` sulla connessione di `check_integrity`), così chiudere l'app o aggiornare non resta bloccato durante `quick_check` su un database grande. Test con un controllo finto lento.

### Task 5: Invio sul broker scelto, crittografia per broker, canali nel composer  _(modello: opus)_

**Files:**
- Modify: `server/meshlens/mqtt_publish.py`, `server/meshlens/api.py` (`MqttSendBody`, `mqtt_send`, `mqtt_channels`), `server/meshlens/app.py` (costruzione di `ctx.mqtt_sender`: `lambda bid: rt.connectors.get(bid)` e `key_for=lambda bid, ch:` `channel_keys` del decoder di `bid`, altrimenti `rt.learned_keys.get(bid, {}).get(ch)`)
- Test: `server/tests/test_mqtt_publish.py`, `server/tests/test_api.py`

**Interfaces:**
- Consumes: `find_broker`, `enabled_brokers` (Task 1); `record_outgoing_mqtt(..., broker=)`, `mqtt_channel_counts(broker=)`, `mqtt_channel_brokers()` (Task 2); getter del Task 4.
- Produces:
  - `confirm_text(host: str) -> str` (testo delle Global Constraints); `CONFIRM_TEXT = confirm_text("mqtt.meshtastic.org")` resta.
  - `build_envelope(text, from_num, to_num, channel_name, key, packet_id, gateway_id, encrypted: bool = True) -> bytes` — con `encrypted=False` oppure `key == b""`: `packet.decoded = data` (niente `encrypted`); `channel = channel_hash(channel_name, key)` in entrambi i casi.
  - `MqttSender(get_connector: Callable[[str], object | None], get_settings, get_radios, clock, record, key_for: Callable[[str, str], bytes | None] = lambda broker, channel: None)`.
  - `MqttSender.send(text, channel, to, confirm_public, broker: str | None = None) -> dict`. Ordine dei controlli: testo, canale, destinatario come oggi → broker (`None` = primo attivo; assente o disattivato → `MqttSendError(400, "unknown_broker", "Broker non trovato o disattivato")`) → conferma: già data se `id in mqtt_send_confirmed_brokers` o (`id == "default"` e `mqtt_send_confirmed`), altrimenti `409 confirm_required` con `confirm_text(broker["host"])` → chiave: canale personalizzato del broker (`expand_psk(psk)`), poi `key_for(id, canale)`, poi `DEFAULT_KEY` per i preset, altrimenti `400 unknown_channel_key` con `f"Non conosco la chiave del canale {canale} su {nome}: aggiungilo ai canali del broker in Impostazioni"` → nodo proprio → connettore del broker (`None` → 503) → limite di frequenza **del broker** (`_sent: dict[str, deque]`) → radice da `root_from_topics(broker["topics"])` → `build_envelope(..., encrypted=broker["encryption"])` → `record(..., broker=id)`.
  - API: `MqttSendBody.broker: str | None = Field(None, max_length=24)`; dopo un invio riuscito con `confirm_public`: aggiunge l'id a `mqtt_send_confirmed_brokers` (e per `"default"` anche `mqtt_send_confirmed: true`).
  - `GET /api/mqtt/channels?broker=<id>`: righe dai conteggi (di quel broker se dato) **più** i canali personalizzati (di quel broker, o di tutti senza parametro) con `count_1h` 0 se non visti; `custom` vero per questi; `brokers` da `mqtt_channel_brokers()` unito ai broker che hanno il canale personalizzato. Broker sconosciuto → 404.

- [ ] **Step 1: test che falliscono** (`make_sender` aggiornato a `lambda bid: conn` e `key_for` a due argomenti; i test esistenti restano con lo stesso significato sul broker `"default"`):
  - `test_send_on_custom_channel_without_traffic` (Review Focus 4): broker `"b1"` con canale `Squadra` (PSK 32 byte) e crittografia accesa → pubblicato su `"<radice di b1>/2/e/Squadra/!a1b2c3d4"`; `EnvelopeDecoder([DEFAULT_KEY, k])` rilegge il testo; `record` riceve `broker="b1"`.
  - `test_encryption_off_publishes_decoded`: broker con `encryption: False` → l'envelope ha `packet.decoded.payload == b"ciao"` e nessun `encrypted`; il decoder lo legge comunque.
  - `test_default_broker_still_encrypted`: broker `"default"` migrato → pacchetto cifrato (come oggi).
  - `test_unknown_or_disabled_broker_400`.
  - `test_rate_limit_is_per_broker`: invio su `"default"`, subito dopo su `"b1"` → entrambi ok; secondo su `"default"` entro 10 s → 429.
  - `test_disconnected_broker_does_not_consume_other_limits`: `get_connector("b1")` → `None` → 503; poi invio su `"default"` ok.
  - `test_confirmation_per_broker`: `mqtt_send_confirmed: true` → `"default"` non chiede conferma, `"b1"` sì, con `confirm_text("<host di b1>")`.
  - `test_root_from_selected_broker_topics`: `"b1"` con topic `msh/US/#` → argomento che inizia con `msh/US/2/e/`.
  - `test_api.py`: `test_send_route_with_broker_and_confirmation_saved` (dopo `confirm_public` su `"b1"`, `mqtt_send_confirmed_brokers == ["b1"]`); `test_channels_route_includes_custom_with_zero_count` (`?broker=b1` → riga `Squadra` con `count_1h 0`, `custom True`; `?broker=nessuno` → 404).
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** suite intera → PASS.
- [ ] **Step 5: Commit** `feat(server): invio MQTT sul broker scelto, con o senza crittografia, e canali personalizzati`.

### Task 6: Importazione dei canali — link meshtastic.org e radio collegata, "mostra PSK"  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/channel_link.py`
- Modify: `server/meshlens/settings.py` (`merge_channels`), `server/meshlens/config_service.py` (`channel_secrets`), `server/meshlens/api.py` (tre rotte)
- Test: `server/tests/test_channel_link.py` (nuovo), `server/tests/test_config_service.py`, `server/tests/test_api.py`

**Interfaces:**
- Consumes: `find_broker`, `save_settings`, `mask_secrets`, `PRESET_CHANNELS` (`mqtt_publish.py`), `ConfigService._connector`/`current_protos`.
- Produces:
  - `preset_name(modem_preset: int) -> str` (`LONG_FAST` → `"LongFast"`, come `_camel` di `radio.py`).
  - `parse_channel_url(url: str) -> list[dict]` — accetta `https://meshtastic.org/e/#<b64url>` e le varianti con `?add=true` prima o dentro il frammento; base64url con o senza `=`; `apponly_pb2.ChannelSet`; per ogni `settings`: `{"name": nome, "psk": base64 standard di psk}`, il primo senza nome prende `preset_name(lora_config.modem_preset)`. Errori `ValueError("Link non valido: usa un link https://meshtastic.org/e/#…")` / `ValueError("Il link non contiene canali")`.
  - `settings.merge_channels(broker: dict, entries: list[dict]) -> tuple[list[str], list[dict]]` — aggiunge in coda; salta con motivo: `"già presente"` (stesso nome), `"canale pubblico predefinito"` (nome tra i preset e chiave espansa uguale a `DEFAULT_KEY`), `"nome troppo lungo"`, `"chiave non valida"`, `"limite di 16 canali"`.
  - `ConfigService.channel_secrets(radio_id: str) -> list[dict]` (async) — canali non `DISABLED` del nodo locale della radio da `current_protos(None)`: `{"name", "psk"}` con lo stesso nome del primario di `read_channels`; radio non collegata → `ConfigError(409, "Radio non collegata")`.
  - Rotte (auth + JSON): `POST /api/mqtt/brokers/{id}/channels/import-link` `{url}`; `POST /api/mqtt/brokers/{id}/channels/import-radio` `{radio_id}` → `merge_channels` sul broker salvato, `save_settings`, `on_settings_changed`, risposta del contratto; broker sconosciuto → 404; `ValueError` → 400. `POST /api/mqtt/brokers/{id}/channels/{index}/reveal` → `{psk}` solo da loopback, 403 dalla rete locale (404 se fuori intervallo). Nessuna PSK nei log.

- [ ] **Step 1: test che falliscono:**
  - `test_parse_link_roundtrip`: costruire un `ChannelSet` con primario senza nome (`LONG_FAST`, psk `b"\x01"`) e secondario `"Squadra"` (32 byte), serializzarlo in base64url senza `=` → `parse_channel_url("https://meshtastic.org/e/#" + s)` == `[{"name": "LongFast", "psk": "AQ=="}, {"name": "Squadra", "psk": <b64>}]`; stessa cosa con `"https://meshtastic.org/e/?add=true#" + s` e con `"…#" + s + "?add=true"`.
  - `test_parse_link_rejects_garbage`: `"https://example.com/e/#abc"`, `"https://meshtastic.org/e/#!!!"`, `ChannelSet` vuoto → `ValueError` coi testi sopra.
  - `test_merge_channels_reasons`: preset `LongFast`/`AQ==` saltato come `"canale pubblico predefinito"`; doppione `"già presente"`; diciassettesimo `"limite di 16 canali"`.
  - `test_channel_secrets_from_local_radio` (`test_config_service.py`, con il connettore finto esistente): primario senza nome → nome del preset; canale disattivato escluso.
  - `test_api.py`: `test_import_link_route_saves_and_masks` (risposta con `added == ["Squadra"]`, `psk` mascherata; il decoder del broker ha la chiave dopo `on_settings_changed`); `test_import_radio_route_409_without_radio`; `test_reveal_psk_route` (200 con la PSK in chiaro; indice 99 → 404; broker sconosciuto → 404; da IP non loopback → 403).
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** pytest → PASS.
- [ ] **Step 5: Commit** `feat(server): importazione dei canali da link meshtastic.org e dalla radio collegata`.

### Task 7: Interfaccia — sezione "Broker MQTT" nelle Impostazioni  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/brokers.ts`, `web/src/lib/brokers.test.ts`, `web/src/components/settings/Brokers.svelte`
- Modify: `web/src/lib/settings.ts` (tipi), `web/src/lib/types.ts` (tipi di stato), `web/src/lib/api.ts` (tre chiamate), `web/src/components/Settings.svelte` (solo scheda MQTT e `save`)

**Interfaces:**
- Consumes: contratti dei Task 1, 4, 6.
- Produces:
  - Tipi (`settings.ts`): `BrokerChannel {name: string; psk: string}`; `Broker {id?: string; name; enabled; host; port; tls; encryption; username; password; topics: string[]; channels: BrokerChannel[]; extra_keys: string[]}`; `AppSettings.mqtt_brokers?: Broker[]`, `AppSettings.mqtt_send_confirmed_brokers?: string[]`. (`types.ts`): `BrokerStatus extends MqttStatus {id; name; enabled; host; tls; encryption}`; `MqttStatus.brokers?: BrokerStatus[]`; `Message.broker?: string | null`.
  - `brokers.ts`: `DEFAULT_BROKER_ID = 'default'`; `MAX_CHANNEL_BYTES = 11`; `newBroker(): Broker` (nome `'Nuovo broker'`, porta 1883, topic `['msh/EU_868/#']`, `enabled: true`, `tls: false`, `encryption: false`, senza `id`); `fromServer(list: Broker[]): Broker[]` (PSK `'••••'` → `'••••#i'`, `extra_keys` con `maskedKeyLines`); `channelNameError(name: string, others: string[]): string | null` («Il nome deve avere da 1 a 11 caratteri», «Il nome non può contenere / # +», «Esiste già un canale con questo nome»; lunghezza in byte UTF-8); `pskError(psk: string): string | null` («La chiave deve essere in base64 e lunga 1, 16 o 32 byte»; `'••••#n'` valida); `portFor(tls: boolean, port: number): number` (1883 ↔ 8883, altre porte invariate); `isChannelLink(text: string): boolean`; `pickBroker(current: string, list: BrokerStatus[]): string`; `brokerLabel(id: string | null | undefined, list: BrokerStatus[] | undefined): string | null` (nome solo se nell'elenco ci sono almeno due broker attivi).
  - `api.ts`: `importChannelLink(brokerId, url)`, `importChannelsFromRadio(brokerId, radioId)`, `revealChannelPsk(brokerId, index)`.
  - `Brokers.svelte` — props `{ brokers: Broker[] (bindable), dirty: boolean, onimported: (s: AppSettings) => void }`; **nessun elemento `<form>`** (vive dentro il modulo principale; i suoi pulsanti sono `type="button"`). Per ogni broker una Card: riga di stato (pallino + msg/s da `app.status.mqtt.brokers`), Nome, `Switch` "Attivo", Host, Porta, `Switch` "TLS" (applica `portFor`), `Switch` "Crittografia" con nota «Spenta: i messaggi inviati escono in chiaro. Accesa: sono cifrati con la chiave del canale.», Utente, Password, Topic (uno per riga), Chiavi aggiuntive (come oggi), elenco Canali (nome, PSK in `type="password"` con pulsante occhio: per le PSK salvate chiama `revealChannelPsk`; "Elimina"), "Aggiungi canale" (nome + PSK con `channelNameError`/`pskError`), "Importa dalla radio" (Select delle radio collegate da `app.radios`), "Incolla link" (campo + `isChannelLink`), "Elimina broker" (assente per `default`; Modal di conferma). Import disattivati con nota «Salva prima le modifiche» se `dirty` o se il broker non ha ancora `id`; esito «Aggiunti: …; saltati: … (motivo)». "Aggiungi broker" (disattivato a 8).
  - `Settings.svelte`: lo stato `host, port, username, password, topics, keys` sparisce; `brokers = $state<Broker[]>([])` con istantanea JSON per `dirty`; `apply` fa `brokers = fromServer(s.mqtt_brokers ?? [])`; `save` invia `mqtt_brokers: brokers` al posto di `mqtt`; nella scheda MQTT restano `MqttStatusDetail` (totale) e "Il tuo id nodo", con `<Brokers bind:brokers {dirty} onimported={…} />` al posto dei campi. Il pulsante Salva si disattiva se `channelNameError`/`pskError` segnalano errori.

- [ ] **Step 1: test che falliscono** (`brokers.test.ts`):
  - `fromServer`: canali `[{psk:'••••'},{psk:'••••'}]` → `'••••#0'`, `'••••#1'`; PSK non mascherata invariata.
  - `channelNameError('Squadra', [])` → `null`; `'ÀÀÀÀÀÀ'` (12 byte) → messaggio di lunghezza; `'a/b'` → messaggio dei caratteri; doppione → messaggio del duplicato; `''` → lunghezza.
  - `pskError('AQ==')`, `pskError(<base64 di 32 byte>)`, `pskError('••••#3')` → `null`; `pskError('abc')`, `pskError(<base64 di 8 byte>)` → messaggio.
  - `portFor(true, 1883) === 8883`, `portFor(false, 8883) === 1883`, `portFor(true, 1999) === 1999`.
  - `isChannelLink('https://meshtastic.org/e/#CgM')` vero; `'https://example.com/#x'` falso.
  - `pickBroker`: corrente attivo → resta; corrente disattivato → primo attivo connesso, poi primo attivo; nessuno → `''`.
  - `brokerLabel('b1', [default, b1 attivi])` → nome di b1; con un solo attivo → `null`; id sconosciuto o `null` → `null`.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/brokers.test.ts` → FAIL.
- [ ] **Step 3:** implementare `brokers.ts`, tipi, `api.ts`, `Brokers.svelte`, modifiche a `Settings.svelte`.
- [ ] **Step 4:** `cd web && npx vitest run` e `npm run check` → PASS, 0 errori.
- [ ] **Step 5: Commit** `feat(web): broker MQTT e canali personalizzati nelle Impostazioni`.

### Task 8: Interfaccia — scelta del broker nel composer  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/shell/BrokerPicker.svelte`
- Modify: `web/src/lib/send.ts`, `web/src/lib/send.test.ts`, `web/src/lib/api.ts` (`mqttChannels`), `web/src/components/Chat.svelte`

**Interfaces:**
- Consumes: `pickBroker`, `brokerLabel`, `BrokerStatus` (Task 7); `POST /api/mqtt/send` con `broker`, `GET /api/mqtt/channels?broker=` (Task 5).
- Produces:
  - `api.ts`: `mqttChannels(broker?: string)` → `'/mqtt/channels' + (broker ? '?broker=' + encodeURIComponent(broker) : '')`; tipo di riga con `custom?: boolean; brokers?: string[]`.
  - `send.ts`: `MqttSendBody.broker?: string`; `mqttBody(text, channel, to, confirmPublic, broker?: string)` (aggiunge `broker` solo se non vuoto); `mqttChannelNames(rows)` mette per primi i canali con `custom`, poi LongFast, poi gli altri; `classifyMqttError` per `confirm_required` restituisce `e.message` del server (o `PUBLIC_WARNING` se vuoto), così la conferma nomina il broker giusto.
  - `BrokerPicker.svelte` — props `{ id: string; brokers: BrokerStatus[]; value: string (bindable) }`: `Select` con solo i broker attivi, etichetta `nome` più « (non connesso)» per i non connessi; nascosto se c'è un solo broker attivo.
  - `Chat.svelte`: `mqttBroker = $state('')`, scelto con `pickBroker` in un `$effect` con `untrack` (stesso schema di `via`); un `$effect` ricarica `mqttChans` con `mqttChannels(mqttBroker)` quando cambia il broker; `mqttConnected` = stato del broker scelto (se `brokers` manca: il totale, per un server vecchio); `BrokerPicker` accanto a "Canale" quando `via === MQTT_VIA`; `mqttBody(..., mqttBroker)`; avviso di successo «Pubblicato su MQTT · <nome> · <canale>» quando `brokerLabel` non è `null`.

- [ ] **Step 1: test che falliscono** (`send.test.ts`):
  - `mqttBody('ciao', 'Squadra', null, false, 'b1')` → `{text:'ciao', channel:'Squadra', broker:'b1'}`; senza broker → nessuna chiave `broker`.
  - `mqttChannelNames([{name:'MediumFast'},{name:'Squadra', custom:true}])` → `['Squadra', 'LongFast', 'MediumFast']`.
  - `classifyMqttError({status:409, code:'confirm_required', message:'Il messaggio sarà pubblico sul broker mio.example …'})` → `kind 'confirm'`, messaggio con `mio.example`; con messaggio vuoto → `PUBLIC_WARNING`.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** `npx vitest run` e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): scelta del broker per l'invio via MQTT`.

### Task 9: Interfaccia — stato per broker e broker d'origine nel feed  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/ui/BrokerBadge.svelte`
- Modify: `web/src/lib/mqttstatus.ts`, `web/src/lib/mqttstatus.test.ts`, `web/src/lib/shell/MqttStatusDetail.svelte`, `web/src/components/MessageFeed.svelte`, `web/src/components/Chat.svelte` (una riga)

**Interfaces:**
- Consumes: `MqttStatus.brokers`, `Message.broker`, `brokerLabel` (Task 7).
- Produces:
  - `mqttSummary(s, now)`: se `s.brokers` ha almeno due attivi e solo una parte è connessa → `tone 'warn'`, titolo `f"Connesso a {n} broker su {m}"`; tutti scollegati → `'ko'`; resto come oggi.
  - `brokerRows(s: MqttStatus | null, now: number) -> {id: string; name: string; tone: MqttTone; detail: string}[]` — una riga per broker attivo (`detail`: «1,5 msg/s» se connesso, altrimenti l'ultimo errore o «Non connesso»), poi i disattivati con `tone 'wait'` e «Disattivato».
  - `MqttStatusDetail.svelte`: sotto il riepilogo, l'elenco `brokerRows` (pallino, nome, dettaglio) quando i broker sono più di uno. La TopBar non cambia: il suo msg/s è già il totale e il popover usa questo componente.
  - `BrokerBadge.svelte` — props `{ id: string | null | undefined }`: legge `app.status?.mqtt.brokers`, mostra `<Badge>` con `brokerLabel(...)` o nulla.
  - `MessageFeed.svelte` e `Chat.svelte`: `<BrokerBadge id={m.broker} />` accanto ai badge esistenti.

- [ ] **Step 1: test che falliscono** (`mqttstatus.test.ts`):
  - due broker attivi, uno connesso → `tone 'warn'`, titolo «Connesso a 1 broker su 2».
  - `brokerRows`: connesso con `msgs_per_s 1.5` → `detail` «1,5 msg/s», `tone 'ok'`; non connesso con `last_error` → quel testo e `'ko'`; disattivato → «Disattivato» e `'wait'`, in fondo.
  - stato senza `brokers` (server vecchio) → `brokerRows` vuoto, `mqttSummary` come prima (i test esistenti restano verdi).
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** `npx vitest run` e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): stato di ogni broker e broker d'origine dei messaggi`.

### Task 10: Favicon con il logo di MeshLens  _(modello: haiku)_

**Files:**
- Create: `packaging/make_favicons.py`, `web/public/favicon.svg`, `web/public/favicon.ico`, `web/public/apple-touch-icon.png`, `web/src/lib/favicon.test.ts`
- Modify: `web/index.html`

**Interfaces:**
- Produces:
  - `web/public/favicon.svg` = copia identica di `docs/img/logo.svg`.
  - `packaging/make_favicons.py` (eseguito a mano, una volta; Pillow dell'extra `tray`): ridisegna la geometria di `docs/img/logo.svg` (stesse linee, cerchi e colori `#14b8a6`, `#0ea5e9`, `#0f766e`, `#f59e0b`, lente con riempimento al 18 %) su una tela 1024×1024 e la riduce con `LANCZOS`; scrive `favicon.ico` (16, 32, 48 px, sfondo trasparente) e `apple-touch-icon.png` (180×180, sfondo opaco `#0f172a`, logo all'80 %). Uso: `../../.venv/Scripts/python packaging/make_favicons.py` dalla radice del worktree.
  - In `<head>` di `web/index.html`, dopo `<title>`: `<link rel="icon" href="/favicon.ico" sizes="any" />`, `<link rel="icon" href="/favicon.svg" type="image/svg+xml" />`, `<link rel="apple-touch-icon" href="/apple-touch-icon.png" />`. Il server li serve già dalla cartella statica (fuori dall'autenticazione, come gli altri file).

- [ ] **Step 1: test che fallisce** `favicon.test.ts` (ambiente `node`, `fs` e `path` relativi a `import.meta.url`): `index.html` contiene i tre `<link>`; esistono `public/favicon.svg`, `public/favicon.ico`, `public/apple-touch-icon.png`; `favicon.svg` è identico a `../docs/img/logo.svg`; i primi 4 byte di `favicon.ico` sono `00 00 01 00`; il PNG ha larghezza 180 (byte 16–19 dell'intestazione IHDR).
- [ ] **Step 2:** `cd web && npx vitest run src/lib/favicon.test.ts` → FAIL.
- [ ] **Step 3:** scrivere lo script, eseguirlo, copiare l'SVG, aggiornare `index.html`.
- [ ] **Step 4:** stesso comando → PASS; `npm run build` → `dist/` contiene i tre file.
- [ ] **Step 5: Commit** `feat(web): favicon con il logo di MeshLens`.

### Task 11: Verifica finale  _(modello: haiku)_

Nessun codice nuovo; la versione resta quella attuale.

- [ ] **Step 1:** dalla radice del worktree `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q` → tutti verdi (più di 657).
- [ ] **Step 2:** `cd web && npx vitest run` → tutti verdi; `npm run check` → 0 errori; `npm run build` → riuscita.
- [ ] **Step 3: prova di aggiornamento:** copiare un `meshlens.db` della fase 9 con impostazioni MQTT personalizzate in una cartella temporanea, avviare `PYTHONPATH=server ../../.venv/Scripts/python -m meshlens run --data-dir <cartella> --no-browser`, verificare: `backups/*-pre-migrazione.db` presente; `PRAGMA user_version` = 3; in `GET /api/settings` un broker `default` con host, topic e `encryption: true` di prima e la password mascherata; nella tabella `settings` nessuna riga `mqtt` e nessuna password o PSK in chiaro; il log contiene «Impostazioni MQTT migrate a più broker».
- [ ] **Step 4: prova con due broker:** aggiungere un secondo broker (per esempio lo stesso mqtt.meshtastic.org con topic `msh/EU_868/IT/#`, oppure un broker pubblico con certificato valido sulla porta 8883 con TLS acceso); la TopBar mostra il totale dei msg/s, il popover lo stato di ciascuno; un messaggio arrivato da entrambi compare una volta sola con il badge del broker; un broker con TLS su una porta sbagliata mostra il suo errore senza fermare l'altro.
- [ ] **Step 5: prova dei canali:** incollare un link `https://meshtastic.org/e/#…` esportato dall'app Meshtastic → i canali compaiono nel broker con la PSK mascherata (l'occhio la mostra); "Importa dalla radio" con una radio collegata; il canale nuovo compare subito in "Canali da ascoltare" e nel composer di quel broker; un invio con Crittografia spenta esce in chiaro (verificabile con `mosquitto_sub` o con un secondo MeshLens), con Crittografia accesa è cifrato e ricevuto da una radio sul canale.
- [ ] **Step 6: prova nel browser** (1280×800 e 390×844, temi scuro e chiaro): sezione "Broker MQTT", conferma della prima volta col nome del broker giusto, favicon visibile nella scheda del browser; il pacchetto diagnostico non contiene password o PSK di nessun broker.
- [ ] **Step 7:** `git status` pulito, un commit per task.
