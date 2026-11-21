# MeshLens Fase 11 — Interventi rapidi sull'interfaccia e strumenti mappa: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:** togliere i vicoli ciechi dell'interfaccia e dare alla mappa gli strumenti da campo. Avviso «connessione persa», filtri attivi visibili con «Azzera filtri», «Riprova» e suggerimenti negli stati vuoti o di errore, distanze e azioni nei popup, ordinamento e ricerca in Nodi, vista ricordata con link diretti ai nodi, avvisi nuovi sui dati già raccolti, poi righello, ricerca sulla mappa, «Dove sono» e raggruppamento disattivabile. Sono le proposte A1, A2, A3, A5, A6, A7, A8 e B13 di `docs/superpowers/research/2026-11-21-proposte-prossima-release.md`. A4 è già fatta nella fase 9 e non va rifatta.

**Architettura:**
- **Logica pura in moduli nuovi di `web/src/lib/`**, ognuno con il suo test vitest: `connection.svelte.ts`, `distance.ts`, `clipboard.ts`, `nodesort.ts`, `route.ts`, `viewstate.ts`, `alerts.ts`, `shell/navigate.ts`, `map/ruler.ts`, `map/search.ts`, `map/geolocate.ts`. I componenti fanno solo da collante.
- **Interfaccia nuova in componenti nuovi** (`lib/shell/ConnectionBar.svelte`, `components/ActiveFilters.svelte`, `components/NodeSortBar.svelte`, `lib/shell/AlertsList.svelte`, `lib/map/MapSearch.svelte`, `lib/map/RulerBar.svelte`, layer `lib/map/RulerLayer.ts` e `lib/map/MeLayer.ts`). Così si riducono al minimo i conflitti con la fase 10, che procede in parallelo.
- **Server:** cambiano solo `alerts.py` (tre tipi nuovi di avviso), `store.py` (una query aggregata sulla telemetria) e `AppContext.alerts()` in `api.py`. Niente impostazioni nuove: le soglie sono costanti in `alerts.py`, perché `settings.py` è toccato dalla fase 10.
- **Navigazione:** l'hash `#/<scheda>` o `#/nodes/!xxxxxxxx` si scrive con `history.replaceState`, senza riempire la cronologia, e si legge all'avvio e a ogni `hashchange`. Il resto della vista (scheda, centro e zoom della mappa, ultima conversazione, ordinamenti, raggruppamento) va in localStorage sotto una chiave sola, `meshlens.view`.

**Tech Stack:** Svelte 5 (runes) + Vite + vitest, MapLibre GL 6 (`GeoJSONSource.setClusterOptions`), API del browser `navigator.geolocation` e `navigator.clipboard`; Python 3 + FastAPI + sqlite3.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md`. Proposte: `docs/superpowers/research/2026-11-21-proposte-prossima-release.md` (A1, A2, A3, A5, A6, A7, A8, B13). Restano valide le Global Constraints della fase 8 (`docs/superpowers/plans/2026-11-21-meshlens-fase8-design-invio.md`) e della fase 9 (`docs/superpowers/plans/2026-11-21-meshlens-fase9-fondamenta.md`).

## Global Constraints

- Valgono tutte le Global Constraints delle fasi 8 e 9:
  - italiano; `Intl` `it-IT`; il meno tipografico «−»;
  - **nessun colore fuori dai token** (`var(--…)` di `tokens.css`; per i layer MapLibre `readDocumentTokens()`);
  - testo ≥ 14 px e aree toccabili ≥ 44 px su telefono (`.vp-phone`, `max-width: 820px`); focus sempre visibile;
  - **nessuna risorsa esterna a runtime** (icone importate una per una da `@lucide/svelte` in `lib/ui/icons.ts`);
  - Svelte 5: nessun `$effect` legge e scrive lo stesso `$state`; timer e listener puliti; l'effetto WebSocket e dati di `App.svelte` non segue stati nuovi (leggere con `untrack`).
- **Nessuna dipendenza nuova** in `pyproject.toml` né in `web/package.json`.
- **Contratti JSON solo additivi:** l'avviso guadagna i `kind` nuovi e un campo facoltativo `detail`; nessun campo esistente cambia.
- **Mappa:** marker come layer, nessun elemento HTML per nodo. I layer nuovi (righello, «Dove sono») vengono ricreati in `setup()` dopo ogni `setStyle`, come gli altri.
- **«Miei nodi» negli avvisi:** come oggi, gli avvisi nascono solo per i nodi con `is_mine` vero.
- **Nessun cambio di versione** (né `pyproject.toml` né `web/package.json` né `__init__.py`).
- **Fase 10 in parallelo** (più broker MQTT, canali personalizzati, favicon). Non toccare:
  - la sezione MQTT di `Settings.svelte`;
  - il compositore di `Chat.svelte`;
  - lo stato MQTT di `TopBar.svelte`;
  - `server/meshlens/settings.py` e i moduli `mqtt_*`.
  
  File condivisi che questa fase tocca, sempre in punti piccoli e dichiarati:
  - `App.svelte`;
  - `TopBar.svelte` (solo il blocco del popover avvisi);
  - `Chat.svelte` (solo lo stato vuoto della lista radio e un `$effect` di una riga);
  - `stores.svelte.ts` (solo funzioni aggiunte in fondo);
  - `lib/ui/icons.ts` (solo righe aggiunte);
  - `lib/types.ts` (solo il tipo `Alert`);
  - `api.py` (solo `AppContext.alerts`).
- Test: `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q` dalla radice del worktree; `cd web && npx vitest run`. Anche `cd web && npm run check` (svelte-check) deve restare senza errori. I test esistenti restano verdi.
- Commit in italiano, stile `feat(web): …` / `feat(server): …` / `fix: …`.

## Contratti JSON (aggiunte)

- `Alert.kind` aggiunge `"chutil_high"`, `"back_online"` e `"firmware_old"`:
  - `chutil_high`: `value` = media di `channel_util` negli ultimi 30 minuti, con una cifra decimale;
  - `back_online`: `value` = ore di silenzio prima del ritorno (intero);
  - `firmware_old`: `value` = 0 e `detail` = la versione letta, per esempio `"2.3.2.63df972"`.
- Chiavi: `chutil:<id>`, `online:<id>`, `firmware:<id>`.
- Ordine dell'elenco: `battery_low`, `silent`, `chutil_high`, `firmware_old`, `back_online`; a parità di tipo, per nome.
- localStorage `meshlens.view` (versione 1):

  ```json
  {"v":1,"tab":"nodes","map":{"lon":12.5,"lat":42.5,"zoom":5},"conv":"mqtt","netSort":{"key":"last_heard","dir":"desc"},"nodeSort":"recent","cluster":true}
  ```

  Ogni campo è facoltativo; un campo non valido torna al valore predefinito.
- Hash: `#/map`, `#/nodes`, `#/network`, `#/coverage`, `#/chat`, `#/radio`, `#/settings`, `#/nodes/!xxxxxxxx`.

## Review Focus

1. **Server riavviato o rete Wi-Fi caduta mentre il telefono è sulla mappa:**
   - la barra «Connessione persa» compare entro 3 s dalla chiusura del WebSocket e non lampeggia nelle riconnessioni rapide;
   - «Riprova ora» ritenta subito;
   - al ritorno compare «Connessione ripristinata» e i dati si ricaricano (`reconnected` → `load`).
   
   → Task 1.
2. **Link diretto a un nodo che non c'è** (id malformato, nodo mai sentito, oppure nodi non ancora caricati all'apertura):
   - con un id malformato niente eccezioni e si resta sulla scheda predefinita;
   - con un nodo mai sentito compare il messaggio «Nodo !xxxxxxxx non trovato»;
   - se il nodo c'è ma arriva dopo l'apertura, viene selezionato appena arriva, una volta sola.
   
   → Task 6.
3. **«Dove sono» e «Copia» dal telefono via rete locale in HTTP** (contesto non sicuro):
   - `navigator.geolocation` e `navigator.clipboard` non sono disponibili;
   - serve un messaggio chiaro («La posizione del browser richiede HTTPS: attivalo in Impostazioni → Rete») e la copia ricade su `document.execCommand('copy')`;
   - nessun errore non gestito.
   
   → Task 4 e Task 10.
4. **Unico nodo seguito fuori dall'Italia, filtro predefinito su IT:** il nodo mio e la radio locale restano visibili su mappa ed elenco; se non resta niente di visibile, la mappa mostra «Nessun nodo con i filtri attivi» con «Azzera filtri». → Task 2.
5. **Cambio di tema o di modalità della mappa con righello attivo e raggruppamento spento:** dopo `setStyle` il righello e il punto «Dove sono» riappaiono, il raggruppamento resta spento e i clic sui nodi restano disattivati finché il righello è attivo. → Task 9 e Task 10.

---

### Task 1: Avviso «connessione persa» (A1)  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/connection.svelte.ts`, `web/src/lib/connection.test.ts`, `web/src/lib/shell/ConnectionBar.svelte`
- Modify: `web/src/lib/ws.ts`, `web/src/lib/ws.test.ts`, `web/src/App.svelte` (import e una riga di markup tra `<TopBar>` e `.main`, più il passaggio di `connection` a `connectWS`)

**Interfaces:**
- Consumes: `connectWS`, `dispatch` e `WSHandlers` (fase 9, `ws.ts`).
- Produces:
  - `ws.ts`:
    - `WSHandlers.connection?(online: boolean): void`: `true` a ogni `onopen`, `false` a ogni `onclose` diverso da 4401 e da una chiusura voluta;
    - `export function reconnectNow(): void`: se c'è un tentativo in attesa annulla il timer e apre subito; altrimenti non fa nulla;
    - `RECONNECT_MS` resta 3000.
  - `connection.svelte.ts`:
    - `export const conn = $state({ online: true, lostAt: null as number | null, attempts: 0, restoredAt: null as number | null })`;
    - `markOnline(now: number): void`: se era offline imposta `restoredAt = now`; azzera `lostAt` e `attempts`;
    - `markOffline(now: number): void`: imposta `lostAt` solo se è null; incrementa `attempts`;
    - `SHOW_AFTER_MS = 3000`, `RESTORED_MS = 4000`;
    - `export function connectionView(c: {online; lostAt; attempts; restoredAt}, nowMs: number, browserOnline: boolean): { show: boolean; tone: 'warn' | 'ok'; text: string; retry: boolean }`.

Testi di `connectionView` (copia esatta):
- offline da meno di 3 s → `show:false`;
- offline da 3 s o più, con `browserOnline` falso → `{show:true, tone:'warn', text:'Il dispositivo è offline: i dati sono fermi', retry:false}`;
- offline da 3 s o più, con `browserOnline` vero → `text: 'Connessione al server persa: i dati sono fermi dalle HH:MM. Nuovo tentativo in corso…'`, `retry:true` (HH:MM con `Intl.DateTimeFormat('it-IT', {hour:'2-digit', minute:'2-digit'})` di `lostAt`);
- online con `restoredAt` entro 4 s → `{show:true, tone:'ok', text:'Connessione ripristinata', retry:false}`;
- negli altri casi `show:false`.

`ConnectionBar.svelte`:
- è una striscia nel flusso del layout (non sovrapposta: spinge giù la mappa solo mentre è visibile) con `role="status"` e `aria-live="polite"`;
- sfondo `--warn-soft` o `--ok-soft`, testo `--ink`, icona `cloudoff` o `check`;
- pulsante «Riprova ora» (≥ 44 px su telefono) che chiama `reconnectNow()`;
- un `setInterval` da 1 s gira **solo** mentre `!conn.online || conn.restoredAt` è recente, per ricalcolare la vista; si pulisce nel cleanup dell'effetto;
- legge `navigator.onLine` e ascolta `online`/`offline` di `window`.

In `App.svelte`, nell'oggetto passato a `connectWS`: `connection: (on) => (on ? markOnline(Date.now()) : markOffline(Date.now()))`. Nessuno stato nuovo letto dall'effetto.

- [ ] **Step 1: test che falliscono.**
  - `connection.test.ts`: i cinque casi di `connectionView` qui sopra, con valori fissi (`lostAt = Date.UTC(...)`); confrontare il testo con l'orario prodotto dallo stesso `Intl`. Poi `markOffline` chiamata due volte → `attempts == 2` e `lostAt` invariato; `markOnline` dopo un `markOffline` → `restoredAt` impostato e `attempts == 0`.
  - `ws.test.ts`, con un `FakeWebSocket` passato a `vi.stubGlobal('WebSocket', …)` e `location` stub:
    - `connectWS` → `onopen` → `connection(true)`;
    - `onclose({code:1006})` → `connection(false)`;
    - `onclose({code:4401})` → nessuna chiamata a `connection(false)`;
    - con timer finti, dopo una chiusura `reconnectNow()` crea subito un secondo WebSocket, prima dei 3000 ms;
    - dopo la funzione di chiusura restituita da `connectWS`, `reconnectNow()` non apre nulla.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/connection.test.ts src/lib/ws.test.ts` → FAIL.
- [ ] **Step 3:** implementare `ws.ts` e `connection.svelte.ts`.
- [ ] **Step 4:** implementare `ConnectionBar.svelte` e inserirla in `App.svelte`.
- [ ] **Step 5:** vitest completo e `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): avviso di connessione persa con riconnessione immediata`.

### Task 2: Filtri attivi visibili, «Azzera filtri», nodi miei sempre visibili (A2)  _(modello: sonnet)_

**Files:**
- Modify: `web/src/lib/filters.ts`, `web/src/lib/filters.test.ts`, `web/src/components/NodeList.svelte` (stato vuoto), `web/src/components/MapView.svelte` (sovrapposizione «nessun nodo»), `web/src/App.svelte` (passa `total` a MapView, monta `ActiveFilters`)
- Create: `web/src/components/ActiveFilters.svelte`

**Interfaces:**
- Produces in `filters.ts`:
  - `matchNode` cambia così: il filtro **nazione** non si applica ai nodi con `is_mine` o `is_local_radio`. Età, fonte, testo e preferiti si applicano a tutti, come oggi.
  - Il filtro testo cerca anche in `hw_model` e `role` (serve ad A6).
  - `export type ActiveFilter = { key: 'countries' | 'age' | 'sources' | 'text' | 'favorites'; label: string }`.
  - `export function activeFilters(f: NodeFilter, countryName: (code: string) => string): ActiveFilter[]`. Etichette:
    - nazioni: una sola → il suo nome (`'none'` → «Nazione sconosciuta»); più di una → «N nazioni»;
    - età: «Ultimo contatto: 2 h», «24 h» oppure «7 g»;
    - fonte: «Fonte: Radio», «Fonte: MQTT» oppure «Fonte: Radio, MQTT»;
    - testo: «Ricerca: “abc”»;
    - preferiti: «Solo preferiti».
    
    `links` non è un filtro.
  - `export function clearFilter(f: NodeFilter, key: ActiveFilter['key']): NodeFilter`.
  - `export function clearAllFilters(f: NodeFilter): NodeFilter`: `countries: []`, `maxAgeH: null`, `sources: []`, `text: ''`, `favorites: false`; `links` invariato.
- `ActiveFilters.svelte`, props `{ compact?: boolean }`:
  - legge e scrive `app.filter`;
  - mostra «Filtri attivi:», un chip per filtro con la ✕ (`aria-label="Togli filtro <label>"`) e il pulsante «Azzera filtri»;
  - non disegna nulla senza filtri attivi;
  - i nomi delle nazioni li ricava da `/api/countries`, caricata una volta; finché non arrivano mostra il codice.
- `NodeList`: quando l'elenco è vuoto, nello slot `action` di `Empty` va il pulsante «Azzera filtri», ma solo se `activeFilters` non è vuoto.
- `MapView`: prop nuova `total: number` (numero di nodi in `app.nodes`). Se `nodes.length === 0 && total > 0` compare in basso al centro, sopra `.notice`, una scheda con `role="status"`: «Nessun nodo con i filtri attivi» più `<ActiveFilters compact />`.
- `App.svelte`: `<ActiveFilters />` sopra `<NodeList>` nello snippet `screens()` (scheda `nodes`), sotto `<Filters />`.

- [ ] **Step 1: test che falliscono** in `filters.test.ts`:
  - `test('mine and local radio ignore the country filter')`:
    - `{...n, country:'FR', is_mine:true}` con `countries:['IT']` → `true`;
    - lo stesso con `is_local_radio:true` → `true`;
    - lo stesso con `is_mine:true` e `maxAgeH:0.5` (sentito un'ora fa) → `false`.
  - `test('text matches model and role')`: `{...n, hw_model:'HELTEC_V3', role:'ROUTER'}` con `text:'heltec'` → `true`; con `text:'router'` → `true`.
  - `test('activeFilters labels')`: `{countries:['IT'], maxAgeH:24, sources:['rf'], text:'abc', links:true, favorites:true}` con `countryName = c => c === 'IT' ? 'Italia' : c` → le etichette `['Italia', 'Ultimo contatto: 24 h', 'Fonte: Radio', 'Ricerca: “abc”', 'Solo preferiti']`; con `countries:['IT','FR']` la prima diventa `'2 nazioni'`; `defaultFilter` senza nazioni → `[]`.
  - `test('clearAllFilters keeps links')`: risultato `{countries:[], maxAgeH:null, sources:[], text:'', links:true, favorites:false}`.
  - `test('clearFilter removes one')`: `clearFilter(f, 'age').maxAgeH === null`, e gli altri campi restano invariati.
- [ ] **Step 2:** `cd web && npx vitest run src/lib/filters.test.ts` → FAIL.
- [ ] **Step 3:** implementare `filters.ts`.
- [ ] **Step 4:** componenti. L'etichetta della sovrapposizione sulla mappa è ≥ 14 px su telefono; i chip sono `ui-chip` ≥ 44 px.
- [ ] **Step 5:** vitest completo e `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): filtri attivi visibili, Azzera filtri e nodi miei sempre in vista`.

### Task 3: «Riprova» e suggerimenti negli stati di errore o vuoti (A3)  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/shell/navigate.ts`, `web/src/lib/shell/navigate.test.ts`
- Modify: `web/src/App.svelte` (registra il navigatore; «Riprova» sull'errore iniziale), `web/src/components/MessageFeed.svelte`, `web/src/components/Chat.svelte` (**solo** la riga `{#if msgs.length === 0}` della lista radio), `web/src/components/Filters.svelte` (errore nazioni), `web/src/components/NodeDetail.svelte` (errore del percorso)

**Interfaces:**
- Produces in `navigate.ts`, un ponte a callback senza stato reattivo come `chatBridge`:
  - `export function setNavigator(fn: ((t: Tab) => void) | null): void`;
  - `export function navigate(t: Tab): boolean`: `false` se nessun navigatore è registrato.
- `export function emptyFeedHint(mqtt: { connected: boolean } | null, radios: number): { title: string; text: string; action: { label: string; tab: Tab } | null }`, sempre in `navigate.ts`. Casi:
  - MQTT non connesso → `{title:'Nessun messaggio', text:'MQTT non è connesso: controlla broker e argomento.', action:{label:'Apri Impostazioni', tab:'settings'}}`;
  - MQTT connesso → `{title:'Nessun messaggio', text:'Nessun messaggio ricevuto finora con i filtri attuali.', action:null}`.
- `export function emptyRadioHint(connectedRadios: number): {...}`:
  - con 0 radio connesse → `{title:'Nessun messaggio', text:'Collega una radio per leggere e inviare sui canali della tua rete.', action:{label:'Vai a Radio', tab:'radio'}}`;
  - altrimenti `{title:'Nessun messaggio', text:'Ancora nessun messaggio su questa conversazione.', action:null}`.

Interventi:
- **`App.svelte`:**
  - `onMount` → `setNavigator(goTab)`; nel cleanup `setNavigator(null)`;
  - per `error` (server non raggiungibile), al posto del solo testo: `Empty` con icona `cloudoff`, titolo «Server non raggiungibile», testo «MeshLens potrebbe essere chiuso o in riavvio.» e il pulsante «Riprova» che chiama `refresh()`;
  - finché c'è l'errore, un nuovo tentativo automatico ogni 5 s: timer in un `$effect` che legge solo `error` e chiama `refresh`, che scrive `auth`/`error` in modo asincrono. Va pulito nel cleanup.
- **`MessageFeed.svelte`:**
  - l'errore «Messaggi non disponibili» diventa un Banner con l'azione «Riprova», che rilancia il caricamento iniziale (estratto in una funzione `loadFirst()`);
  - lo stato vuoto usa `emptyFeedHint(app.status?.mqtt ?? null, app.radios.length)` e il pulsante chiama `navigate(action.tab)`;
  - quando ci sono messaggi nascosti dal filtro, accanto a «N messaggi nascosti» compare il pulsante «Mostra tutti» (`app.feedFilter.countries = []`, `includeUnknown = true`).
- **`Chat.svelte`:** solo l'`Empty` della lista radio usa `emptyRadioHint(app.radios.filter(r => r.state === 'connected').length)`.
- **`Filters.svelte`:** «Elenco nazioni non disponibile» con il pulsante «Riprova».
- **`NodeDetail.svelte`:** «Percorso non disponibile» con il pulsante «Riprova» (`toggleTrack`).

- [ ] **Step 1: test che falliscono** in `navigate.test.ts`:
  - `navigate('chat')` senza registrazione → `false`; dopo `setNavigator(fn)` → `true` e `fn` chiamata con `'chat'`;
  - `emptyFeedHint({connected:false}, 0).action?.tab === 'settings'`; `emptyFeedHint(null, 0)` è come non connesso; `emptyFeedHint({connected:true}, 0).action === null`;
  - `emptyRadioHint(0).action?.tab === 'radio'`; `emptyRadioHint(1).action === null`.
- [ ] **Step 2:** `npx vitest run src/lib/shell/navigate.test.ts` → FAIL.
- [ ] **Step 3:** implementare `navigate.ts`.
- [ ] **Step 4:** applicare gli interventi nei componenti.
- [ ] **Step 5:** vitest completo e `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): Riprova e suggerimenti negli stati vuoti e di errore`.

### Task 4: Distanze e azioni nei popup della mappa (A5)  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/distance.ts`, `web/src/lib/distance.test.ts`, `web/src/lib/clipboard.ts`, `web/src/lib/clipboard.test.ts`, `web/src/lib/geopos.svelte.ts`
- Modify: `web/src/lib/map/NodePopup.svelte`, `web/src/components/MapView.svelte`, `web/src/App.svelte` (prop `onpick` a MapView)

**Interfaces:**
- Produces in `distance.ts`:
  - `export function haversineM(a: {lat:number; lon:number}, b: {lat:number; lon:number}): number`, con raggio terrestre `6_371_000`;
  - `export function bearingDeg(a, b): number` (0–360, rispetto al nord);
  - `export function cardinal(deg: number): string`, otto settori `['N','NE','E','SE','S','SO','O','NO']`;
  - `export type Origin = { lat: number; lon: number; label: string }`;
  - `export function myOrigin(nodes: Map<string, Node>, radios: Radio[], browser: {lat:number; lon:number} | null): Origin | null`. Priorità:
    1. il nodo `my_node_id` della prima radio `connected` che ha una posizione → label «dalla radio <nome radio>»;
    2. un qualsiasi nodo con `is_local_radio` e una posizione → «dalla tua radio»;
    3. la posizione del browser → «dalla tua posizione»;
    4. altrimenti `null`.
  
  Il formato delle distanze riusa `formatMeters` di `geo.ts`.
- Produces in `geopos.svelte.ts`: `export const geopos = $state({ pos: null as { lat: number; lon: number; accuracy: number; time: number } | null })`. Lo scrive il Task 10; qui è letto da `myOrigin`.
- Produces in `clipboard.ts`: `export async function copyText(text: string, nav: Pick<Navigator, 'clipboard'> | null = navigator, doc: Document | null = document): Promise<boolean>`.
  - Con `window.isSecureContext` e `nav.clipboard` usa `writeText`.
  - Altrimenti usa una `textarea` temporanea con `doc.execCommand('copy')`, rimossa sempre.
  - Ritorna `false` senza lanciare eccezioni.
- `NodePopup.svelte`, prop aggiunta: `actions?: { label: string; icon: IconName; onclick: () => void | Promise<void>; disabled?: boolean }[]`. Le azioni vanno in una riga di pulsanti sotto le righe (≥ 44 px su telefono, ≥ `--control-h-desktop` su desktop). Dopo un `onclick` che restituisce `true` compare per 2 s l'etichetta «Copiato» (`role="status"`).
- `MapView.svelte`, prop nuova `onpick: (id: string) => void`, che è il `pickId` di App. Nel popup del nodo:
  - riga «Distanza», `${formatMeters(d)} ${origin.label}`, solo con origine e posizione note e se il nodo non è l'origine stessa;
  - azioni:
    - «Messaggio diretto» (icona `send`), solo se c'è una radio connessa: `openChat('dm:<radio>:<id>')` + `navigate('chat')` + chiusura del popup;
    - «Dettagli» (icona `info`): `onpick(id)` + chiusura;
    - «Copia id» (icona `copy`): `copyText(id)`;
    - «Copia coordinate» (icona `pin`): `copyText(`${lat.toFixed(5)}, ${lon.toFixed(5)}`)`, solo se c'è una posizione.
  
  Nel popup del collegamento: riga «Lunghezza» = `formatMeters(haversineM(a, b))` fra le due estremità, letta da `app.nodes`.

- [ ] **Step 1: test che falliscono.**
  - `distance.test.ts`:
    - `haversineM({lat:45.4642, lon:9.19}, {lat:41.9028, lon:12.4964})` tra 476 000 e 478 000 (Milano–Roma ≈ 477 km);
    - `haversineM(p, p) === 0`;
    - `bearingDeg({lat:0,lon:0}, {lat:1,lon:0})` ≈ 0 e `({lat:0,lon:0}, {lat:0,lon:1})` ≈ 90;
    - `cardinal(350) === 'N'`, `cardinal(225) === 'SO'`;
    - `myOrigin`: la radio connessa con il nodo posizionato vince sul browser; la radio connessa con il nodo senza posizione e il browser presente → label `'dalla tua posizione'`; niente di tutto ciò → `null`.
  - `clipboard.test.ts`:
    - con `nav.clipboard.writeText` finto e `isSecureContext` vero → `true` e testo passato;
    - con `nav = null` e un `doc` finto il cui `execCommand` ritorna `true` → `true`, e la textarea è rimossa;
    - con `execCommand` che lancia → `false`.
- [ ] **Step 2:** `npx vitest run src/lib/distance.test.ts src/lib/clipboard.test.ts` → FAIL.
- [ ] **Step 3:** implementare `distance.ts`, `clipboard.ts` e `geopos.svelte.ts`.
- [ ] **Step 4:** collegare `NodePopup.svelte` e `MapView.svelte`. In `openPopup` le azioni restano callback props del componente montato. Il popup si chiude con `popup?.remove()`.
- [ ] **Step 5:** vitest completo e `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): distanze e azioni rapide nei popup della mappa`.

### Task 5: Ordinamento e ricerca in Nodi (A6)  _(modello: haiku)_

**Files:**
- Create: `web/src/lib/nodesort.ts`, `web/src/lib/nodesort.test.ts`, `web/src/components/NodeSortBar.svelte`
- Modify: `web/src/components/NodeList.svelte`, `web/src/components/Filters.svelte` (segnaposto «Cerca nome, id, modello o ruolo…»), `web/src/App.svelte` (stato `nodeSort` e passaggio delle props)

**Interfaces:**
- Consumes: `haversineM`, `myOrigin`, `Origin` (Task 4); ricerca su modello e ruolo già in `matchNode` (Task 2).
- Produces:
  - `export type NodeSortKey = 'recent' | 'name' | 'snr' | 'hops' | 'distance'`;
  - `export const NODE_SORTS: { key: NodeSortKey; label: string }[]`, con le etichette «Recenti», «Nome», «SNR», «Salti», «Distanza»;
  - `export function sortNodeList(nodes: Node[], key: NodeSortKey, origin: Origin | null): Node[]`. Non modifica l'input; i valori mancanti vanno sempre in fondo; a parità si ordina per `compareLastHeard`. Criteri:
    - `recent` = `compareLastHeard`;
    - `name` = `nodeName` con `localeCompare(…, 'it')`;
    - `snr` decrescente;
    - `hops` crescente (usa `hops`, poi `hops_min`);
    - `distance` crescente da `origin`; senza origine equivale a `recent`.
- `NodeSortBar.svelte`, props `{ value: NodeSortKey; hasOrigin: boolean; onchange: (k: NodeSortKey) => void }`:
  - un `Select` (componente `lib/ui/Select.svelte`) con etichetta «Ordina per»;
  - «Distanza» è disattivata senza origine, con il testo d'aiuto «Serve la posizione della tua radio o del browser».
- `NodeList.svelte`: props aggiunte `sort: NodeSortKey` e `origin: Origin | null`. Usa `sortNodeList`. Con `sort === 'distance'` mostra la distanza (`formatMeters`) al posto dei salti nella colonna dei valori.
- `App.svelte`: `let nodeSort = $state<NodeSortKey>('recent')`; `origin = $derived(myOrigin(app.nodes, app.radios, geopos.pos))`. La persistenza arriva nel Task 6.

- [ ] **Step 1: test che falliscono** in `nodesort.test.ts`:
  - `sortNodeList` per `name` con `['b', 'À', 'a']` → `['a', 'À', 'b']` (collazione `it`);
  - per `snr`, `[-5, null, 3]` → `[3, -5, null]`;
  - per `hops`, `[{hops:2}, {hops:null, hops_min:1}, {hops:0}]` → `[0, ≥1, 2]`;
  - per `distance` con l'origine Milano: Monza prima di Roma; il nodo senza posizione in fondo; con `origin = null` lo stesso ordine di `recent`;
  - l'array di input resta invariato (`toEqual` sulla copia).
- [ ] **Step 2:** `npx vitest run src/lib/nodesort.test.ts` → FAIL.
- [ ] **Step 3:** implementare `nodesort.ts`.
- [ ] **Step 4:** implementare i componenti.
- [ ] **Step 5:** vitest completo e `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): ordinamento dei nodi per recente, nome, SNR, salti e distanza`.

### Task 6: Vista ricordata e link diretti ai nodi (A7)  _(modello: opus)_

**Files:**
- Create: `web/src/lib/route.ts`, `web/src/lib/route.test.ts`, `web/src/lib/viewstate.ts`, `web/src/lib/viewstate.test.ts`
- Modify: `web/src/App.svelte`, `web/src/components/MapView.svelte` (centro e zoom iniziali, salvataggio a `moveend`), `web/src/components/Network.svelte` (ordinamento iniziale e salvato), `web/src/components/Chat.svelte` (**solo** un `$effect(() => rememberConv(conv))`), `web/src/lib/stores.svelte.ts` (aggiunge `rememberConv` in fondo), `web/src/components/NodeDetail.svelte` (pulsante «Copia link»)

**Interfaces:**
- Consumes: `copyText` (Task 4); `NodeSortKey` (Task 5); `SortKey` di `network.ts`; `openChat` e `attachChat` di `stores.svelte.ts`.
- Produces in `route.ts`:
  - `export type Route = { tab: Tab | null; nodeId: string | null }`;
  - `export function parseHash(hash: string): Route`. Accetta `#/<tab>` per le schede di `Tab` tranne `more`, e `#/nodes/<id>` con id `^!?[0-9a-fA-F]{8}$`, normalizzato in `!` + minuscole. In quel caso il risultato è `{tab:'nodes', nodeId}`. Tutto il resto dà `{tab:null, nodeId:null}`.
  - `export function formatHash(r: Route): string` (`nodeId` vince: `#/nodes/!xxxxxxxx`; `tab:null` → `''`);
  - `export function nodeLink(id: string, loc: Pick<Location, 'origin' | 'pathname'>): string`, cioè `origin + pathname + '#/nodes/' + id`.
- Produces in `viewstate.ts`:
  - `VIEW_KEY = 'meshlens.view'`;
  - `export type ViewState = { tab: Tab | null; map: { lon: number; lat: number; zoom: number } | null; conv: string | null; netSort: { key: SortKey; dir: 'asc' | 'desc' } | null; nodeSort: NodeSortKey; cluster: boolean }`;
  - `export function loadView(storage: Pick<Storage, 'getItem'> | null): ViewState`. Valori predefiniti: `tab:null`, `map:null`, `conv:null`, `netSort:null`, `nodeSort:'recent'`, `cluster:true`. Una `lat` fuori da ±85 o una `lon` fuori da ±180, uno zoom fuori da 0–22, un `tab` sconosciuto o un `v` diverso da 1 tornano al predefinito campo per campo. Un JSON rotto restituisce tutti i predefiniti.
  - `export function saveView(storage: Pick<Storage, 'getItem' | 'setItem'> | null, patch: Partial<ViewState>): void`: legge, unisce, scrive `{v:1, ...}`; ignora gli errori di storage.
- Produces in `stores.svelte.ts`: `export function rememberConv(key: string): void`, che chiama `saveView(localStorage, { conv: key })`.

Comportamento in `App.svelte`:
- **Scheda iniziale:** `parseHash(location.hash).tab ?? loadView(localStorage).tab ?? (viewport.phone ? 'map' : 'nodes')`. Su desktop `map` e `more` diventano `nodes` (via `effectiveTab`).
- **Hash e vista seguono lo stato:** un `$effect` legge `activeTab` (su telefono `tab`) e `app.selectedId`, poi:
  - `history.replaceState(null, '', formatHash({tab, nodeId: app.selectedId}) || location.pathname)`;
  - `saveView(localStorage, { tab })`.
  
  Non scrive stati reattivi.
- **Hash che cambia dall'esterno:** il listener `hashchange`, registrato in `onMount` e rimosso nel cleanup, applica la route con `applyRoute(r)`. Con `nodeId`: se il nodo è in `app.nodes` chiama `pickId(id)`; altrimenti imposta `pendingNode = id`, una variabile semplice e non `$state`. Con `tab`: `goTab(tab)`.
- **Nodo in attesa:** dentro `load()`, dopo `upsertNodes` della prima lista:
  - se `pendingNode` è in `app.nodes` → `pickId` e `pendingNode = null`;
  - se manca → `getJSON('/nodes/' + id)`; con un 404 compare un `Toast` `warn` «Nodo !xxxxxxxx non trovato» (stato `routeError`) e `pendingNode = null`.
- **Ultima conversazione:** in `onMount`, se `loadView().conv` esiste e non c'è una route con nodo, chiama `openChat(conv)`. La richiesta resta in attesa nel ponte finché Chat non si monta.
- **`nodeSort`:** iniziale da `loadView().nodeSort`; al cambio `saveView(localStorage, { nodeSort })`.
- **`MapView.svelte`:** `new maplibregl.Map({ center, zoom })` usa `loadView(localStorage).map ?? { lon: 12.5, lat: 42.5, zoom: 5 }`. In `onMoveEnd`, già con un ritardo di 250 ms, aggiunge `saveView(localStorage, { map: { lon, lat, zoom } })` con 5 decimali e lo zoom a 2 decimali.
- **`Network.svelte`:** `key` e `dir` iniziali da `loadView().netSort ?? { key: 'last_heard', dir: 'desc' }`; `sortBy` chiama `saveView(localStorage, { netSort: { key, dir } })`.
- **`NodeDetail.svelte`:** pulsante «Copia link» (icona `copy`) accanto alle azioni esistenti: `copyText(nodeLink(node.id, location))`, poi «Link copiato» per 2 s.

- [ ] **Step 1: test che falliscono.**
  - `route.test.ts`:
    - `parseHash('#/nodes/!ABCDEF01')` → `{tab:'nodes', nodeId:'!abcdef01'}`;
    - `parseHash('#/nodes/abcdef01')` → stesso id con `!`;
    - `parseHash('#/nodes/!abc')` → `{tab:null, nodeId:null}`;
    - `parseHash('#/network')` → `{tab:'network', nodeId:null}`;
    - `parseHash('#/more')` e `parseHash('')` → tutto null;
    - `formatHash({tab:'chat', nodeId:null}) === '#/chat'`;
    - `formatHash({tab:'map', nodeId:'!0000abcd'}) === '#/nodes/!0000abcd'`;
    - `nodeLink('!0000abcd', {origin:'http://127.0.0.1:8686', pathname:'/'}) === 'http://127.0.0.1:8686/#/nodes/!0000abcd'`.
  - `viewstate.test.ts`:
    - storage vuoto → predefiniti;
    - giro completo `saveView`/`loadView` su tutti i campi;
    - `saveView(s, {conv:'mqtt'})` dopo `saveView(s, {tab:'chat'})` mantiene entrambi;
    - `map.lat = 120` → `map:null` con gli altri campi validi conservati;
    - `tab:'boh'` → `tab:null`;
    - `'{rotto'` → predefiniti;
    - con uno storage che lancia su `setItem` non c'è nessuna eccezione.
- [ ] **Step 2:** `npx vitest run src/lib/route.test.ts src/lib/viewstate.test.ts` → FAIL.
- [ ] **Step 3:** implementare `route.ts` e `viewstate.ts`.
- [ ] **Step 4:** collegare `App.svelte`, MapView, Network, Chat, `stores.svelte.ts` e NodeDetail come descritto. Controllare a mano: aprire `http://127.0.0.1:8686/#/nodes/<id di un nodo demo>` → nodo selezionato e mappa centrata; ricaricare su Rete con l'ordinamento per SNR → stessa scheda e stesso ordinamento.
- [ ] **Step 5:** vitest completo e `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): vista ricordata e link diretti ai nodi`.

### Task 7: Avvisi nuovi sul server — canale saturo, nodo tornato, firmware vecchio (A8)  _(modello: sonnet)_

**Files:**
- Modify: `server/meshlens/alerts.py`, `server/meshlens/store.py`, `server/meshlens/api.py` (**solo** `AppContext.alerts`)
- Test: `server/tests/test_alerts.py`, `server/tests/test_store.py`, `server/tests/test_api.py`

**Interfaces:**
- Produces in `alerts.py`:
  - costanti: `CHUTIL_ALERT_PCT = 25.0`, `CHUTIL_WINDOW_S = 1800`, `CHUTIL_MIN_SAMPLES = 2`, `BACK_ONLINE_KEEP_S = 3600`, `FIRMWARE_MIN = (2, 5, 0)`, `KIND_ORDER = {"battery_low": 0, "silent": 1, "chutil_high": 2, "firmware_old": 3, "back_online": 4}`;
  - `parse_firmware(v: str | None) -> tuple[int, int, int] | None`: prime tre parti numeriche di `"2.3.2.63df972"`; `None` se il valore manca o non si legge;
  - `compute_alerts(nodes, settings, now, previous, chutil: dict[str, float] | None = None) -> list[dict]`. La firma esistente resta compatibile: `chutil` è facoltativo e i test attuali passano invariati. Per i nodi `is_mine`:
    - `chutil_high` se `chutil.get(id)` ≥ `CHUTIL_ALERT_PCT`; `value = round(avg, 1)`;
    - `firmware_old` se `parse_firmware(n["firmware"]) < FIRMWARE_MIN`; `value = 0`, `detail = n["firmware"]`;
    - `back_online`: se `previous` contiene `silent:<id>` e il nodo ora non è più silenzioso, nasce `online:<id>` con `since = now` e `value = previous["silent:<id>"]["value"]`. Se `previous` contiene già `online:<id>` e `now - since < BACK_ONLINE_KEEP_S`, l'avviso si conserva con lo stesso `since` e lo stesso `value`. Se il nodo torna silenzioso, l'avviso `online` sparisce.
  - Ordinamento: `(KIND_ORDER[kind], node_name)`.
  - `detail` c'è **solo** in `firmware_old`.
- Produces in `store.py`: `Store.channel_util_stats(nums: list[int], since: float) -> dict[int, tuple[float, int]]`. È una sola query `SELECT node_num, AVG(channel_util), COUNT(channel_util) … WHERE node_num IN (…) AND time >= ? AND channel_util IS NOT NULL GROUP BY node_num`. Con `nums` vuoto restituisce `{}` senza query. Usa `idx_telemetry_node_time`.
- `AppContext.alerts()`:
  - raccoglie i nodi miei da `self.live.nodes`;
  - `stats = self.store.channel_util_stats(nums, now - CHUTIL_WINDOW_S)`;
  - `chutil = {id: avg}` solo per `count >= CHUTIL_MIN_SAMPLES`;
  - passa `chutil` a `compute_alerts`.
  
  Il confronto per pubblicare sul WS resta su `(key, value)`.

- [ ] **Step 1: test che falliscono.**
  - `test_alerts.py`:
    - `test_chutil_high_only_for_mine_and_threshold`: `chutil={'!00000001': 31.26, '!00000002': 40}` con il nodo 2 non mio → un solo avviso `chutil_high` con `value == 31.3`; con `24.9` nessun avviso;
    - `test_firmware_old`: `firmware='2.3.2.63df972'` → `firmware_old` con `detail == '2.3.2.63df972'`; `'2.5.0.abc'` → nessuno; `None` e `'boh'` → nessuno;
    - `test_parse_firmware`: `parse_firmware('2.6.11.60ec05e') == (2, 6, 11)`, `parse_firmware('2.5') is None`;
    - `test_back_online_after_silent`: primo calcolo con `last_heard = NOW - 7*3600` → `silent`; secondo calcolo con `last_heard = NOW + 60`, a `NOW + 120` e con `previous` dal primo → `back_online` con `value == 7` e `since == NOW + 120`, nessun `silent`; terzo a `NOW + 120 + 3599` → ancora presente con lo stesso `since`; a `NOW + 120 + 3601` → sparito;
    - `test_back_online_not_without_previous_silent`: nodo sentito ora, `previous` vuoto → niente `back_online`;
    - `test_kind_order`: un nodo con batteria bassa, uno silenzioso, uno con canale saturo, uno con firmware vecchio → i `kind` in quest'ordine.
  - `test_store.py`: `test_channel_util_stats`: tre righe di telemetria per il nodo 1 (10, 20, `NULL`) dentro la finestra e una fuori → `{1: (15.0, 2)}`; `nums = []` → `{}`.
  - `test_api.py`: `test_alerts_include_chutil_for_mine`: nodo mio in `live`, due righe di telemetria con `channel_util` 30 e 34 negli ultimi 10 minuti → `GET /api/alerts` contiene `kind == 'chutil_high'` con `value == 32.0`.
- [ ] **Step 2:** `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q server/tests/test_alerts.py server/tests/test_store.py` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** suite pytest completa → PASS.
- [ ] **Step 5: Commit** `feat(server): avvisi per canale saturo, nodo tornato online e firmware vecchio`.

### Task 8: Elenco avvisi nell'interfaccia (A8)  _(modello: haiku)_

**Files:**
- Create: `web/src/lib/alerts.ts`, `web/src/lib/alerts.test.ts`, `web/src/lib/shell/AlertsList.svelte`
- Modify: `web/src/lib/types.ts` (solo `Alert`), `web/src/lib/nodes.ts` (`alertText` delega), `web/src/lib/shell/TopBar.svelte` (**solo** il contenuto del popover `.pop.alerts`, la funzione locale `alertText` e il tono del pulsante), `web/src/components/Network.svelte` (tono dei Banner)

**Interfaces:**
- Consumes: i contratti JSON del Task 7.
- Produces:
  - `types.ts`: `Alert.kind: 'battery_low' | 'silent' | 'chutil_high' | 'back_online' | 'firmware_old'`, più `detail?: string`.
  - `alerts.ts`:
    - `export function alertLabel(a: Pick<Alert, 'kind' | 'value' | 'detail'>): string`, con questi testi:
      - `battery_low` → «Batteria al 12%»;
      - `silent` → «Silenzioso da 30 h»;
      - `chutil_high` → «Canale occupato al 31,3% (media 30 min)»;
      - `back_online` → «Di nuovo online dopo 7 h»;
      - `firmware_old` → «Firmware vecchio (2.3.2)», cioè le prime tre parti di `detail`;
      - un `kind` sconosciuto → «Avviso».
    - `export function alertTone(kind: string): 'warn' | 'ok'` (`back_online` → `ok`);
    - `export function alertIcon(kind: string): IconName` (`battery`, `clock`, `bars`, `check`, `alert`).
  - `nodes.ts`: `alertText` resta esportata e restituisce `alertLabel(a)`, così i test esistenti restano invariati (cambiano solo i casi nuovi).
  - `AlertsList.svelte`, props `{ alerts: Alert[]; onpick: (nodeId: string) => void }`:
    - elenco di pulsanti ≥ 44 px, con icona colorata `--warn` o `--ok` e testo `<alertLabel> — <node_name>`;
    - sotto ogni voce, «da <ago(since)>» in `--ink-muted` e ≥ 14 px su telefono.
  - `TopBar.svelte`:
    - il popover avvisi contiene solo `<AlertsList alerts={app.alerts} onpick={…chiude e chiama onpickalert} />`;
    - la classe `warn` del pulsante si applica solo se almeno un avviso ha `alertTone === 'warn'`.
  - `Network.svelte`: `Banner kind={alertTone(a.kind)}`.

- [ ] **Step 1: test che falliscono** in `alerts.test.ts`:
  - i sei testi di `alertLabel` qui sopra (`chutil_high` con `value: 31.3` → `'Canale occupato al 31,3% (media 30 min)'`);
  - `alertTone('back_online') === 'ok'`, `alertTone('silent') === 'warn'`;
  - `alertIcon('chutil_high') === 'bars'`.
- [ ] **Step 2:** `npx vitest run src/lib/alerts.test.ts` → FAIL.
- [ ] **Step 3:** implementare.
- [ ] **Step 4:** vitest completo, compresi i test esistenti di `nodes.test.ts`, e `npm run check` → PASS.
- [ ] **Step 5: Commit** `feat(web): elenco avvisi con i nuovi tipi e il tono giusto`.

### Task 9: Righello e raggruppamento disattivabile (B13)  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/map/ruler.ts`, `web/src/lib/map/ruler.test.ts`, `web/src/lib/map/RulerLayer.ts`, `web/src/lib/map/RulerBar.svelte`
- Modify: `web/src/lib/map/NodeLayer.ts` (parametro `cluster`), `web/src/lib/map/layers.test.ts`, `web/src/lib/map/MapControls.svelte` (secondo gruppo «Strumenti»), `web/src/lib/ui/icons.ts` (aggiunge `ruler` = `@lucide/svelte/icons/ruler` e `cluster` = `@lucide/svelte/icons/boxes`), `web/src/components/MapView.svelte`

**Interfaces:**
- Consumes: `haversineM`, `bearingDeg`, `cardinal` (Task 4); `formatMeters`; `loadView` e `saveView` (Task 6, campo `cluster`).
- Produces:
  - `ruler.ts`:
    - `export type RulerPoint = { lon: number; lat: number; nodeId: string | null }`;
    - `export function addRulerPoint(pts: RulerPoint[], p: RulerPoint): RulerPoint[]`: aggiunge fino a 2 punti; il terzo ricomincia da `[p]`;
    - `export function rulerGeoJSON(pts: RulerPoint[]): FeatureCollection`: un `Point` per punto con `{idx}`, più una `LineString` con 2 punti;
    - `export function rulerText(pts: RulerPoint[], name: (id: string) => string): string`:
      - con 0 punti → «Tocca il primo punto sulla mappa»;
      - con 1 punto → «Tocca il secondo punto»;
      - con 2 punti → «12,3 km · 45° NE» (`formatMeters`, gradi interi, `cardinal`), seguito da « · da A a B» quando entrambi i punti sono nodi.
  - `RulerLayer.ts`: `addRulerLayers(map, t: MapTokens): void`. Sorgente `ruler`, layer `ruler-line` (linea `t.accent`, larghezza 2.5, tratteggio `[2, 1]`) e `ruler-pts` (cerchio di raggio 6, riempimento `t.surfaceRaised`, bordo `t.accent` da 2.5). Va aggiunto **sopra** i nodi, dopo `addCoverageLayers`.
  - `NodeLayer.ts`: `addNodeLayers(map, t, hasGlyphs, cluster = true)`, che passa `cluster` all'`addSource`; `export const CLUSTER_OPTS = { clusterMaxZoom: 7, clusterRadius: 40 }`.
  - `MapControls.svelte`, props aggiunte: `ruler: boolean`, `cluster: boolean`, `onruler: () => void`, `oncluster: () => void`.
    - Secondo gruppo `role="group" aria-label="Strumenti mappa"`, staccato da `--space-2`, con i pulsanti `aria-pressed`: «Righello» e «Raggruppa nodi».
    - Il Task 10 aggiunge qui «Cerca nodo» e «Dove sono».
  - `RulerBar.svelte`, props `{ text: string; onclear: () => void; onclose: () => void }`:
    - scheda in alto a sinistra, con lo stesso stile di `.covbar`; su telefono sotto la barra della copertura, se presente;
    - pulsanti «Ricomincia» e «Chiudi righello».
- **`MapView.svelte`:**
  - `let tool = $state<'none' | 'ruler'>('none')`. Il controllo `if (picking) return` diventa `if (picking || tool !== 'none') return` in tutti i gestori di clic su nodi, collegamenti e copertura.
  - In modalità righello, `map.on('click', rulerHandler)`: se c'è una feature `points*` sotto il punto, aggancia le coordinate e l'`id` del nodo; altrimenti usa `e.lngLat`.
  - Il cursore è `crosshair`. `Escape` (listener su `window` attivo solo col righello) chiude il righello.
  - `setup()` richiama `addRulerLayers` e `pushRuler()`, così il righello sopravvive a `setStyle`.
  - Raggruppamento: `let cluster = $state(loadView(localStorage).cluster)`. Al cambio:
    - `src('nodes')?.setClusterOptions({ cluster, ...CLUSTER_OPTS })`;
    - `saveView(localStorage, { cluster })`.
    
    `setup()` passa `cluster` (letto con `untrack`) ad `addNodeLayers`.
  - Mentre è aperto un popup, attivare il righello chiude il popup.

- [ ] **Step 1: test che falliscono.**
  - `ruler.test.ts`:
    - `addRulerPoint` → 1, 2, poi 1 punto (ricomincia);
    - `rulerGeoJSON` con 2 punti → 3 feature, di cui una `LineString`; con 1 punto → 1 feature;
    - `rulerText` con 0, 1 e 2 punti (Milano→Monza: comincia con `'1'` o `'2'` e contiene `' km · '` e `'N'`); con due nodi termina con `' · da Alfa a Beta'`.
  - `layers.test.ts`: serve una mappa finta minima, da aggiungere nel file: `{ addSource: vi.fn(), addLayer: vi.fn() }` con cast a `MLMap`, e `FALLBACK_TOKENS`. Con `addNodeLayers(m, T, true, false)` la prima chiamata di `addSource` ha `('nodes', objectContaining({ cluster: false }))`; senza il quarto argomento ha `cluster: true`. `addRulerLayers(m, T)` aggiunge i layer con id `ruler-line` e `ruler-pts`.
- [ ] **Step 2:** `npx vitest run src/lib/map/ruler.test.ts src/lib/map/layers.test.ts` → FAIL.
- [ ] **Step 3:** implementare `ruler.ts`, `RulerLayer.ts` e il parametro di `NodeLayer.ts`.
- [ ] **Step 4:** implementare `MapControls`, `RulerBar` e il collegamento in `MapView`.
- [ ] **Step 5:** vitest completo e `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): righello sulla mappa e raggruppamento dei nodi disattivabile`.

### Task 10: Ricerca di un nodo sulla mappa e «Dove sono» (B13)  _(modello: sonnet)_

**Files:**
- Create: `web/src/lib/map/search.ts`, `web/src/lib/map/search.test.ts`, `web/src/lib/map/geolocate.ts`, `web/src/lib/map/geolocate.test.ts`, `web/src/lib/map/MapSearch.svelte`, `web/src/lib/map/MeLayer.ts`
- Modify: `web/src/lib/map/MapControls.svelte`, `web/src/lib/ui/icons.ts` (aggiunge `locate` = `@lucide/svelte/icons/locate-fixed`), `web/src/components/MapView.svelte`

**Interfaces:**
- Consumes: `geopos` (Task 4); `circlePolygon` di `geo.ts`; `MapControls` (Task 9); la prop `onpick` di MapView (Task 4); `nodeName`.
- Produces:
  - `search.ts`: `export function searchNodes(nodes: Iterable<Node>, q: string, limit = 8): Node[]`.
    - Considera solo i nodi con una posizione, cercando fra **tutti** quelli in `app.nodes` (anche se nascosti dai filtri).
    - Confronto senza maiuscole né accenti (`normalize('NFD')`).
    - Punteggio: 0 = id uguale (con o senza `!`); 1 = `short_name` che inizia con la ricerca; 2 = `long_name` che inizia con la ricerca; 3 = `long_name` o `short_name` che la contiene; 4 = `id`, `hw_model` o `role` che la contiene.
    - A parità di punteggio vince il `last_heard` più recente. Una ricerca vuota dopo `trim` dà `[]`.
  - `geolocate.ts`:
    - `export function geoErrorText(code: number | 'insecure' | 'unsupported'): string`. Testi:
      - `'insecure'` → «La posizione del browser richiede HTTPS: attivalo in Impostazioni → Rete, oppure usa MeshLens su questo PC»;
      - `'unsupported'` → «Questo browser non fornisce la posizione»;
      - `1` → «Permesso di posizione negato: consentilo nelle impostazioni del browser»;
      - `2` → «Posizione non disponibile»;
      - `3` → «Posizione non trovata in tempo: riprova all'aperto»;
      - altro → «Posizione non disponibile».
    - `export function locate(geo: Geolocation | undefined, secure: boolean): Promise<{ lat: number; lon: number; accuracy: number; time: number }>`.
      - Rifiuta con `Error(geoErrorText('insecure'))` se `!secure` e con `'unsupported'` se `geo` manca.
      - Altrimenti chiama `getCurrentPosition` con `{ enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }`; un errore diventa `Error(geoErrorText(err.code))`.
  - `MeLayer.ts`:
    - `addMeLayers(map, t: MapTokens): void`: sorgente `me`; layer `me-acc` (riempimento `t.accent` con opacità 0.12) e `me-dot` (cerchio di raggio 7, `t.accent`, bordo `t.outline` da 2);
    - `meData(pos: { lat; lon; accuracy } | null): FeatureCollection`: il punto, più il poligono dell'accuratezza se `accuracy` è tra 1 e 5000 m.
  - `MapSearch.svelte`, props `{ onpick: (id: string) => void; onclose: () => void }`:
    - riquadro in alto a sinistra (su telefono a tutta larghezza meno `--space-3`, sopra `.covbar`), con `input type="search"` dal focus automatico, segnaposto «Cerca un nodo sulla mappa…» ed `aria-label="Cerca un nodo sulla mappa"`;
    - risultati con `role="listbox"`, frecce su/giù, Invio e `Escape`;
    - ogni voce mostra nome, id e un'icona se il nodo è nascosto dai filtri (`!matchNode(n, app.filter, now)`), con il titolo «Nascosto dai filtri»;
    - «Nessun nodo con posizione trovato» se non ci sono risultati.
  - `MapControls.svelte`, props aggiunte: `onsearch: () => void`, `onlocate: () => void`, `locating: boolean`. Pulsanti «Cerca nodo» (icona `search`) e «Dove sono» (icona `locate`, con `spinner` mentre `locating`) nel gruppo «Strumenti».
- **`MapView.svelte`:**
  - `let searchOpen = $state(false)`. Scegliendo un risultato:
    1. `onpick(id)`, che seleziona e mette a fuoco anche se il nodo è filtrato: lo strato `selected` legge da `app.nodes`;
    2. chiusura;
    3. `showNodePopup` sul nodo.
  - «Dove sono»: `locate(navigator.geolocation, window.isSecureContext)` → `geopos.pos = …` → `src('me').setData(meData(pos))` → `easeTo({ center, zoom: max(zoom, 13) })`. Un errore compare in `notice` per 6 s, con un timer pulito.
  - `setup()` richiama `addMeLayers` (sotto il righello, sopra i nodi) e ripubblica `meData(geopos.pos)`.

- [ ] **Step 1: test che falliscono.**
  - `search.test.ts`:
    - `'!a1b2c3d4'` e `'a1b2c3d4'` danno il nodo con quell'id per primo;
    - `'bm'` mette prima `short_name 'BM'` e poi `long_name 'Abm…'`;
    - `'citta'` trova `'Città Alta'`;
    - `'heltec'` trova per `hw_model`;
    - il nodo senza posizione è escluso;
    - `'  '` → `[]`;
    - `limit` viene rispettato.
  - `geolocate.test.ts`:
    - `locate(undefined, true)` rifiuta con il testo `'unsupported'`;
    - `locate(geoFinto, false)` rifiuta con il testo `'insecure'` senza chiamare `getCurrentPosition`;
    - un `geo` finto che chiama il successo con `coords {latitude: 45, longitude: 9, accuracy: 20}` e `timestamp: 1000` → `{lat: 45, lon: 9, accuracy: 20, time: 1000}`;
    - un errore con `code: 1` → il testo «Permesso di posizione negato…»;
    - le opzioni passate contengono `timeout: 10000`.
  - In `layers.test.ts`: `meData(null).features.length === 0`; `meData({lat: 45, lon: 9, accuracy: 50})` → 2 feature; con `accuracy: 9000` → 1.
- [ ] **Step 2:** `npx vitest run src/lib/map/search.test.ts src/lib/map/geolocate.test.ts src/lib/map/layers.test.ts` → FAIL.
- [ ] **Step 3:** implementare `search.ts`, `geolocate.ts` e `MeLayer.ts`.
- [ ] **Step 4:** implementare `MapSearch`, `MapControls` e il collegamento in `MapView`.
- [ ] **Step 5:** vitest completo e `npm run check` → PASS.
- [ ] **Step 6: Commit** `feat(web): ricerca di un nodo sulla mappa e pulsante Dove sono`.

### Task 11: Verifica finale  _(modello: sonnet)_

**Files:**
- Nessun file nuovo. Correzioni piccole dove la verifica trova problemi, ognuna con il suo commit `fix: …`.

- [ ] **Step 1: suite complete.**
  - `PYTHONPATH=server ../../.venv/Scripts/python -m pytest -q` → tutti verdi;
  - `cd web && npx vitest run` → tutti verdi;
  - `cd web && npm run check` → 0 errori;
  - `cd web && npm run build` → build riuscita.
- [ ] **Step 2: controllo nel browser** (server demo; `.claude/launch.json` se esiste, altrimenti avvio del server come nelle fasi precedenti) a **1280×800** e **390×844**, con il tema scuro e con quello chiaro.
  - **A1:** fermare il server → la barra compare entro 3 s; «Riprova ora» → nuovo tentativo; riavviare il server → «Connessione ripristinata» e dati aggiornati.
  - **A2:** filtro IT con un nodo mio in FR → il nodo resta visibile; mettere un filtro che svuota tutto → la sovrapposizione sulla mappa e «Azzera filtri» funzionano.
  - **A3:**
    - errore iniziale con «Riprova» e tentativo automatico;
    - feed vuoto con MQTT spento → «Apri Impostazioni» porta alla scheda;
    - lista radio vuota → «Vai a Radio».
  - **A5:**
    - popup del nodo con la distanza e le quattro azioni; «Copia id» → «Copiato»;
    - «Messaggio diretto» apre la conversazione giusta;
    - popup del collegamento con la lunghezza.
  - **A6:** i cinque ordinamenti; «Distanza» disattivata senza origine; ricerca «heltec» o «router».
  - **A7:**
    - ricaricando, si ritrovano scheda, centro e zoom, ultima conversazione e ordinamento di Rete;
    - `#/nodes/<id>` incollato in una scheda nuova seleziona il nodo;
    - un id inesistente mostra il messaggio;
    - «Copia link» produce un URL che funziona.
  - **A8:** con il server demo e dati preparati (telemetria `channel_util` ≥ 25, firmware `2.3.x` su un nodo mio, nodo silenzioso che torna), i tre avvisi compaiono nel popover, con l'icona e il tono giusti, e in Rete.
  - **B13:**
    - righello fra due nodi agganciati e fra due punti liberi; `Escape` chiude;
    - cambio di tema con il righello aperto → il righello resta;
    - raggruppamento spento e ricarica → resta spento;
    - ricerca di un nodo filtrato → selezionato, con il popup;
    - «Dove sono» su `127.0.0.1` (permesso concesso o negato) e da LAN in HTTP → il messaggio HTTPS.
- [ ] **Step 3: controllo automatico del layout** nel browser, a 390×844, su ogni scheda:
  - nessun testo sotto i 14 px nelle parti nuove;
  - nessun elemento cliccabile nuovo sotto i 44×44 px;
  - nessuno scorrimento orizzontale del documento;
  - nessun colore letterale nei file nuovi: `grep -nE "#[0-9a-fA-F]{3,8}\b|rgb\(" ` sui file creati da questa fase → nessun risultato fuori dai test.
- [ ] **Step 4: confini con la fase 10.** `git diff --stat main...HEAD` → i file condivisi toccati sono solo quelli elencati nelle Global Constraints. Nessuna modifica a `Settings.svelte`, `settings.py` e `mqtt_*`; nessun cambio di versione.
- [ ] **Step 5: Commit** delle eventuali correzioni (`fix: …`). La fase si chiude senza rilascio.
