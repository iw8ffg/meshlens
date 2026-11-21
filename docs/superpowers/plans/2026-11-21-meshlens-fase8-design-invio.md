# MeshLens Fase 8 — Nuova interfaccia (Claude Design) e invio via radio o MQTT: piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Obiettivo:**
1. Applicare a tutta l'interfaccia il design system prodotto da Claude Design (`docs/design/claude-design/`): token, tema scuro e chiaro, componenti, navigazione e tutte le schermate.
2. Inviare messaggi di testo sia via radio sia via MQTT da un unico campo "Invia via".

**Architettura:**
- **Server:** nuovo `mqtt_publish.py`. Costruisce un `ServiceEnvelope` con un `MeshPacket` cifrato AES-CTR (chiave del canale, nonce come in decodifica) a nome del nodo dell'utente e lo pubblica con il client MQTT esistente.
- **Interfaccia:**
  - la base: `tokens.css` generato, font locali IBM Plex, icone Lucide, bandiere SVG e un guscio con TopBar e Panel ridimensionabile su desktop, BottomNav e Sheet su telefono;
  - i componenti in `web/src/lib/ui/` e `web/src/lib/map/`, come in `docs/design/claude-design/implementazione.md`;
  - le schermate rifatte una per volta, **senza cambiare le API**.

**Spec:** `docs/superpowers/specs/2026-11-20-meshlens-design.md`. **Modifica decisa dall'utente il 2026-11-21:** l'anti-obiettivo "non pubblica nulla su MQTT" diventa "pubblica solo messaggi di testo, a nome del proprio nodo, su richiesta esplicita". Design: `docs/design/claude-design/README.md`, `implementazione.md`, `tokens.css`, `tokens.json`, `components/*/README.md`, `components/bundle.css` e `bundle.js` (anteprime di riferimento, non da copiare tali e quali).

## Global Constraints

- **Invio MQTT:**
  - **solo `TEXT_MESSAGE_APP`**, a nome del nodo dell'utente: di default l'id della prima radio collegata, oppure l'impostazione `mqtt_node_id` (`!hex`);
  - argomento `msh/<regione>/2/e/<canale>/<gateway>`, dove `<regione>` viene dal primo argomento sottoscritto (default `EU_868`) e `<gateway>` è l'id del nodo stesso;
  - `hop_limit` 3; `want_ack` false; `channel` = hash del nome del canale con la chiave; cifratura con la chiave del canale (default `AQ==` espansa, oppure quella configurata per quel canale);
  - id del pacchetto casuale a 32 bit, diverso da 0;
  - testo di al massimo **200 byte UTF-8**;
  - **limite: un messaggio ogni 10 s e 30 all'ora**; oltre si risponde 429 "Attendi N s";
  - la **prima volta** serve una conferma esplicita (`confirm_public: true`), con il testo "Il messaggio sarà pubblico sul broker mqtt.meshtastic.org e potrà essere ritrasmesso via radio dai gateway". La scelta si ricorda nell'impostazione `mqtt_send_confirmed`;
  - **nient'altro** viene pubblicato: né posizioni né nodeinfo;
  - il messaggio inviato compare nel feed con `direction:"out"` e `via:"mqtt"`.
- **Invio radio:** quello esistente (`POST /api/radios/{id}/send`), invariato.
- **Interfaccia:**
  - italiano, numeri e date con `Intl` `it-IT`, il meno tipografico «−»;
  - nessun colore fuori dai token; tema scuro predefinito, chiaro di pari livello, interruttore Auto / Scuro / Chiaro salvato in localStorage;
  - testo di almeno 14 px su telefono (`vp-phone` con `max-width: 820px`), aree toccabili di almeno 44 px, focus sempre visibile;
  - **nessuna risorsa esterna a runtime:** font WOFF2 locali (licenza OFL), icone importate singolarmente da `@lucide/svelte` (licenza ISC), bandiere SVG da `flag-icons` (licenza MIT) solo per le nazioni usate.
- **Mappa:** marker come layer, nessun elemento HTML per nodo; anello della fonte con immagini nello sprite; stile del fondo in tema (`map-dark.json` e `map-light.json` per l'online; per l'offline lo stile Protomaps con colori dai token); `fadeDuration: 0`; popup e legenda in HTML.
- **Logo Meshtastic:** solo nel badge «Compatibile con Meshtastic®» (Accesso, Informazioni, piè delle Impostazioni), accanto alla frase di non affiliazione. Il file ufficiale **non** va incluso senza verificare la trademark policy: per ora il badge è solo testuale, con una nota per l'utente.
- **Svelte 5:**
  - nessun `$effect` legge e scrive lo stesso `$state`;
  - timer e listener vanno puliti;
  - l'effetto WebSocket e dati in App non segue stati nuovi.
- I test esistenti (server e vitest) restano verdi. Le funzioni pure nuove hanno i loro test.
- Contratti JSON: **invariati**, salvo le aggiunte per l'invio MQTT.

## Contratti JSON (aggiunte)

- `POST /api/mqtt/send` body `{text, channel:"LongFast", to?:"!hex", confirm_public?:bool}` → 202 `{message:<Message con direction "out", via "mqtt", status "sent">}`.
  - 409 con il codice `confirm_required` alla prima volta, finché manca la conferma;
  - 400 per testo vuoto o oltre 200 byte, oppure per un nodo dell'utente sconosciuto ("Collega una radio o imposta il tuo id nodo in Impostazioni → MQTT");
  - 429 per il limite di frequenza;
  - 503 se il client MQTT non è connesso.
- Impostazioni: `mqtt_node_id` (`!hex` oppure stringa vuota) e `mqtt_send_confirmed` (bool).
- Messaggio: il campo facoltativo `via: "radio" | "mqtt"`.

## Review Focus

1. **Pacchetto MQTT valido:** un pacchetto pubblicato e poi decodificato dal nostro `EnvelopeDecoder` restituisce lo stesso testo, mittente e canale (prova di andata e ritorno).
2. **Nessuna pubblicazione accidentale:** senza conferma, con il limite superato o con MQTT disconnesso non parte nulla, e nessun altro tipo di pacchetto viene mai pubblicato.
3. **Tema:** il passaggio scuro ↔ chiaro aggiorna anche mappa, marker, grafici e popup, senza ricaricare la pagina e senza cicli di `setStyle`.
4. **Telefono:** BottomNav (Mappa, Nodi, Chat, Copertura, Altro) e Sheet a tre fermi funzionano anche con i pulsanti; la tastiera non copre il compositore della chat.
5. **Nessuna regressione funzionale:** ogni funzione delle fasi 1–7 resta raggiungibile, cioè traceroute, Configura, Prepara le radio, mappe offline e aggiornamenti.

---

### Task 1: Server, invio di testo via MQTT
**File:** crea `server/meshlens/mqtt_publish.py`; modifica `mqtt_client.py` (metodo `publish(topic, payload)`), `api.py`, `settings.py`, `ingest.py` (registra il messaggio in uscita con `via:"mqtt"`). Test in `server/tests/test_mqtt_publish.py`.
- `build_envelope(text, from_num, to_num, channel_name, key, packet_id, gateway_id) -> bytes`, funzione pura;
- `MqttSender(connector, settings, radios, clock)`, che gestisce limite di frequenza, conferma, nodo dell'utente e risoluzione della regione;
- rotta `POST /api/mqtt/send`.
- **Test:**
  - andata e ritorno con `EnvelopeDecoder` (Review Focus 1);
  - hash del canale;
  - testo oltre 200 byte → 400;
  - prima volta → 409 `confirm_required`;
  - limiti di 10 s e 30 all'ora → 429;
  - MQTT disconnesso → 503;
  - nodo sconosciuto → 400;
  - nessun publish negli scenari d'errore (Review Focus 2).
- **Commit** `feat(server): invio di messaggi di testo via MQTT a nome del proprio nodo`.

### Task 2: Interfaccia, fondamenta del design
**File:**
- `web/src/app.css`, con `tokens.css` copiato da `docs/design/claude-design/tokens.css` e i font locali in `web/public/fonts/`;
- `web/src/lib/theme.ts` (Auto / Scuro / Chiaro, `data-theme` su `<html>`, `matchMedia`);
- `web/src/lib/viewport.svelte.ts` (`vp-phone`);
- `web/src/lib/format.ts`, esteso con `num`, `signed`, `ago` come nel design.
- **Componenti di base** in `web/src/lib/ui/`: Button, Field, Select, Switch, Check, Segmented, Chip, Badge, SnrBadge, BatteryBadge, SourceMark, Flag, Card, Banner, Toast, Progress, Empty, Skeleton, Modal (con la variante `risk`), Sheet (tre fermi, trascinamento più pulsanti), Icon (wrapper Lucide), Table (colonna fissa).
- **Test vitest** per `theme.ts`, per `format.ts` (casi del design: "3,59 V", "−3,5 dB", "12 min fa") e per la logica dei fermi dello Sheet.
- **Commit** `feat(web): token, temi, font locali e componenti di base del design`.

### Task 3: Interfaccia, guscio e navigazione
- **Desktop:** TopBar di 48 px con logo, stato MQTT, nodi, radio, avvisi e aggiornamento; Panel ridimensionabile tra 320 e 560 px, salvato in localStorage; pagine lunghe (Rete, Configura, Impostazioni) a tutta area.
- **Telefono:** BottomNav di 64 px (Mappa, Nodi, Chat, Copertura, Altro), dove "Altro" porta a Rete, Radio e Impostazioni; Sheet per i pannelli; `100dvh` e safe area.
- Schermata d'accesso con PIN nel nuovo stile e badge testuale «Compatibile con Meshtastic®» più la frase di non affiliazione.
- **Commit** `feat(web): guscio, navigazione e accesso nel nuovo design`.

### Task 4: Interfaccia, mappa
- `web/src/lib/map/`: NodeLayer (riempimento per età, anello della fonte come immagini nello sprite ricolorate per tema, stella "Mio nodo", cluster), LinkLayer, TrackLayer, CoverageLayer, Legend, MapControls, NodePopup in HTML.
- Stili del fondo `map-dark.json` e `map-light.json` derivati da OpenFreeMap (online) con i colori `map-*`; per l'offline lo stile Protomaps con colori dai token.
- Il cambio di tema ricrea gli stili una sola volta (Review Focus 3). La logica online/offline e la scelta della base della Copertura restano.
- **Commit** `feat(web): mappa nel nuovo design con temi`.

### Task 5: Interfaccia, Nodi, dettaglio nodo, Rete
- Le schermate secondo `components/SchermataNodi`, `SchermataDettaglioNodo` e `SchermataRete`: filtri a chip, righe con SnrBadge, BatteryBadge e SourceMark, grafico nei colori dei token, traceroute, avvisi.
- **Commit** `feat(web): nodi, dettaglio e rete nel nuovo design`.

### Task 6: Interfaccia, Chat con "Invia via"
- `SchermataChat`: conversazioni (canali delle radio, messaggi diretti, "Pubblico (MQTT)" con il suo filtro e il canale su ogni messaggio).
- **Compositore unico:** "Invia via: Radio «nome» (canale) / MQTT (canale)"; le opzioni non disponibili sono disattivate con il motivo; contatore in byte UTF-8 (massimo 200).
  - Alla prima pubblicazione MQTT compare una Modal di conferma con il testo delle Global Constraints.
  - Stati del messaggio: ⏳, ✓, ✓✓, ⚠ con etichette accessibili; i messaggi MQTT mostrano "via MQTT".
- Su telefono `visualViewport` tiene il compositore sopra la tastiera.
- **Test vitest** per il contatore in byte, per la scelta "Invia via" disponibile o disattivata e per la logica della conferma.
- **Commit** `feat(web): chat con invio via radio o MQTT nel nuovo design`.

### Task 7: Interfaccia, Copertura, Radio, Configura, Impostazioni
- Le schermate secondo i rispettivi README.
- Configura con Modal `risk`.
- Impostazioni con l'interruttore del tema, "Il tuo id nodo per MQTT", i canali da ascoltare, Mappe offline, Aggiornamenti e Informazioni, con il badge Meshtastic e le licenze.
- **Commit** `feat(web): copertura, radio, configura e impostazioni nel nuovo design`.

### Task 8: Verifica, release 1.1.0
- Controllo nel browser di tutte le schermate a 1280×800 e 390×844, nei due temi; audit automatico su testo, aree toccabili e scorrimento orizzontale; schermate nuove per il README.
- Release `v1.1.0`: è anche la prova completa dell'aggiornamento dall'app partendo dalla 1.0.2.
