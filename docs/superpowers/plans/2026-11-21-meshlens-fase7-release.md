# MeshLens Fase 7 — Installer, repository, release 1.0 e aggiornamento: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:**
- un installer Windows per utente, con icona nell'area di notifica;
- il repository GitHub privato `iw8ffg/meshlens`, con README, CHANGELOG e licenza in italiano (primaria) e inglese;
- la release **1.0.0** costruita automaticamente;
- l'aggiornamento dall'app: controllo, download verificato e installazione.

**Architettura:**
- **Eseguibile:** PyInstaller in modalità *onedir* crea `MeshLens.exe` (finestra nascosta) con il server, l'interfaccia compilata, i dati inclusi e `go-pmtiles`.
- **Lanciatore:** `meshlens.tray` avvia il server in un thread, apre il browser e mostra un'icona `pystray` (Apri MeshLens, Apri cartella dati, Avvia all'accesso, Esci). Se MeshLens è già in esecuzione, un secondo avvio apre solo il browser.
- **Installer:** Inno Setup, installazione per l'utente senza amministratore.
- **Build:** GitHub Actions su runner Windows costruisce e pubblica la release a ogni tag `v*`.
- **Aggiornamento:** `updater.py` interroga l'API GitHub Releases (con un token finché il repository è privato), scarica l'installer, ne verifica lo SHA-256 e lo avvia in modalità silenziosa. L'installer chiude MeshLens e lo riavvia.

**Tecnologie:** in più alle precedenti `pyinstaller`, `pystray` e `Pillow` (solo per la build e il lanciatore), Inno Setup 6 (preinstallato sui runner `windows-latest`) e GitHub Actions.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md`. Le decisioni dell'utente del 2026-11-21 superano l'anti-obiettivo ".exe" della §2.

## Global Constraints

- **Decisioni dell'utente:**
  - repository **privato `iw8ffg/meshlens`**, destinato a diventare pubblico;
  - installazione **per utente** con icona di notifica e avvio automatico facoltativo;
  - **token** di aggiornamento inserito dall'utente in Impostazioni;
  - **licenza GPL-3.0, "Copyright © 2026 iw8ffg"**;
  - README, CHANGELOG e licenza **in italiano (primaria) e inglese**.
- **Versione:**
  - `1.0.0`, definita **solo** in `server/meshlens/__init__.py` come `__version__`;
  - `pyproject.toml` la legge in modo dinamico, e l'installer e la build la ricevono dallo script;
  - i tag git hanno la forma `vX.Y.Z`.
- **Percorsi:**
  - in esecuzione installata (`sys.frozen`), i dati stanno in `%LOCALAPPDATA%\MeshLens\data` e gli aggiornamenti scaricati in `%LOCALAPPDATA%\MeshLens\updates`;
  - in sviluppo restano `./data`, come oggi;
  - `--data-dir` ha sempre la precedenza.
- **Installer:**
  - `PrivilegesRequired=lowest`, cartella `{localappdata}\Programs\MeshLens`;
  - collegamento nel menu Start;
  - attività facoltativa "Avvia MeshLens all'accesso a Windows", che scrive `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`;
  - `CloseApplications=yes`;
  - avvio di MeshLens a fine installazione, **anche in modalità silenziosa**;
  - la disinstallazione **non** cancella `%LOCALAPPDATA%\MeshLens\data`, salvo una domanda esplicita in modalità interattiva;
  - `AppId` fisso (GUID generato una volta e scritto nello script).
- **Nome degli asset della release:** `MeshLens-Setup-X.Y.Z.exe` e `MeshLens-Setup-X.Y.Z.exe.sha256`, quest'ultimo con una riga `<hex>  MeshLens-Setup-X.Y.Z.exe`.
- **go-pmtiles** incluso nell'installer in `tools\pmtiles.exe`. La CI lo scarica e ne verifica lo SHA-256 con le stesse costanti di `maps.py`; se è presente, `maps.py` lo usa senza scaricarlo.
- **Aggiornamento:**
  - impostazioni `update_repo` (default `iw8ffg/meshlens`), `update_token` (segreto, mascherato `"••••"` come gli altri, mai nei log) e `update_auto_check` (default true, un controllo ogni 24 h);
  - solo HTTPS, verso `api.github.com` e i redirect degli asset GitHub;
  - **lo SHA-256 deve coincidere, altrimenti il file viene cancellato e l'installazione non parte**;
  - l'installazione richiede `confirm:true` ed è possibile solo in esecuzione installata. In sviluppo il controllo funziona, ma l'installazione risponde 409 "Disponibile solo nella versione installata".
  - Il confronto delle versioni è semver: le pre-release (`-beta`) si ignorano.
- **Firma del codice:** l'installer non è firmato. README e note di rilascio spiegano l'avviso di SmartScreen ("Ulteriori informazioni → Esegui comunque").
- **Niente dati personali nel repository:**
  - `data/` resta ignorata;
  - prima del push si fa un controllo esplicito: nessun file di `data/` nella storia, nessun token o PIN nel codice, nessun indirizzo email personale fuori da quelli dei commit;
  - le **schermate del README** usano un **database dimostrativo** con nodi finti, generato da `tools/demo_seed.py`, non i dati MQTT reali.
- **Licenze di terze parti:** un file `THIRD_PARTY_NOTICES.md` elenca le dipendenze incluse nell'installer con le loro licenze. Lo genera `pip-licenses`, più le voci JS da `npm` (licenze di produzione), più go-pmtiles (BSD-3), i caratteri Noto (OFL), gli sprite Protomaps (MIT) e l'attribuzione ODbL dei dati.
- Testi dell'app in italiano.

## Contratti JSON (aggiornamento)

- `GET /api/version` → `{version, frozen:bool, data_dir}`.
- `GET /api/update/status` → `{current, latest:string|null, available:bool, notes:string|null, published_at, checked_at, error:string|null, job:<Lavoro>|null, can_install:bool}`.
- `POST /api/update/check` → lo stato aggiornato. Gli errori diventano `error`:
  - 401/403/404 dall'API, con token mancante o non valido → "Repository privato: inserisci un token valido in Impostazioni → Aggiornamenti";
  - nessuna rete → "Nessuna connessione".
- `POST /api/update/download` → 202 Lavoro `{id, status:"running"|"done"|"failed", bytes_done, bytes_total, error}`. WebSocket: `{"type":"update_job","job":{...}}`.
- `POST /api/update/install` body `{confirm:true}` → 202 `{ok:true}`.
  - Lancia `MeshLens-Setup-X.Y.Z.exe /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS` staccato dal processo, poi chiede al lanciatore di uscire dopo 2 s.
  - Rifiutato con 409 se il file non è scaricato e verificato, oppure se l'esecuzione non è installata.
- Le impostazioni accettano `update_repo` (formato `owner/name`), `update_token` (stringa; `"••••"` significa invariato) e `update_auto_check` (bool).

## Review Focus

1. **Installer scaricato e corrotto o manomesso:** con l'impronta diversa il file viene cancellato e nulla viene eseguito. Un download interrotto non lascia file "pronti".
2. **Token:** non compare mai in risposte, WebSocket, log o messaggi d'errore. Un token sbagliato dà un messaggio chiaro senza far cadere nulla.
3. **Doppio avvio:** il secondo `MeshLens.exe` apre il browser e termina, senza secondo server né errore di porta occupata. Se la porta è occupata da un altro programma, compare un messaggio chiaro.
4. **Aggiornamento silenzioso:** l'installer chiude l'istanza in esecuzione e la riavvia; i dati in `%LOCALAPPDATA%\MeshLens\data` restano intatti.
5. **Repository pulito:** nessun dato personale (database, PIN, token, coordinate reali della casa) nei file o nella storia pubblicata.

---

### Task 1: Server, versione, percorsi per l'esecuzione installata, go-pmtiles incluso

**File:**
- Modifica: `server/meshlens/__init__.py`, `server/meshlens/__main__.py`, `server/meshlens/api.py`, `server/meshlens/maps.py`, `pyproject.toml`
- Test: `server/tests/test_paths.py`, `server/tests/test_api.py`

**Interfacce prodotte:**
- `__version__ = "1.0.0"`;
- `paths.py` con `is_frozen() -> bool`, `default_data_dir() -> Path`, `app_dir() -> Path` (la cartella dell'eseguibile, oppure la radice del repository), `bundled_tool() -> Path | None` (`app_dir()/tools/pmtiles.exe`, se esiste);
- `MapsManager` considera lo strumento installato se `bundled_tool()` esiste;
- `GET /api/version`;
- `pyproject.toml`: `dynamic = ["version"]` con `[tool.setuptools.dynamic] version = {attr = "meshlens.__version__"}`.

- [ ] **Step 1: Test che falliscono**
  - `test_default_data_dir_frozen_uses_localappdata`, con `sys.frozen` e la variabile d'ambiente simulati;
  - `test_default_data_dir_dev_is_repo_data`;
  - `test_bundled_tool_used_by_maps`;
  - `test_version_route`.
- [ ] **Step 2: Esegui** `.venv/Scripts/python -m pytest server/tests -q`. Atteso: falliscono i test nuovi.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): versione 1.0.0 e percorsi per la versione installata`.

### Task 2: Lanciatore con icona di notifica

**File:**
- Crea: `server/meshlens/tray.py`, `server/meshlens/assets/meshlens.ico` (più `meshlens.png` per l'icona di notifica; sono il logo del Task 6, quindi si crea qui una prima versione semplice in SVG e PNG generati con Pillow, poi la si sostituisce)
- Modifica: `server/meshlens/__main__.py` (nuovo comando `tray`, che è il default in esecuzione installata), `pyproject.toml` (extra `[tray]` con `pystray` e `Pillow`)
- Test: `server/tests/test_tray.py` (solo la logica pura)

**Interfacce:**
- `single_instance(port) -> "free" | "meshlens" | "other"`: prova la porta e, se è occupata, chiama `GET /api/version` per capire se risponde MeshLens;
- `set_autostart(enabled: bool, exe: Path)` e `get_autostart() -> bool`, tramite `winreg` su HKCU Run, nome `MeshLens`;
- `run_tray(data_dir)`:
  - avvia uvicorn in un thread con `should_exit` controllabile;
  - apre il browser su `http://127.0.0.1:<porta>`;
  - menu: "Apri MeshLens", "Apri cartella dati" (`os.startfile`), "Avvia all'accesso" (spunta), "Esci";
  - chiusura pulita: ferma il server, che a sua volta ferma radio e processi figli;
- endpoint interno `POST /api/internal/shutdown`, accettato **solo da 127.0.0.1** e con un token casuale generato all'avvio e noto solo al lanciatore. L'aggiornamento lo usa per uscire.

- [ ] **Step 1: Test che falliscono:**
  - `single_instance` con una porta libera, con un finto MeshLens e con un finto altro programma;
  - `set_autostart`/`get_autostart` con un `winreg` simulato;
  - `/api/internal/shutdown` restituisce 403 senza token o da un IP non locale.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat: lanciatore con icona di notifica e istanza singola`.

### Task 3: Aggiornamento, server

**File:**
- Crea: `server/meshlens/updater.py`
- Modifica: `server/meshlens/api.py`, `server/meshlens/app.py`, `server/meshlens/settings.py`
- Test: `server/tests/test_updater.py`, `server/tests/test_api_update.py`

**Interfacce:**
- `parse_version(s) -> tuple | None`, che restituisce None per le pre-release;
- `is_newer(latest, current) -> bool`;
- `class Updater(settings, bus, http, clock, frozen, updates_dir, launcher_exit)`, con i metodi `status()`, `check()`, `start_download()`, `install(confirm)` e un controllo automatico ogni 24 h se `update_auto_check` è attivo;
- `http` è iniettabile per i test e non usa mai la rete reale nei test.
- Gli asset si scaricano con `Accept: application/octet-stream` dall'URL API dell'asset e `Authorization: Bearer <token>` se il token è impostato. I redirect si seguono senza propagare il token a domini diversi da `api.github.com`: lo fanno già urllib e httpx con l'opzione giusta, va verificato.

- [ ] **Step 1: Test che falliscono:**
  - `is_newer` ("1.0.1" contro "1.0.0" → true; "1.0.0-beta" → ignorata);
  - `check` con token mancante e risposta 404 → messaggio del repository privato;
  - `test_token_never_in_status_or_logs` (Review Focus 2);
  - `test_download_bad_sha_deleted` (Review Focus 1);
  - `test_install_requires_confirm_and_frozen`;
  - `test_install_launches_detached_and_requests_exit`, con il lanciatore simulato;
  - `test_auto_check_daily`.
- [ ] **Step 2: Esegui pytest.** Atteso: falliscono.
- [ ] **Step 3: Implementa.**
- [ ] **Step 4: Esegui tutta la suite.** Atteso: verde.
- [ ] **Step 5: Commit** `feat(server): aggiornamento da GitHub Releases con verifica SHA-256`.

### Task 4: Aggiornamento, interfaccia

**File:**
- Crea: `web/src/components/Updates.svelte`, `web/src/lib/update.ts`, `web/src/lib/update.test.ts`
- Modifica: `web/src/components/Settings.svelte`, `web/src/lib/api.ts`, `web/src/lib/types.ts`, `web/src/lib/stores.svelte.ts`, `web/src/lib/ws.ts`, `web/src/components/StatusBar.svelte` (banner)

**Comportamento:**
- **Impostazioni → "Aggiornamenti":**
  - versione attuale;
  - campo "Token GitHub (repository privato)", con il segreto mascherato e il pulsante "Sostituisci", più una guida per creare un token *fine-grained* con "Contents: Read-only" sul solo repository `iw8ffg/meshlens`;
  - casella "Controlla automaticamente ogni giorno";
  - pulsante "Controlla ora";
  - le note della release come testo;
  - "Scarica" con l'avanzamento, poi "Installa e riavvia" con la conferma "MeshLens si chiuderà per qualche secondo e si riaprirà aggiornato";
  - in sviluppo il pulsante d'installazione è disattivato e spiegato.
- **Banner** nella barra di stato quando c'è un aggiornamento: "Disponibile MeshLens X.Y.Z", che porta alle impostazioni.
- `update.ts`: `updateLabel(status)` e `canInstall(status, job)`.

- [ ] **Step 1: Test vitest che falliscono** su `updateLabel` e `canInstall`.
- [ ] **Step 2: Esegui vitest.** Atteso: falliscono.
- [ ] **Step 3: Implementa.** Nessun `$effect` deve leggere e scrivere lo stesso stato, e i timer vanno puliti.
- [ ] **Step 4: Verifica:** vitest, `npm run check` e `npm run build` puliti.
- [ ] **Step 5: Commit** `feat(web): impostazioni aggiornamenti e banner`.

### Task 5: Build, installer e automazione GitHub

**File:**
- Crea:
  - `packaging/meshlens.spec` (PyInstaller onedir, `console=False`, icona; include `web/dist`, `server/meshlens/data`, `server/meshlens/assets` e le parti WinRT di bleak tramite hook, oppure `collect_all('bleak')`, `collect_all('winrt')`, `collect_all('meshtastic')`);
  - `packaging/meshlens.iss` (Inno Setup secondo le Global Constraints, con la versione da `/DAppVersion`);
  - `tools/build.ps1` (build locale: npm ci, build, PyInstaller; non serve Inno in locale);
  - `.github/workflows/ci.yml` (push e PR: pytest e vitest su `windows-latest`);
  - `.github/workflows/release.yml`.
- **`release.yml`**, su tag `v*`:
  1. installa Python 3.12 e Node 24;
  2. esegue test e build;
  3. scarica go-pmtiles con verifica SHA-256 e lo mette in `tools/`;
  4. esegue PyInstaller e poi `iscc /DAppVersion=X.Y.Z`;
  5. calcola lo SHA-256;
  6. crea la release con `gh release create vX.Y.Z` e gli asset, usando come note la sezione della versione dal CHANGELOG, italiano più inglese;
  7. **fallisce se la versione del tag e `__version__` non coincidono.**

- [ ] **Step 1:** esegui `tools/build.ps1` in locale. `dist\MeshLens\MeshLens.exe` deve partire, mostrare l'icona e servire l'interfaccia su `http://127.0.0.1:8686`. Prova anche il secondo avvio (Review Focus 3). Il controllore verifica nel browser.
- [ ] **Step 2:** scrivi l'`.iss` e i workflow; validali con `actionlint`, se disponibile senza installare nulla, altrimenti con una lettura attenta.
- [ ] **Step 3: Commit** `build: PyInstaller, Inno Setup e workflow di release`.

### Task 6: Documentazione bilingue, logo, schermate

**File:**
- Crea:
  - `README.md` (italiano), `README.en.md` (inglese), con un collegamento reciproco in cima;
  - `CHANGELOG.md`: per ogni versione una sezione italiana e poi una inglese, formato *Keep a Changelog*;
  - `LICENSE` (testo ufficiale GPL-3.0 in inglese), `LICENZA.md` (riassunto in italiano più l'avviso bilingue che fa fede il testo inglese, con link alla traduzione non ufficiale elencata dalla FSF);
  - `THIRD_PARTY_NOTICES.md`;
  - `docs/img/logo.svg`, `docs/img/banner.png`, `docs/img/screen-*.png`;
  - `tools/demo_seed.py`.
- **README:**
  - banner con il logo;
  - badge (licenza GPL-3.0, ultima release, Windows);
  - in breve cos'è;
  - schermate: mappa con i nodi, scheda Rete con il grafico, chat radio, prova di copertura, pannello Configura e una vista telefono;
  - funzioni principali;
  - requisiti: Windows 10/11, radio Meshtastic con firmware 2.5 o superiore, ma provato con il 2.7;
  - installazione, con la nota su SmartScreen;
  - primo avvio con il PIN;
  - uso dal telefono;
  - mappe offline;
  - aggiornamenti, con il token finché il repository è privato;
  - sviluppo da sorgente;
  - privacy (nessun dato inviato, MQTT solo in ascolto);
  - licenza e ringraziamenti (Meshtastic, Protomaps, OpenStreetMap, OpenFreeMap).
  - Le note "non affiliato al progetto Meshtastic" e "Meshtastic® è un marchio di Meshtastic LLC" vanno nella sezione legale.
- **`demo_seed.py`:** crea in una cartella temporanea un database con circa 40 nodi finti in Italia (nomi inventati e coordinate casuali in città italiane), telemetria finta per i grafici, collegamenti e una sessione di copertura finta. Le schermate le cattura il controllore nel browser avviando il server con `--data-dir` su quella cartella, MQTT disattivato con un broker vuoto.

- [ ] **Step 1:** crea `demo_seed.py` con un test che verifica che il database dimostrativo si apra e contenga nodi senza dati reali.
- [ ] **Step 2:** scrivi i documenti, il logo e il banner.
- [ ] **Step 3:** il controllore cattura le schermate (desktop 1280×800 e telefono 375×812) e le salva in `docs/img/`.
- [ ] **Step 4: Commit** `docs: README, CHANGELOG e licenza bilingue, logo e schermate`.

### Task 7: Pubblicazione (controllore)

- [ ] **Controllo prima del push** (Review Focus 5):
  - `git log --all --name-only` non deve contenere file sotto `data/`;
  - una ricerca su tutto il repository non deve trovare token (`ghp_`, `gho_`, `github_pat_`), PIN o file `.db`;
  - controlla la dimensione del repository.
- [ ] `gh repo create iw8ffg/meshlens --private --source . --push`, poi `git push --tags`.
- [ ] Crea il tag `v1.0.0` su `main` ed esegui `git push origin v1.0.0`. Controlla l'esito di Actions e che gli asset della release esistano.
- [ ] Scarica l'installer dalla release, controlla lo SHA-256 e installalo **in locale con la conferma dell'utente**. Poi verifica:
  - l'avvio dal menu Start e l'icona di notifica;
  - l'interfaccia;
  - "Controlla ora" con il token dell'utente, che inserisce lui stesso, e la risposta "nessun aggiornamento";
  - la disinstallazione, che lascia i dati.
- [ ] Il collaudo dell'aggiornamento vero si fa con la release 1.0.1 di prova (Task 8).

### Task 8: Prova di aggiornamento e prove con le radio (alla fine, con l'utente)

- [ ] Pubblica una `v1.0.1` di prova, con solo il CHANGELOG cambiato. Dall'app 1.0.0 la si trova, si scarica e si installa; l'app si riavvia in 1.0.1 e i dati restano (Review Focus 4).
- [ ] Sessione di prove con le radio vere: le liste dell'ultimo task dei piani delle fasi 2–6.

---

**Esecuzione:** i Task 1→2→3 (server) e il 4 (interfaccia, in un worktree) procedono in parallelo; il 6 (documentazione) in parallelo al 3. Il 5 si fa dopo che 1–4 sono stati uniti; il 7 e l'8 alla fine. Ramo `fase7`, creato da `main`.
