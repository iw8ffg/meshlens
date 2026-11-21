# MeshLens Fase 9 — Fondamenta del server: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** rendere il server solido prima delle funzioni della 1.3.0: database con migrazioni versionate, indici, pulizia a blocchi e backup; log con rotazione e pacchetto diagnostico; stato MQTT spiegato con ricollegamento automatico; code limitate tra MQTT, loop e WebSocket; accesso più sicuro (blocco persistente, sessioni, dispositivi, HTTPS facoltativo, token cifrato). Proposte A4, A9, A10, B10, D1–D5 di `docs/superpowers/research/2026-11-21-proposte-prossima-release.md`.

**Architettura:**
- **Database:** `db.py` passa a `PRAGMA user_version` con una lista di migrazioni numerate; prima di migrare un database esistente si fa un backup. La pulizia diventa una sequenza di piccoli blocchi asincroni (ogni ora, la prima dopo 60 s), seguita da `incremental_vacuum`.
- **Lavori pesanti fuori dal loop:** backup (`VACUUM INTO`), statistiche e pacchetto diagnostico usano **una connessione SQLite separata in un thread** (WAL permette letture concorrenti); argon2 gira in `asyncio.to_thread`. La connessione principale resta usata solo dal thread del loop, come dice `api.py`.
- **Flussi:** il thread paho consegna gli eventi a una `EventInbox` limitata (scarta i più vecchi e li conta), svuotata a lotti dal loop; il `Bus` verso i WebSocket, quando una coda trabocca, la sostituisce con un unico messaggio `resync` e il client ricarica i dati.
- **Interfaccia:** popover dello stato MQTT nella TopBar; in Impostazioni le schede nuove "Database e backup", "Accesso e dispositivi", "Diagnostica" e l'interruttore HTTPS nella scheda "Rete". Componenti nuovi in `web/src/components/settings/` per non gonfiare `Settings.svelte`.

**Tech Stack:** Python 3 + FastAPI/uvicorn, sqlite3 (stdlib), paho-mqtt, argon2-cffi, `cryptography` (già dipendenza), ctypes (DPAPI), `logging.handlers.RotatingFileHandler`; Svelte 5 + Vite + vitest.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md` (§5.3 Sicurezza, §4 archivio e retention). Proposte: `docs/superpowers/research/2026-11-21-proposte-prossima-release.md` (A4, A9, A10, B10, D1–D5). Le Global Constraints della fase 8 (`docs/superpowers/plans/2026-11-21-meshlens-fase8-design-invio.md`) restano valide.

## Global Constraints

- Valgono tutte le Global Constraints della fase 8: italiano, `Intl` `it-IT`, meno tipografico «−», nessun colore fuori dai token, testo ≥ 14 px e aree ≥ 44 px su telefono, nessuna risorsa esterna a runtime, regole Svelte 5 (`$effect` senza leggere e scrivere lo stesso `$state`, timer e listener puliti).
- **Nessuna dipendenza nuova** in `pyproject.toml` né in `web/package.json`. DPAPI via `ctypes`; certificati con `cryptography`.
- **Connessione SQLite principale solo dal thread del loop.** Ogni lavoro in `to_thread` apre la propria connessione (`sqlite3.connect(db_path, timeout=30)`), mai `ctx.conn`.
- **Nessun blocco lungo del loop:** ogni passo della pulizia cancella al massimo `PURGE_CHUNK = 2000` righe per tabella, poi `await asyncio.sleep(0.05)`. Unica eccezione dichiarata: "Compatta database" (`VACUUM`), su richiesta esplicita e con avviso.
- **Contratti JSON solo additivi:** `/api/status`, il messaggio WS `status` e `GET /api/settings` mantengono i campi attuali; si aggiungono campi e rotte, non si rinominano.
- **Segreti:** `mqtt.password`, `update_token` e ogni voce di `mqtt.extra_keys` non escono mai in chiaro da API, esportazione predefinita, pacchetto diagnostico o log. Maschera `MASK = "••••"` (quella di `api.py`, spostata in `settings.py`).
- **Il PC non resta mai chiuso fuori:** il blocco globale dei tentativi PIN non si applica a `127.0.0.1`/`::1`; `meshlens reset-pin` continua a funzionare.
- **Loopback sempre in HTTP** su `127.0.0.1:8686`; l'HTTPS è facoltativo (predefinito spento) e solo per l'accesso dalla rete locale.
- **Fase 10 (più broker) non va progettata qui, ma non va resa più difficile:** lo stato MQTT è un dizionario autocontenuto prodotto da un connettore (domani una lista di connettori); la cifratura dei segreti è generica (`SECRET_KEYS`), non specifica del token; l'esportazione delle impostazioni ha `"format": 1`.
- I test esistenti restano verdi (oggi 494 pytest e 195 vitest). Comandi: `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q` dalla radice del worktree; `cd web && npx vitest run`.
- Messaggi di commit in italiano, stile `feat(server): …` / `feat(web): …`.

## Contratti JSON (aggiunte)

- `GET /api/mqtt/status` (e, con gli stessi campi in più, `/api/status` e il WS `status.mqtt`): `{connected, msgs_per_s, undecodable, connected_since, last_msg_age_s, reconnects, watchdog_restarts, last_error, last_error_at, decoded, drops:{empty, unsupported_port, undecodable, json_topic, not_protobuf}, filtered_channel, queue_dropped, queue_size}`. Tempi in secondi epoch, `null` se mai successo.
- `GET /api/db` → `{size_bytes, free_bytes, schema_version, integrity, rows:{<tabella>: n}, last_purge:{time, deleted}|null}`; `POST /api/db/compact` `{confirm:true}` → `{before_bytes, after_bytes}`.
- `GET /api/backups` → `[{name, time, reason, size_bytes}]`; `POST /api/backups` → backup "manuale"; `POST /api/backups/{name}/restore` `{confirm:true}` → `{ok:true, restart_required:true}`.
- `GET /api/settings/export?secrets=0|1` → file `meshlens-impostazioni-AAAAMMGG.json` `{app:"meshlens", format:1, version, exported_at, settings}`; `secrets=1` solo da loopback (403 altrimenti). `POST /api/settings/import` `{format:1, settings}` → `{settings:<mascherate>, skipped:[chiavi]}`.
- `GET /api/diagnostics/bundle` → zip `meshlens-diagnostica-AAAAMMGG-HHMM.zip`.
- `GET /api/auth/status` aggiunge `pin_short: bool|null` (PIN < 6 cifre con accesso LAN attivo; `null` se la lunghezza non è ancora nota).
- `POST /api/auth/pin` `{current_pin, new_pin}` → `{ok:true}`; `GET /api/auth/sessions` → `[{id, created, last_seen, user_agent, ip, current}]`; `DELETE /api/auth/sessions/{id}`; `POST /api/auth/sessions/revoke-others`.
- `GET /api/tls` → `{enabled, port, fingerprint_sha256, not_after, error}`.
- WS: nuovo messaggio `{"type":"resync"}`.
- Impostazioni: nuova chiave `lan_https: bool` (predefinito `false`).

## Review Focus

1. **Aggiornamento da una 1.2.x con un database grande** (`user_version` 0, milioni di righe): il backup "pre-migrazione" esiste prima di qualsiasi `ALTER`/`CREATE INDEX`; una seconda apertura non rifà né migrazione né backup. → Task 1 e Task 3.
2. **PC mai chiuso fuori:** con il blocco globale attivo (attacco dalla LAN) il login da `127.0.0.1` funziona ancora; il blocco sopravvive al riavvio. → Task 8.
3. **Database spostato su un altro PC o profilo Windows:** il token DPAPI non si decifra → l'app parte, il token vale `""`, un warning nel log, nessuna eccezione. → Task 9.
4. **Raffica MQTT o client lento:** il loop non si blocca, i pacchetti scartati sono contati e visibili; un WebSocket che trabocca riceve **un solo** `resync`, non una perdita silenziosa. → Task 6 e Task 7.
5. **Porta HTTPS occupata o certificato non generabile:** l'interfaccia su `http://127.0.0.1:8686` resta disponibile e l'errore è mostrato in Impostazioni. → Task 10.

---

### Task 1: Database — migrazioni con `user_version` e indici  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/db.py`
- Test: `server/tests/test_db.py` (nuovo)

**Interfaces:**
- Produces:
  - `SCHEMA_VERSION = 2`
  - `connect(path, before_migrate: Callable[[sqlite3.Connection, int, int], None] | None = None) -> sqlite3.Connection` — `before_migrate(conn, old_version, new_version)` è chiamata solo per un database **già esistente** con `user_version < SCHEMA_VERSION`, prima di qualsiasi modifica dello schema.
  - `schema_version(conn) -> int`
  - Tabelle nuove: `auth_failures(ip TEXT PRIMARY KEY, failures INTEGER NOT NULL, locked_until REAL, last_failure REAL)`, `auth_attempts(time REAL, ip TEXT)` con indice su `time`; colonna nuova `sessions.ip TEXT`.

Ordine dentro `connect`: `journal_mode=WAL` → legge `user_version` e se la tabella `nodes` esiste → se nuovo database `PRAGMA auto_vacuum=INCREMENTAL` (prima di creare tabelle) → se esistente e da migrare chiama `before_migrate` → `executescript(SCHEMA)` → migrazioni da `old+1` a `SCHEMA_VERSION`, ognuna in transazione, ognuna seguita da `PRAGMA user_version=N`.
- Migrazione 1 = le `_MIGRATIONS` attuali (colonne) + `migr_hops_mqtt_v120`, idempotenti come oggi.
- Migrazione 2 = indici nuovi + `sessions.ip` + tabelle auth (in `SCHEMA` con `IF NOT EXISTS`):
  - `idx_messages_country_time ON messages(country, time)`
  - `idx_messages_radio_time ON messages(radio_id, time) WHERE radio_id IS NOT NULL`
  - `idx_nodes_last_heard ON nodes(last_heard)`
  - `idx_traceroutes_target_time ON traceroutes(target_num, time)`
  - `idx_cov_points_session_time ON coverage_points(session_id, time)` e `DROP INDEX IF EXISTS idx_cov_points_session`
  - `idx_positions_time ON positions(time)` e `idx_telemetry_time ON telemetry(time)` (servono alla pulizia a blocchi del Task 2)

- [ ] **Step 1: test che falliscono** in `test_db.py`:
  - `test_new_db_has_current_version_and_incremental_vacuum`: `schema_version(conn) == SCHEMA_VERSION` e `PRAGMA auto_vacuum` == 2; `before_migrate` **non** chiamata.
  - `test_legacy_db_is_migrated_after_hook`: crea un file con lo schema vecchio (tabella `messages` senza `radio_id`, `user_version` 0, una riga); `connect(path, hook)` → hook chiamato una volta con `(conn, 0, 2)` e, nel momento della chiamata, `radio_id` non esiste ancora; dopo: colonna presente, riga intatta, versione 2.
  - `test_reopen_does_not_migrate_again`: seconda `connect` sullo stesso file → hook non chiamato.
  - `test_indexes_exist`: i 7 indici sopra in `sqlite_master`; `idx_cov_points_session` assente.
  - `test_query_plans_use_indexes`: `EXPLAIN QUERY PLAN SELECT * FROM messages WHERE country=? ORDER BY time DESC LIMIT 50` contiene `idx_messages_country_time`.
- [ ] **Step 2:** `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q server/tests/test_db.py` → FAIL.
- [ ] **Step 3:** implementare in `db.py` come sopra; `_MIGRATIONS` resta come dati della migrazione 1.
- [ ] **Step 4:** stesso comando → PASS; poi suite intera verde.
- [ ] **Step 5: Commit** `feat(server): migrazioni del database con user_version e nuovi indici`.

### Task 2: Pulizia a blocchi, statistiche e "Compatta database"  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/store.py`, `server/meshlens/app.py`, `server/meshlens/api.py`
- Create: `server/meshlens/maintenance.py`, `web/src/components/settings/Maintenance.svelte`, `web/src/lib/maintenance.ts`
- Modify: `web/src/components/Settings.svelte`
- Test: `server/tests/test_store.py`, `server/tests/test_app.py`, `server/tests/test_maintenance.py` (nuovo), `web/src/lib/maintenance.test.ts` (nuovo)

**Interfaces:**
- Consumes: `connect`, `schema_version` (Task 1).
- Produces:
  - `PurgeStep` (dataclass: `deleted: dict[str, int]`, `done: bool`); `Store.purge_step(now: float, settings: dict, limit: int = PURGE_CHUNK) -> PurgeStep`; `Store.purge(now, settings) -> dict[str, int]` resta (ripete `purge_step` fino a `done`, per compatibilità con i test).
  - `Store.incremental_vacuum(pages: int = 1000) -> None` (no-op se `auto_vacuum != 2`).
  - In `maintenance.py`: `read_db_stats(db_path: Path) -> dict` (connessione propria in sola lettura `file:…?mode=ro`, `{size_bytes, free_bytes, schema_version, rows}`; tabelle: nodes, positions, messages, telemetry, links, traceroutes, coverage_points, sessions); `compact(conn) -> tuple[int, int]` (commit, `PRAGMA auto_vacuum=INCREMENTAL`, `VACUUM`, ritorna byte prima/dopo).
  - In `app.py`: costanti `PURGE_INTERVAL_S = 3600`, `PURGE_FIRST_DELAY_S = 60`, `PURGE_CHUNK = 2000`; `Runtime._every_async(seconds: float, fn: Callable[[], Awaitable[None]], first_delay: float) -> None`; `Runtime.purge_once() -> dict` (async); `Runtime.last_purge: dict | None`; `Runtime.db_path: Path | None`.
  - `AppContext` aggiunge `db_path: Path | None`, `last_purge: Callable[[], dict | None]`.
  - Rotte `GET /api/db` (stats in `asyncio.to_thread(read_db_stats, …)` + `integrity` e `last_purge`; `integrity` vale `"non controllata"` finché il Task 3 non la imposta) e `POST /api/db/compact` (`confirm` diverso da `true` → 400; sul loop, dichiarato bloccante).

`purge_step`, una tabella alla volta nell'ordine messages, positions, telemetry, links, nodes: `DELETE FROM t WHERE rowid IN (SELECT rowid FROM t WHERE time < ? LIMIT ?)` (per nodes la condizione attuale su `last_heard`, `is_mine`, `is_favorite`); `done` è vero quando nessuna tabella ha cancellato `limit` righe **e** `_used_bytes() <= cap`; oltre il limite di spazio cancella `limit` righe più vecchie da positions e messages. `purge_once`: ripete `purge_step` + `commit` + `await asyncio.sleep(0.05)` fino a `done`, poi `incremental_vacuum`, poi `live.evict_older_than` come oggi, poi un `log.info("Pulizia: %s", deleted)`.

- [ ] **Step 1: test che falliscono:**
  - `test_purge_step_deletes_at_most_limit`: 5000 messaggi scaduti, `purge_step(..., limit=2000)` → `deleted["messages"] == 2000`, `done is False`; tre passi → `done is True`, 0 messaggi scaduti.
  - `test_purge_keeps_existing_semantics`: i test `test_purge_*` esistenti in `test_store.py` passano invariati.
  - `test_purge_once_yields_to_loop` (`test_app.py`): con 5000 righe scadute e `PURGE_CHUNK` a 1000 (monkeypatch), un task concorrente che incrementa un contatore ogni `sleep(0)` avanza durante `purge_once()`.
  - `test_first_purge_is_delayed`: dopo `rt.start()` nessuna riga scaduta viene cancellata prima di `PURGE_FIRST_DELAY_S` (monkeypatch a 0.2 s: subito dopo l'avvio le righe ci sono, dopo 0.5 s no).
  - Aggiornare `test_purge_evicts_live_nodes_not_heard_for_7_days` a `await rt.purge_once()`.
  - `test_read_db_stats_counts_rows` e `test_compact_reduces_free_pages` (`test_maintenance.py`; dopo una cancellazione massiva `after < before`).
  - `test_db_endpoint_and_compact_requires_confirm` (`test_api.py`, con `build(tmp_path)`): `GET /api/db` 200 con `rows.messages`; `POST /api/db/compact {}` → 400; `{confirm:true}` → 200.
  - vitest `maintenance.test.ts`: `bytes(1_536_000)` → `"1,5 MB"`; `bytes(0)` → `"0 B"`.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare server; `_purge` sincrono e il task `_every(PURGE_INTERVAL_S, self._purge, first_now=True)` sono sostituiti da `_every_async(PURGE_INTERVAL_S, self.purge_once, PURGE_FIRST_DELAY_S)`.
- [ ] **Step 4:** interfaccia: `Maintenance.svelte` (scheda "Database e backup": dimensione, spazio libero, righe per tabella, ultima pulizia, pulsante "Compatta database" con Modal `risk` dal testo «L'interfaccia resterà ferma durante la compattazione: con un database grande può servire un minuto.»). `maintenance.ts`: `bytes(n: number) -> string`. Inserita in `Settings.svelte` dopo "Conservazione".
- [ ] **Step 5:** pytest e vitest → PASS.
- [ ] **Step 6: Commit** `feat: pulizia del database a piccoli blocchi, statistiche e compattazione`.

### Task 3: Backup automatici, controllo d'integrità, esporta/importa impostazioni  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/backup.py`
- Modify: `server/meshlens/app.py`, `server/meshlens/api.py`, `server/meshlens/updater.py`, `server/meshlens/settings.py`, `web/src/components/settings/Maintenance.svelte`, `web/src/lib/maintenance.ts`
- Test: `server/tests/test_backup.py` (nuovo), `server/tests/test_api.py`, `server/tests/test_updater.py`, `web/src/lib/maintenance.test.ts`

**Interfaces:**
- Consumes: `connect(path, before_migrate)` (Task 1); `Runtime._every_async` (Task 2).
- Produces:
  - `BACKUP_KEEP = 5`, `BACKUP_WEEKLY_S = 7 * 86400`, `REASONS = ("pre-migrazione", "pre-aggiornamento", "settimanale", "manuale")`.
  - `class BackupManager(db_path: Path, backups_dir: Path, clock=time.time, keep: int = BACKUP_KEEP)` con `create_sync(conn, reason) -> dict` (`VACUUM INTO` sulla connessione data: usato solo prima della migrazione), `async create(reason) -> dict` (thread + connessione propria), `list() -> list[dict]`, `prune() -> None`, `due(now: float) -> bool`, `schedule_restore(name: str) -> None` (scrive `restore.json` accanto al database).
  - `apply_pending_restore(data_dir: Path) -> str | None` — chiamata in `build()` **prima** di `connect`: sposta `meshlens.db` (+ `-wal`, `-shm`) in `backups/meshlens-<ts>-prima-del-ripristino.db` e copia il backup scelto; ritorna il nome ripristinato.
  - `quick_check(conn) -> str` (`"ok"` o il primo errore di `PRAGMA quick_check`).
  - Nomi dei file: `meshlens-AAAAMMGG-HHMMSS-<motivo>.db`; regex di validazione `^meshlens-\d{8}-\d{6}-[a-z-]+\.db$` (qualsiasi altro nome → 404, niente path traversal).
  - In `settings.py`: `MASK = "••••"` (spostata da `api.py`, che la importa), `mask_secrets(s: dict) -> dict` (password, `update_token`, ogni voce di `extra_keys` → `MASK`), `export_settings(s: dict, include_secrets: bool) -> dict`, `prepare_import(data: dict) -> tuple[dict, list[str]]` (scarta valori `MASK`, `extra_keys` se contiene `MASK`, `mqtt_send_confirmed`; `format` diverso da 1 → `ValueError`).
  - `Updater(..., before_install: Callable[[], Awaitable[None]] | None = None)`: chiamata dopo la verifica SHA e prima del launcher; un'eccezione diventa `UpdateError(f"Backup del database non riuscito: {e}", 409)` e l'installazione non parte.
  - `Runtime.backups: BackupManager`, `Runtime.db_health: str`; `AppContext.backups`, `AppContext.db_health: Callable[[], str]` (va in `GET /api/db` → `integrity`).

In `build()`: `apply_pending_restore` → `connect(db, before_migrate=lambda c, o, n: backups.create_sync(c, "pre-migrazione"))` → `db_health = quick_check(conn)` (se ≠ `"ok"`: `log.error`) → task `_every_async(3600, backup_if_due, 300)` che crea "settimanale" se `due()`. Dopo ogni creazione `prune()` (i 5 più recenti, qualsiasi motivo).

- [ ] **Step 1: test che falliscono** (`test_backup.py`):
  - `test_create_and_list_and_prune`: 7 backup con orologio finto → `list()` ne ha 5, i più recenti per primi, con `reason` e `size_bytes > 0`.
  - `test_async_backup_while_writer_open`: con la connessione principale in una transazione aperta, `await create("manuale")` produce un file apribile con le righe già committate.
  - `test_due_weekly`: nessun backup → `due` vero; backup di 6 giorni fa → falso; 8 giorni → vero.
  - `test_premigration_backup_from_legacy_db` (Review Focus 1): database vecchio con `user_version` 0 → dopo `build(tmp_path)` esiste un `*-pre-migrazione.db` che ha `user_version` 0 e la riga originale; un secondo `build` non ne crea un altro.
  - `test_restore_roundtrip`: `schedule_restore(nome)` + `apply_pending_restore` → il database corrente diventa quello del backup e il vecchio è in `*-prima-del-ripristino.db`; `restore.json` rimosso.
  - `test_restore_rejects_bad_names`: `"../meshlens.db"`, `"x.db"` → `ValueError`.
  - `test_quick_check_ok`.
  - `test_api.py`: `test_settings_export_masks_secrets_by_default` (nessuna password, token o PSK in chiaro nel corpo); `test_settings_export_with_secrets_only_local` (da `192.168.1.5` → 403); `test_settings_import_skips_masked` (import con `password: MASK` lascia la password salvata; `skipped` la elenca; chiave sconosciuta → 400 e nulla salvato); `test_backup_routes` (lista, creazione manuale, restore con `confirm` → `restart_required`).
  - `test_updater.py`: `test_install_runs_backup_first` (ordine backup → launcher) e `test_install_aborts_if_backup_fails` (409, launcher non chiamato).
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare `backup.py`, le funzioni di `settings.py`, le rotte (`/api/backups*`, `/api/settings/export`, `/api/settings/import`, quest'ultima chiama `save_settings` + `on_settings_changed`), il collegamento in `build()` e `before_install=lambda: rt.backups.create("pre-aggiornamento")`.
- [ ] **Step 4:** interfaccia in `Maintenance.svelte`: Banner `danger` se `integrity ≠ "ok"` («Il database risulta danneggiato: ripristina un backup»); elenco backup con data, motivo, dimensione, "Ripristina" (Modal `risk`: «Il ripristino sostituisce tutti i dati attuali. Riavvia MeshLens per completarlo.»); "Crea backup ora"; "Esporta impostazioni" (link `/api/settings/export`, casella "includi i segreti" visibile solo se `auth.is_local`); "Importa impostazioni" (file JSON → `POST /api/settings/import`, esito con le chiavi saltate). `maintenance.ts`: `reasonLabel(r)` → "Prima della migrazione", "Prima dell'aggiornamento", "Settimanale", "Manuale"; test vitest.
- [ ] **Step 5:** pytest e vitest → PASS.
- [ ] **Step 6: Commit** `feat: backup automatici del database, controllo d'integrità ed esportazione delle impostazioni`.

### Task 4: Log con rotazione e pacchetto diagnostico  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/logsetup.py`, `server/meshlens/diagnostics.py`, `web/src/components/settings/Diagnostics.svelte`
- Modify: `packaging/launcher.py`, `server/meshlens/paths.py`, `server/meshlens/__main__.py`, `server/meshlens/tray.py`, `server/meshlens/api.py`, `server/meshlens/app.py`, `server/meshlens/mqtt_client.py`, `server/meshlens/auth.py` (solo righe di log), `web/src/components/Settings.svelte`
- Test: `server/tests/test_logsetup.py`, `server/tests/test_diagnostics.py` (nuovi), `server/tests/test_paths.py`

**Interfaces:**
- Consumes: `read_db_stats` (Task 2), `BackupManager.list`, `mask_secrets` (Task 3).
- Produces:
  - `paths.logs_dir() -> Path`: installata `%LOCALAPPDATA%\MeshLens\logs`, sviluppo `app_dir()/data/logs`.
  - `LOG_FILE = "meshlens.log"`, `LOG_MAX_BYTES = 1_000_000`, `LOG_BACKUPS = 5`; `setup_logging(log_dir: Path, level: int = logging.INFO) -> Path` — idempotente (handler con nome `"meshlens-file"`), formato `"%(asctime)s %(levelname)s %(name)s: %(message)s"`, logger `meshlens` a INFO, radice a WARNING, `uvicorn.access` a WARNING.
  - `tail_file(path: Path, max_bytes: int) -> str` (ultimi byte, decodifica `errors="replace"`, inizio dalla prima riga intera).
  - `build_bundle(info: dict, settings: dict, log_dir: Path) -> bytes` — zip con `info.json`, `settings.json` (già mascherate da chi chiama, ma `build_bundle` riapplica `mask_secrets`), `meshlens.log` (ultimi 512 KB), `meshlens.log.1` (ultimi 256 KB, se esiste), `console.log` (ultimi 128 KB, se esiste).
  - Rotta `GET /api/diagnostics/bundle`: sul loop raccoglie `info` = versione, `frozen`, `sys.platform`, versione Python, uptime, `mqtt_status()`, stato delle radio (`id`, `kind`, `state`, ultimo errore), `bus.resyncs` se presente, `db_health`, `last_purge`, elenco backup; nel thread aggiunge `read_db_stats` e costruisce lo zip. `AppContext.log_dir: Path | None`, `AppContext.started_at: float`.

**Conciliazione con `launcher.py`:** su Windows un file aperto da un altro stream non si può rinominare, quindi `RotatingFileHandler` e la redirezione di stdout/stderr **non** possono condividere `meshlens.log`. Il launcher reindirizza su `console.log` (rotazione all'avvio oltre 1 MB, un file `.1`, come oggi); `logging` scrive `meshlens.log` con rotazione 1 MB × 5. `setup_logging(logs_dir())` è chiamata in `__main__.main` per `run` e `tray` (non per `reset-pin`).

Righe di log INFO da aggiungere (mai PIN, password, token o PSK): connessione/disconnessione MQTT con motivo; login riuscito/fallito con IP e blocchi (in `auth.py`); pulizia (già nel Task 2); backup creato/ripristinato; migrazione eseguita.

- [ ] **Step 1: test che falliscono:**
  - `test_setup_logging_rotates_at_1mb`: scrivere ~2,5 MB via `logging.getLogger("meshlens.x").info` → esistono `meshlens.log`, `.1`, `.2`; nessun file supera 1 000 000 byte + una riga; seconda chiamata a `setup_logging` non duplica le righe.
  - `test_meshlens_info_written_but_root_info_not`.
  - `test_tail_file_starts_at_line_boundary`.
  - `test_bundle_contains_files_and_no_secrets`: impostazioni con password `"segreta123"`, token `"ghp_abc"`, PSK `"AQ=="` extra e un log che contiene una riga normale → lo zip ha `info.json`, `settings.json`, `meshlens.log`; nessun file contiene `segreta123` né `ghp_abc`.
  - `test_bundle_endpoint` (`build(tmp_path)` + login): 200, `content-type` `application/zip`, `content-disposition` con `meshlens-diagnostica-`.
  - `test_logs_dir_frozen_and_dev` (`test_paths.py`).
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare; in `launcher.py` cambiare solo il nome del file (`console.log`) e il commento.
- [ ] **Step 4:** interfaccia: `Diagnostics.svelte` (scheda "Diagnostica": testo «Il pacchetto contiene la parte finale del log, la versione, le impostazioni senza password né chiavi, le dimensioni del database e lo stato di MQTT e delle radio. Non viene inviato a nessuno: lo salvi tu e lo alleghi a una segnalazione.», pulsante-link "Scarica pacchetto diagnostico" verso `/api/diagnostics/bundle` con attributo `download`). In `Settings.svelte` prima di "Informazioni".
- [ ] **Step 5:** pytest e vitest → PASS.
- [ ] **Step 6: Commit** `feat: log con rotazione e pacchetto diagnostico scaricabile`.

### Task 5: Stato MQTT spiegato e ricollegamento automatico  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/mqtt_client.py`, `server/meshlens/ingest.py`, `server/meshlens/app.py`, `server/meshlens/api.py`
- Create: `web/src/lib/mqttstatus.ts`, `web/src/lib/shell/MqttStatusDetail.svelte`
- Modify: `web/src/lib/types.ts`, `web/src/lib/shell/TopBar.svelte`, `web/src/components/Settings.svelte`
- Test: `server/tests/test_mqtt_client.py`, `server/tests/test_app.py`, `server/tests/test_ingest.py`, `web/src/lib/mqttstatus.test.ts` (nuovo)

**Interfaces:**
- Produces:
  - `MqttConnector.status() -> dict` con i campi del contratto (senza `filtered_channel`, `watchdog_restarts`, `queue_*`, aggiunti altrove): `connected_since` (istante dell'ultimo CONNACK riuscito), `last_msg_age_s`, `reconnects` (CONNACK riusciti dopo il primo), `last_error`, `last_error_at`, `decoded` (= `stats["ok"]`), `drops`.
  - Testi di `last_error`: CONNACK rifiutato → `f"Connessione rifiutata dal broker: {rc}"`; con codice "Bad user name or password"/"Not authorized" → `"Utente o password MQTT rifiutati"`; `OSError` in `connect_async` → `f"Broker non raggiungibile: {e}"`; disconnessione con codice ≠ 0 → `f"Connessione persa: {rc}"`; ricollegamento del watchdog → `f"Nessun messaggio da {MQTT_SILENT_S} s: ricollegamento"`.
  - `Ingestor.filtered_channel: int` (eventi scartati dal filtro `mqtt_channels`).
  - In `app.py`: `MQTT_SILENT_S = 300`, `MQTT_WATCHDOG_EVERY_S = 30`; `Runtime.mqtt_watchdog() -> None` (async): se il connettore è connesso e `now - (last_msg or connected_since) > MQTT_SILENT_S` → `restart_connector(reason)`; `Runtime.restart_connector(reason: str) -> None` (async: ferma il vecchio in thread conservando `learned_keys` come `on_settings_changed`, ne avvia uno nuovo, incrementa `watchdog_restarts`, imposta `last_error` sul nuovo). `Runtime.mqtt_status()` aggiunge `filtered_channel` e `watchdog_restarts`. Anche il dizionario di riserva (connettore assente) ha tutti i campi, a `null`/0.
  - Rotta `GET /api/mqtt/status` = `ctx.mqtt_status()`.
  - Web: `MqttStatus` in `types.ts` (tutti i campi nuovi facoltativi, così il client regge un server vecchio); `mqttSummary(s: MqttStatus | null, now: number) -> {tone: 'ok' | 'warn' | 'ko' | 'wait', title: string, rows: {label: string; value: string}[]}`; `DROP_LABELS = {empty:'vuoti', unsupported_port:'tipo non gestito', undecodable:'non decifrabili', json_topic:'formato JSON', not_protobuf:'non protobuf'}`.

- [ ] **Step 1: test che falliscono:**
  - `test_status_reports_connected_since_and_reconnects`: due `_on_connect` riusciti con orologio monkeypatchato → `connected_since` = secondo istante, `reconnects == 1`.
  - `test_refused_connack_sets_last_error` (codice "Bad user name or password" → `"Utente o password MQTT rifiutati"`), `test_network_error_sets_last_error` (`FakeClient(fail=True)` → inizia con `"Broker non raggiungibile"`).
  - `test_last_msg_age_and_drop_reasons`: un payload non protobuf + uno valido → `drops["not_protobuf"] == 1`, `decoded == 1`, `last_msg_age_s` ≥ 0.
  - `test_filtered_channel_counted` (`test_ingest.py`).
  - `test_watchdog_restarts_silent_connector` (`test_app.py`): `FakeConnector` con `status()` connesso e `last_msg_age_s = 301` → dopo `await rt.mqtt_watchdog()` c'è un nuovo connettore, il vecchio è fermato, `mqtt_status()["watchdog_restarts"] == 1`; con età 10 → nessun riavvio; non connesso → nessun riavvio.
  - `test_mqtt_status_route_has_new_fields`.
  - vitest: connesso con età 5 → `tone 'ok'`, titolo "Connesso"; connesso con età 180 → `'warn'`, titolo "Connesso, nessun messaggio da 3 min"; non connesso con `last_error` → `'ko'` e una riga "Ultimo errore" con quel testo; `null` → `'wait'`; righe dei motivi di scarto solo per valori > 0 con le etichette di `DROP_LABELS`; stato vecchio senza campi nuovi → nessuna eccezione.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare server; il watchdog parte in `Runtime.start` con `_every_async(MQTT_WATCHDOG_EVERY_S, self.mqtt_watchdog, MQTT_WATCHDOG_EVERY_S)`.
- [ ] **Step 4:** interfaccia: nella TopBar lo stato MQTT diventa un pulsante (`open = 'mqtt'`, stessa gestione esterno/Esc degli altri popover) che mostra `MqttStatusDetail` con il riepilogo e il link "Impostazioni MQTT" (`onselect('settings')`); su telefono si apre come gli altri popover. In Impostazioni, scheda MQTT, lo stesso `MqttStatusDetail` sopra i campi. Tempi relativi con `ago` di `format.ts`.
- [ ] **Step 5:** pytest e vitest → PASS.
- [ ] **Step 6: Commit** `feat: stato MQTT spiegato e ricollegamento automatico se non arriva nulla`.

### Task 6: Coda limitata MQTT → loop, deduplica unica, limite dei nodi in memoria  _(modello: opus)_

**Files:**
- Create: `server/meshlens/inbox.py`
- Modify: `server/meshlens/mqtt_client.py`, `server/meshlens/dedup.py`, `server/meshlens/ingest.py`, `server/meshlens/live.py`, `server/meshlens/app.py`
- Test: `server/tests/test_inbox.py` (nuovo), `server/tests/test_dedup.py`, `server/tests/test_ingest.py`, `server/tests/test_live.py`, `server/tests/test_mqtt_client.py`

**Interfaces:**
- Consumes: `MqttConnector.status()` (Task 5).
- Produces:
  - `INBOX_MAX = 5000`, `INBOX_BATCH = 200`; `class EventInbox(loop, handler: Callable[[object], None], maxsize: int = INBOX_MAX, batch: int = INBOX_BATCH)` con `put(item) -> None` (thread paho), `dropped: int`, `size() -> int`, `high_water: int`.
  - `MqttConnector.__init__` **invariata** (i `FakeConnector` dei test non cambiano); crea la sua `EventInbox(loop, on_event)`; `status()` aggiunge `queue_dropped`, `queue_size`.
  - `Deduplicator.observe(from_node: int, packet_id: int, now: float, source: str | None = None) -> tuple[bool, bool]` → `(is_new, source_seen_before)`; `is_new(...)` resta come `observe(..., None)[0]`. Valore interno per chiave: `[first_seen: float, sources: int]` (bit 1 = rf, 2 = mqtt).
  - `LiveState(max_messages: int = 2000, max_nodes: int = MAX_LIVE_NODES)` con `MAX_LIVE_NODES = 50_000`; `enforce_cap() -> int`.

`EventInbox`: `collections.deque` + `threading.Lock` + flag `_scheduled`. `put`: sotto lock, se piena `popleft()` e `dropped += 1`; `append`; se `_scheduled` è falso lo mette a vero e, fuori dal lock, `loop.call_soon_threadsafe(self._drain)` (un solo callback per raffica; `RuntimeError` a loop chiuso ignorato). `_drain` (loop): preleva sotto lock fino a `batch` elementi; per ognuno `handler(item)` in `try/except` con `log.exception` (un evento difettoso non ferma gli altri); se restano elementi `loop.call_soon(self._drain)`, altrimenti `_scheduled = False` **sotto lock, ricontrollando che la coda sia vuota** (niente evento orfano tra l'ultimo prelievo e l'azzeramento del flag).

Ingestor: `_mqtt_seen` sparisce; in `handle` una sola chiamata `is_new, seen_mqtt = self.dedup.observe(num, ev.packet_id, ev.rx_time, ev.source)` (stessa condizione di oggi su RF senza id) e il conteggio dei gateway usa `seen_mqtt` al posto di `key in self._mqtt_seen`. `record_outgoing_mqtt` continua a usare `is_new` senza sorgente (l'eco del broker resta un duplicato e conta come primo gateway, come oggi). `enforce_cap` toglie i nodi con `last_heard` più vecchio, esclusi propri e preferiti, fino al 95 % di `max_nodes`; chiamata nel task da 60 s di `Runtime` insieme a `dedup.prune`.

- [ ] **Step 1: test che falliscono:**
  - `test_inbox_drops_oldest_and_counts`: con un loop finto che registra i callback, 10 000 `put` da un thread con `maxsize=5000` → `dropped == 5000`, un solo `call_soon_threadsafe`; dopo il drain il gestore ha ricevuto gli elementi 5000…9999 in ordine.
  - `test_inbox_drains_in_batches`: 450 elementi, `batch=200` → tre giri di `_drain`, di cui due rischedulati con `call_soon`.
  - `test_inbox_handler_exception_does_not_stop_batch`.
  - `test_inbox_no_orphan_after_drain` (vero loop asyncio + thread produttore che fa `put` mentre il drain chiude: alla fine tutti gli elementi sono stati consegnati, `size() == 0`).
  - `test_on_message_delivers_event_on_loop` esistente resta verde; `test_status_reports_queue_counters`.
  - `test_observe_tracks_sources`: rf nuovo → `(True, False)`; stesso pacchetto da mqtt → `(False, False)`; di nuovo mqtt → `(False, True)`; dopo `window_s` → `(True, False)`.
  - I test sui gateway MQTT in `test_ingest.py` restano verdi; `test_ingestor_has_no_private_mqtt_seen` (`not hasattr(ingestor, "_mqtt_seen")`).
  - `test_enforce_cap_keeps_mine_and_favorites`: `max_nodes=100`, 120 nodi con 5 propri e 5 preferiti tra i più vecchi → restano 95 nodi, tra cui i 10 protetti.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** suite intera → PASS.
- [ ] **Step 5: Commit** `feat(server): coda limitata tra MQTT e loop, deduplica unica e limite dei nodi in memoria`.

### Task 7: WebSocket — `resync` quando la coda trabocca, timeout d'invio  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/bus.py`, `server/meshlens/api.py`, `web/src/lib/ws.ts`, `web/src/App.svelte`
- Test: `server/tests/test_bus.py` (nuovo), `server/tests/test_api.py`, `web/src/lib/ws.test.ts` (nuovo)

**Interfaces:**
- Produces:
  - `RESYNC = {"type": "resync"}`; `Bus.resyncs: int`; `Bus.publish` su coda piena: svuota la coda, inserisce `RESYNC`, poi il messaggio nuovo; `resyncs += 1`.
  - `WS_SEND_TIMEOUT_S = 10`; `async def send_with_timeout(ws, msg: dict, timeout: float = WS_SEND_TIMEOUT_S) -> bool` in `api.py`; nel ciclo del WS un `False` chiude con codice `1013` ed esce (il client si ricollega dopo 3 s e chiama `reconnected`, che ricarica).
  - Web: `export function dispatch(msg: unknown, h: WSHandlers): void` in `ws.ts` (estratta da `onmessage`); `WSHandlers.resync?(): void`; in `App.svelte` `resync: load` (stessa ricarica di `reconnected`, senza incrementare `app.reconnects`).

- [ ] **Step 1: test che falliscono:**
  - `test_bus_overflow_replaces_backlog_with_single_resync`: `Bus(maxsize=3)`, publish m1, m2, m3, m4 → coda `[RESYNC, m4]`; m5 → `[RESYNC, m4, m5]`; m6 → `[RESYNC, m6]`; `resyncs == 2`.
  - `test_bus_other_subscribers_unaffected`: un secondo iscritto che legge resta senza `RESYNC`.
  - `test_send_with_timeout_false_on_stuck_client`: finto ws il cui `send_json` attende per sempre, `timeout=0.05` → `False`; finto ws normale → `True`.
  - vitest `ws.test.ts`: `dispatch({type:'resync'}, h)` chiama `h.resync`; `dispatch({type:'status', mqtt:{...}}, h)` chiama `h.status({mqtt})`; tipo sconosciuto o `null` → nessuna chiamata, nessuna eccezione.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** pytest e vitest → PASS.
- [ ] **Step 5: Commit** `feat: il client ricarica i dati quando il WebSocket perde eventi`.

### Task 8: Accesso più sicuro — blocco persistente, PIN, sessioni e dispositivi  _(modello: opus)_

**Files:**
- Modify: `server/meshlens/auth.py`, `server/meshlens/api.py`
- Create: `web/src/components/settings/Devices.svelte`
- Modify: `web/src/lib/settings.ts`, `web/src/lib/types.ts`, `web/src/components/Settings.svelte`, `web/src/components/Login.svelte` (minimo 6 al primo PIN con LAN attiva)
- Test: `server/tests/test_auth.py`, `server/tests/test_api.py`, `web/src/lib/settings.test.ts`

**Interfaces:**
- Consumes: tabelle `auth_failures`, `auth_attempts`, colonna `sessions.ip` (Task 1).
- Produces (costanti in `auth.py`):
  - `MAX_FAILURES = 5`; `lock_seconds(failures: int) -> int` = `min(60 * 2 ** (failures - MAX_FAILURES), 3600)` per `failures >= 5` (60, 120, 240 … 3600), 0 sotto; contatore per IP azzerato da un login riuscito o dopo `FAILURE_RESET_S = 86400` senza errori.
  - Blocco globale: `GLOBAL_MAX_FAILURES = 30` errori da IP non loopback in `GLOBAL_WINDOW_S = 600` → tutti gli IP non loopback bloccati per `GLOBAL_LOCK_S = 900` (in `auth` chiave `global_lock_until`). Loopback (`127.0.0.1`, `::1`) esente dal globale, non dal blocco per IP.
  - `SESSION_IDLE_S = 30 * 86400`; `TOUCH_INTERVAL_S = 60`; `MIN_PIN = 4`, `MIN_PIN_LAN = 6`, `MAX_PIN = 12`.
  - `Auth.set_pin(pin: str, min_len: int = MIN_PIN) -> None` (salva anche `pin_len`); `Auth.pin_length() -> int | None`.
  - `Auth.login(pin, client_ip, user_agent=None) -> str` resta sincrona (CLI e test); `async Auth.alogin(pin, client_ip, user_agent=None) -> str` per l'API: controllo blocchi sul loop → verifica argon2 in `asyncio.to_thread` → registrazione esito sul loop. Entrambe condividono `_precheck(ip, now)`, `_record_failure(ip, now)`, `_issue_token(ip, ua, now)`. Un login riuscito memorizza `pin_len` se mancava.
  - Concorrenza: `asyncio.Lock` per IP (i tentativi dallo stesso IP sono in fila: niente tentativi paralleli che sfuggono al contatore) e `asyncio.Semaphore(2)` globale sulle verifiche argon2 (64 MiB ciascuna).
  - `Auth.check(token) -> bool`: sessione con `last_seen` più vecchio di `SESSION_IDLE_S` → cancellata e `False`; aggiorna `last_seen` (e committa) solo se sono passati `TOUCH_INTERVAL_S`.
  - `Auth.change_pin(token: str, current: str, new: str, min_len: int) -> None` (async: verifica come `alogin`, contando gli errori; poi revoca tutte le altre sessioni).
  - `Auth.sessions(current_token: str | None) -> list[dict]` (`id` = primi 16 caratteri di `token_hash`); `Auth.revoke(session_id: str) -> bool` (id validato `^[0-9a-f]{16}$`); `Auth.revoke_others(current_token: str) -> int`.
  - API: `/api/auth/login` e `/api/auth/setup` usano `alogin`; `setup` con `lan_access` attivo richiede `MIN_PIN_LAN`; rotte `POST /api/auth/pin`, `GET /api/auth/sessions`, `DELETE /api/auth/sessions/{id}`, `POST /api/auth/sessions/revoke-others`; `auth/status` aggiunge `pin_short` (`lan_access` e `pin_length() < 6`; `null` se lunghezza ignota). I PIN di 4–5 cifre già impostati continuano a funzionare anche con LAN attiva.
  - Web: `pinError(pin: string, lan: boolean) -> string | null` in `settings.ts` («Il PIN deve avere da 6 a 12 cifre» con LAN, «da 4 a 12» senza; solo cifre).

- [ ] **Step 1: test che falliscono** (`test_auth.py`, con `Clock` esistente):
  - `test_backoff_grows_and_caps`: `lock_seconds(5) == 60`, `(6) == 120`, `(11) == 3600`, `(20) == 3600`.
  - `test_lock_survives_restart`: 5 errori → nuova `Auth` sulla stessa connessione → `LockedError` con `retry_after == 60`.
  - `test_global_lock_spares_loopback` (Review Focus 2): 30 errori da 30 IP diversi → `10.0.0.99` riceve `LockedError`; `127.0.0.1` con PIN giusto entra.
  - `test_failures_reset_after_success_and_after_a_day`.
  - `test_alogin_runs_verify_off_loop`: monkeypatch di `asyncio.to_thread` che registra la chiamata → la verifica passa da lì.
  - `test_parallel_attempts_same_ip_are_serialized`: 10 `alogin` errati in `gather` dallo stesso IP → al più 5 verifiche argon2, gli altri `LockedError`.
  - `test_session_expires_after_30_days_idle` e `test_touch_is_throttled` (due `check` a 10 s di distanza → un solo `UPDATE` di `last_seen`).
  - `test_sessions_list_and_revoke`: due login → `sessions(t1)` ha 2 voci, una con `current: True`, con `ip` e `user_agent`; `revoke(id di t2)` → `check(t2)` falso; id non valido → `False`.
  - `test_api.py`: `test_setup_requires_6_digits_with_lan` (400 con `"1234"` se `lan_access` vero); `test_short_pin_keeps_working_with_lan` (PIN `"1234"`, poi LAN attiva → login ok, `pin_short` vero); `test_change_pin_requires_current_and_revokes_others`; `test_login_lock_returns_429_with_retry_after`.
  - vitest: `pinError('1234', true)` → messaggio; `pinError('123456', true)` → `null`; `pinError('12a4', false)` → messaggio.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare `auth.py` e le rotte.
- [ ] **Step 4:** interfaccia `Devices.svelte` (scheda "Accesso e dispositivi"): Banner `warn` se `pin_short` («Il PIN ha meno di 6 cifre: per l'accesso dalla rete cambialo con uno più lungo»); modulo "Cambia PIN" (attuale, nuovo, conferma; `pinError`); elenco dispositivi (browser dal user agent, IP, ultimo accesso con `ago`, "Questo dispositivo"), "Esci" per riga e "Esci da tutti gli altri". In `Settings.svelte` dopo "Rete".
- [ ] **Step 5:** pytest e vitest → PASS.
- [ ] **Step 6: Commit** `feat: blocco PIN persistente con attese crescenti, scadenza e revoca delle sessioni`.

### Task 9: Token GitHub cifrato con DPAPI  _(modello: sonnet)_

**Files:**
- Create: `server/meshlens/secretbox.py`
- Modify: `server/meshlens/settings.py`, `server/meshlens/app.py`
- Test: `server/tests/test_secretbox.py` (nuovo), `server/tests/test_settings.py`

**Interfaces:**
- Consumes: `mask_secrets`, `export_settings` (Task 3).
- Produces:
  - `SECRET_KEYS = ("update_token",)` (elenco generico: la fase 10 potrà aggiungere le password dei broker).
  - `class Protector(Protocol)`: `protect(plain: str) -> str`, `unprotect(stored: str) -> str` (solleva `SecretError`).
  - `DpapiProtector` (Windows: `CryptProtectData`/`CryptUnprotectData` via `ctypes`, struttura `DATA_BLOB`, flag `CRYPTPROTECT_UI_FORBIDDEN = 0x1`, entropia `b"MeshLens"`, `LocalFree` del buffer); formato salvato `"dpapi:v1:" + base64`.
  - `PlainProtector` (non Windows): `"plain:" + valore`.
  - `default_protector() -> Protector` (`sys.platform == "win32"` → DPAPI); `set_protector(p)` per i test.
  - `save_settings` cifra le `SECRET_KEYS` non vuote prima di scriverle; `load_settings` le decifra: valore senza prefisso = vecchio testo in chiaro (restituito così com'è); `SecretError` → `""` e `log.warning("Impossibile decifrare %s: reimpostalo", key)`.
  - `migrate_secrets(conn) -> int`: riscrive cifrati i valori in chiaro; chiamata in `build()` subito dopo `connect`.

- [ ] **Step 1: test che falliscono:**
  - `test_dpapi_roundtrip` (`skipif sys.platform != "win32"`): `unprotect(protect("ghp_x")) == "ghp_x"`, il valore salvato inizia con `"dpapi:v1:"` e non contiene `ghp_x`.
  - `test_saved_token_is_not_plaintext_in_db`: con `PlainProtector` finto che fa ROT/base64, la riga grezza in `settings` non contiene il token; `load_settings` lo restituisce in chiaro.
  - `test_legacy_plaintext_token_migrated`: riga in chiaro scritta a mano → `migrate_secrets` ritorna 1, la riga ora è cifrata, `load_settings` dà lo stesso token; seconda chiamata ritorna 0.
  - `test_undecryptable_token_becomes_empty` (Review Focus 3): protector che solleva `SecretError` → `load_settings()["update_token"] == ""`, warning nel log, nessuna eccezione; `build(tmp_path)` parte.
  - `test_get_settings_still_masks_token` (`test_api.py`).
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** suite intera → PASS (l'Updater legge il token da `settings()` già decifrato: nessuna modifica).
- [ ] **Step 5: Commit** `feat(server): token GitHub cifrato con DPAPI e migrazione trasparente`.

### Task 10: HTTPS facoltativo per l'accesso dalla rete locale  _(modello: opus)_

**Files:**
- Create: `server/meshlens/tls.py`, `server/meshlens/serving.py`
- Modify: `server/meshlens/settings.py`, `server/meshlens/tray.py`, `server/meshlens/__main__.py`, `server/meshlens/api.py`, `server/meshlens/app.py`, `web/src/components/Settings.svelte`, `web/src/lib/settings.ts`
- Test: `server/tests/test_tls.py`, `server/tests/test_serving.py` (nuovi), `server/tests/test_settings.py`, `server/tests/test_tray.py`, `server/tests/test_api.py`

**Interfaces:**
- Produces:
  - Impostazione `lan_https: bool` (predefinito `False`, validata come `lan_access`).
  - `CERT_DAYS = 825`, `RENEW_BEFORE_DAYS = 30`; `CertInfo` (dataclass: `cert_path`, `key_path`, `fingerprint_sha256: str` in esadecimale con `:`, `not_after: float`); `local_ipv4s() -> list[str]`; `ensure_cert(cert_dir: Path, ips: list[str], now: float | None = None) -> CertInfo` — chiave EC P-256, autofirmato, CN "MeshLens", SAN `DNS:localhost`, `IP:127.0.0.1` e gli IP dati; rigenera se manca, non si legge, scade entro 30 giorni o non copre gli IP correnti; file in `data_dir/tls/` (`cert.pem`, `key.pem`).
  - `HTTPS_PORT_OFFSET = 1`; `Bind` (dataclass: `host`, `port`, `tls: bool`); `plan_binds(lan_access: bool, lan_https: bool, port: int) -> list[Bind]`:
    - LAN spenta → `[Bind("127.0.0.1", port, False)]`;
    - LAN accesa senza HTTPS → `[Bind("0.0.0.0", port, False)]` (come oggi);
    - LAN e HTTPS → `[Bind("127.0.0.1", port, False), Bind("0.0.0.0", port + 1, True)]`.
  - `make_servers(app, binds, cert: CertInfo | None, log_config) -> list[uvicorn.Server]`: **solo il primo server ha `lifespan="on"`, gli altri `lifespan="off"`** (altrimenti `Runtime.start` girerebbe due volte); `ssl_certfile`/`ssl_keyfile` per i `Bind` con `tls`.
  - `async serve_all(servers, errors: list[str]) -> None`: il primo server come oggi; i secondari in task separati che catturano `BaseException` (uvicorn chiama `sys.exit(1)` se la porta è occupata) e aggiungono il messaggio a `errors` senza fermare il primo.
  - `ServerThread(app, binds: list[Bind], cert: CertInfo | None)` usa `make_servers` + `serve_all`; `wait_started` aspetta solo il primo; `stop` mette `should_exit` su tutti. `__main__ run` usa gli stessi helper (`asyncio.run(serve_all(...))`) al posto di `uvicorn.run`.
  - `AppContext.tls: dict` (`{enabled, port, fingerprint_sha256, not_after, error}`), impostato da chi avvia il server; rotta `GET /api/tls`.
  - Cookie: `secure=(request.url.scheme == "https")`.
  - Se `ensure_cert` fallisce: `log.exception` e si serve **solo** il loopback HTTP (`[Bind("127.0.0.1", port, False)]`: la LAN non si apre in chiaro se l'utente ha chiesto HTTPS); `tls.error` lo spiega.

- [ ] **Step 1: test che falliscono:**
  - `test_plan_binds_cases`: i tre casi sopra.
  - `test_ensure_cert_creates_and_reuses`: prima chiamata crea i file; seconda con gli stessi IP non li riscrive (mtime invariato); IP nuovo → rigenera e la SAN contiene il nuovo IP.
  - `test_ensure_cert_renews_near_expiry`: `now` = `not_after - 10 giorni` → rigenera.
  - `test_cert_fields`: SAN contiene `127.0.0.1` e `localhost`; chiave EC; `fingerprint_sha256` = SHA-256 del DER.
  - `test_make_servers_only_first_has_lifespan`.
  - `test_secondary_bind_failure_keeps_primary` (Review Focus 5): server secondario finto la cui `serve()` solleva `SystemExit(1)` → `errors` ha un messaggio, il primario ha continuato (finto che registra l'avvio).
  - `test_cert_failure_serves_loopback_only`: `ensure_cert` che solleva → binds = `[Bind("127.0.0.1", port, False)]`, `tls.error` impostato.
  - `test_cookie_secure_on_https` (`ASGITransport` con `base_url="https://127.0.0.1"` → `Set-Cookie` contiene `Secure`; su http no).
  - `test_lan_https_setting_validation`.
- [ ] **Step 2:** eseguire → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** interfaccia nella scheda "Rete": `Switch` "Usa HTTPS per l'accesso dalla rete" (disattivato se l'accesso dalla rete è spento), nota «Indirizzo: https://<IP del PC>:8687. Il browser mostrerà un avviso perché il certificato è creato da MeshLens: confronta l'impronta qui sotto. Dal PC resta http://127.0.0.1:8686. Vale dal prossimo avvio; Windows potrebbe chiedere il permesso del firewall per la nuova porta.»; impronta e scadenza da `GET /api/tls`; Banner `danger` con `tls.error`.
- [ ] **Step 5:** pytest e vitest → PASS.
- [ ] **Step 6: Commit** `feat: HTTPS facoltativo con certificato locale per l'accesso dalla rete`.

### Task 11: Verifica finale  _(modello: haiku)_

Nessun codice nuovo; la versione resta quella attuale (il passaggio a 1.3.0 si fa nella release, a parte).

- [ ] **Step 1:** dalla radice del worktree `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q` → tutti verdi (più di 494).
- [ ] **Step 2:** `cd web && npx vitest run` → tutti verdi (più di 195); `cd web && npm run check` → 0 errori; `cd web && npm run build` → build riuscita.
- [ ] **Step 3: prova di aggiornamento del database:** copiare un `meshlens.db` di una 1.2.x in una cartella temporanea, avviare `PYTHONPATH=server ../../.venv/Scripts/python -m meshlens run --data-dir <cartella> --no-browser`, verificare: `backups/*-pre-migrazione.db` presente; `PRAGMA user_version` = 2; `logs/meshlens.log` con la riga della migrazione; `GET /api/db` con `integrity: "ok"`.
- [ ] **Step 4: prova nel browser** (1280×800 e 390×844, temi scuro e chiaro): popover MQTT nella TopBar; Impostazioni → "Database e backup" (Compatta, Crea backup, Esporta/Importa), "Accesso e dispositivi" (cambio PIN, revoca), "Diagnostica" (lo zip si scarica e non contiene la password MQTT), interruttore HTTPS.
- [ ] **Step 5: prova LAN + HTTPS:** con `lan_access` e `lan_https` attivi e riavvio, `https://<IP>:8687` da un altro dispositivo mostra l'avviso del certificato con la stessa impronta delle Impostazioni; `http://127.0.0.1:8686` funziona dal PC; `http://<IP>:8686` dalla LAN non risponde.
- [ ] **Step 6: prova del blocco:** 5 PIN errati da un altro dispositivo → 429 con `Retry-After: 60`; riavvio di MeshLens → ancora bloccato; dal PC l'accesso funziona.
- [ ] **Step 7:** `git status` pulito, un commit per task.
