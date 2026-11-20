# MeshLens — Documento di design

Data: 2026-11-20 · Stato: in attesa di approvazione finale
Studio di riferimento: [docs/studio-iniziale.md](../../studio-iniziale.md)

## 1. Intento

MeshLens è una webapp locale per Windows, per un solo utente, che riunisce in un'unica mappa interattiva tutto ciò che accade su una rete Meshtastic, da due fonti:

- **Internet (MQTT)**: traffico pubblico Meshtastic (posizioni GPS, messaggi, info nodi, telemetria), filtrabile per nazione.
- **Radio (RF)**: una o più radio Meshtastic collegate al PC via **USB** o **Bluetooth**, usate per ricevere e trasmettere.

L'utente la usa per tre scopi, con pari importanza:
1. **Osservare** la rete (chi c'è, dove, cosa si dice).
2. **Gestire la propria rete locale**: stato dei nodi, batteria, copertura, configurazione remota.
3. **Comunicare** via radio anche **senza internet**.

Si usa dal PC e dal telefono collegato alla stessa Wi-Fi di casa.

## 2. Obiettivi, non-obiettivi, anti-obiettivi

**Obiettivi**
- Mappa con nodi da MQTT e da RF, fusi in un'unica vista, con fonte/radio che ha sentito ciascun nodo.
- Filtro per nazione (e per fonte, per ultimo contatto, per ruolo).
- Chat: ricezione e invio di messaggi su canali e diretti tramite le radio collegate.
- Più radio collegate contemporaneamente (USB + Bluetooth).
- Stato nodi, batteria con storico e avvisi, mappa dei collegamenti, test di copertura sul campo.
- Configurazione remota dei nodi della propria rete.
- Funzionamento completo offline (mappe dell'Italia incluse).
- Interfaccia utilizzabile bene dal telefono.

**Non-obiettivi (prima versione)**
- Radio via Wi-Fi/TCP (architettura predisposta, non implementata).
- Più utenti, ruoli, accesso da internet.
- HTTPS (quindi niente GPS del telefono né notifiche push nel browser).
- Aggiornamento firmware, app mobile nativa, eseguibile unico `.exe`.

**Anti-obiettivi (sarebbe un fallimento anche se funziona)**
- MeshLens **non pubblica nulla** sui broker MQTT pubblici: solo sottoscrizione.
- Non aggira i limiti di legge (duty cycle EU 10%, potenza, preset non ammessi).
- Non diventa uno strumento di tracciamento a lungo termine delle persone: lo storico ha una scadenza.
- Una modifica di configurazione remota non avviene mai senza conferma esplicita.

## 3. Vincoli

- Windows 11; già presenti Python 3.12, Node 24, git.
- Hardware dell'utente: Heltec V3 (base, USB; senza GPS), LilyGO T-Deck (GPS solo se versione Plus [?]), LilyGO T-Pager (GPS integrato; supporto firmware recente [?]). Tutti ESP32-S3/ESP32.
- Regione radio `EU_868`.
- Broker pubblico: posizioni imprecise (~1,5 km), solo zero-hop, solo alcuni portnum, niente `msh/#` (vedi studio §2).
- Una porta COM e una connessione Bluetooth per radio possono essere usate da un solo programma alla volta.
- Licenze: le librerie Meshtastic sono GPL-3.0 → MeshLens è GPL-3.0 (uso personale, nessun problema).

## 4. Approcci considerati

| | Approccio | Esito |
|---|---|---|
| **A** | **Server Python** (libreria ufficiale `meshtastic`) + interfaccia web | **Scelto** (scelta delegata a Claude dall'utente) |
| B | Server Node.js/TypeScript con `@meshtastic/core` | Scartato: Bluetooth da Node su Windows debole; librerie JS in rifacimento; trasporto seriale lato Node molto recente |
| C | Estendere MeshDash o m9wav/MeshConsole | Scartato: mancano multi-radio, nazione, copertura, offline; si erediterebbe un design da riscrivere. Restano riferimenti di codice |

Esclusi a priori: app desktop chiusa (Electron/Tauri, niente telefono) e Web Serial nel browser (niente telefono, niente Bluetooth su Windows, solo Chromium).

**Perché A**: è l'unico in cui USB, Bluetooth, telemetria, traceroute e configurazione remota con chiavi admin sono già solidi e documentati oggi.

## 5. Architettura

```
 Radio USB ─┐                                 ┌─ Browser PC
 Radio BLE ─┼─► Connettori radio ─┐           │
            │                     ├─► Bus eventi ─► API REST + WebSocket ─┤
 Broker MQTT ─► Connettore MQTT ──┘     │                                  └─ Browser telefono (Wi-Fi)
                                        ▼
                         Elaborazione (decodifica, deduplica, nazione)
                                        ▼
                                   SQLite (storico)
```

### 5.1 Server (Python 3.12)
- **Web**: FastAPI + uvicorn; API REST per letture/azioni, **WebSocket** per eventi in tempo reale. Serve anche i file statici dell'interfaccia.
- **Radio**: libreria `meshtastic` (`SerialInterface` per USB, `BLEInterface` per Bluetooth, basato su bleak). La libreria lavora a thread e pubsub: gli eventi vanno passati al loop asyncio in modo thread-safe.
- **Gestore radio**: un connettore per radio, ciascuno con id, nome, tipo (usb/ble), indirizzo (COM o MAC), stato (connessa/riconnessione/errore). Riconnessione automatica con backoff. Elenco porte COM e scansione Bluetooth dall'interfaccia. Interfaccia astratta comune per poter aggiungere TCP in futuro.
- **MQTT**: client (paho-mqtt o aiomqtt) con broker configurabili; default `mqtt.meshtastic.org`, credenziali pubbliche, topic `msh/EU_868/#`. Decodifica `ServiceEnvelope` protobuf, decifratura AES-CTR con la chiave di default (`AQ==`) più chiavi aggiuntive configurate dall'utente; lettura dei map report (non cifrati). I pacchetti non decifrabili si contano ma non si salvano.
- **Elaborazione**:
  - **Deduplica** per chiave (nodo mittente, packet id) in una finestra temporale; ogni ricezione resta come "osservazione" (fonte, radio, SNR, RSSI, hop, gateway, ora).
  - **Nazione**: point-in-polygon su confini Natural Earth admin-0 (file incluso, offline), con tolleranza per punti in mare/vicino ai confini (nazione più vicina entro X km). Calcolata alla prima posizione e ricalcolata se il nodo si sposta. Nodi senza posizione → "sconosciuto". Messaggi associati alla nazione del mittente.
- **Database**: SQLite (file locale). Pulizia automatica secondo la retention.
- **Avvio**: `start.bat` che attiva l'ambiente Python e apre il browser.

### 5.2 Interfaccia (web, responsive, prima il telefono)
- Svelte + Vite, compilata in statici serviti dal server.
- **Mappa**: MapLibre GL JS. Offline: file **PMTiles** dell'Italia (estratto Protomaps/OpenStreetMap, scaricato una volta, ~1–2 GB [?]). Online: tile del mondo da un servizio che ne consente l'uso (es. OpenFreeMap/Protomaps), commutazione automatica.
- **Viste**: Mappa (a tutto schermo), Nodi (elenco con filtri), Chat, Rete (stato/batteria/collegamenti), Copertura, Radio (connessioni), Impostazioni.
- Su telefono: pannelli a scomparsa sopra la mappa; su PC: pannello laterale.

### 5.3 Sicurezza
- Per default il server ascolta solo su `127.0.0.1`. Un'impostazione abilita l'ascolto sulla rete locale.
- **PIN** scelto al primo avvio; ogni dispositivo lo inserisce una volta e riceve un cookie di sessione di lunga durata. Blocco temporaneo dopo tentativi errati. Il PIN è richiesto anche dal PC (semplicità, un solo meccanismo).
- Le azioni che trasmettono via radio o modificano configurazioni passano tutte dall'API autenticata.

## 6. Funzioni

### 6.1 Mappa e osservazione
- Marker per nodo, colore per fonte (RF / MQTT / entrambi) e per ultimo contatto (verde < 2 h, giallo < 24 h, grigio oltre; soglie configurabili).
- Dettaglio nodo: nome lungo/corto, id, hardware, ruolo, firmware, ultima posizione e precisione, batteria/tensione, utilizzo canale, chi l'ha sentito (radio/MQTT) con SNR/RSSI/hop, nazione.
- Traccia posizioni del nodo nel periodo di retention (attivabile dal dettaglio, non per default).
- Filtri: nazione (multi-selezione), fonte, radio, ultimo contatto, ruolo, testo (nome/id).
- Feed messaggi MQTT pubblici (canale di default) con filtro per nazione.

### 6.2 Radio e comunicazione
- Aggiunta radio: scelta porta COM (con nome dispositivo/VID-PID) o scansione Bluetooth + abbinamento (PIN mostrato dalla radio).
- Più radio insieme; per ogni radio: stato, nodo locale, canali configurati.
- Chat per canale (dei canali delle radio) e messaggi diretti; scelta della radio da cui trasmettere; stato di consegna (ack) quando disponibile.
- I messaggi diretti cifrati a chiave pubblica sono gestiti dalla radio stessa.

### 6.3 Gestione rete
- **Stato nodi**: tabella con ultimo contatto, ruolo, firmware, SNR, utilizzo canale/airtime.
- **Batteria**: dalla telemetria; grafico storico per nodo; avviso in app (banner + elenco) sotto soglia configurabile (default 20%) o se un nodo segnato come "mio" tace da più di N ore.
- **"I miei nodi"**: l'utente marca i nodi della propria rete; viste e avvisi si concentrano su questi.
- **Mappa collegamenti**: linee tra nodi da NeighborInfo e da traceroute; colore per SNR. Traceroute avviabile a richiesta verso un nodo.

### 6.4 Copertura sul campo (Range Test)
- Sessione di prova: l'utente sceglie la radio di base (es. Heltec V3 via USB) e il nodo mobile (T-Pager o T-Deck Plus con GPS).
- Il nodo mobile trasmette la posizione a intervalli regolari (modulo Range Test o posizione periodica; MeshLens può impostarlo via configurazione remota prima della prova).
- MeshLens registra per ogni pacchetto ricevuto: posizione, SNR, RSSI, ora. Durante la prova il telefono non serve.
- Al termine: mappa dei punti colorati per qualità del segnale, traccia del percorso, punti mancanti dedotti dai numeri di sequenza; storico delle sessioni.
- Futuro (non v1): misura nei due sensi.

### 6.5 Configurazione remota
- Basata sulle **chiavi admin** (firmware ≥ 2.5): la chiave pubblica della radio di MeshLens va inserita una volta nei nodi da gestire (MeshLens mostra la chiave e una guida).
- Lettura configurazione del nodo remoto; modifica di sezioni (LoRa, posizione, telemetria, ruolo, canali, range test, ecc.); riavvio.
- Prima di ogni modifica: **riepilogo delle differenze e conferma esplicita**; **copia della configurazione precedente** salvata nel database e ripristinabile.
- Avviso rafforzato per modifiche che possono isolare il nodo (regione, preset, canale primario, chiavi).

## 7. Dati e retention
- Entità principali: radio, nodi, osservazioni, pacchetti (deduplicati), messaggi, posizioni, telemetria, collegamenti tra nodi, sessioni di copertura con punti, backup configurazioni, impostazioni.
- Retention di default (modificabile): messaggi e posizioni **90 giorni**; telemetria **1 anno**; sessioni di copertura e backup di configurazione **senza scadenza**.
- Pulizia automatica giornaliera.

## 8. Fasi di sviluppo (proposta)
1. **Base**: server, database, MQTT (decodifica, deduplica, nazione), mappa online, elenco nodi, feed messaggi, PIN.
2. **Radio**: USB, Bluetooth, più radio, chat e invio, fusione RF+MQTT.
3. **Gestione rete**: stato, batteria con grafici e avvisi, "i miei nodi", collegamenti e traceroute.
4. **Copertura**: sessioni Range Test.
5. **Configurazione remota** con conferma e backup.
6. **Offline e rifinitura**: mappe PMTiles Italia, `start.bat`, impostazioni, ottimizzazione mobile.

Ogni fase si chiude con l'app funzionante e provata con le radio reali dell'utente.

## 9. Decisioni prese da Claude dopo la revisione (da controllare)
- **Posizioni da più fonti**: si conserva una posizione per fonte (RF esatta, MQTT approssimata) con precisione dichiarata. Sulla mappa e per la nazione vale la più precisa tra quelle recenti (< 24 h), altrimenti la più recente.
- **Range Test**: meccanismo principale = modulo Range Test di Meshtastic (ha numeri di sequenza → punti mancanti). Richiede GPS sul nodo mobile; senza GPS la sessione non parte (messaggio chiaro). Posizione periodica solo come ripiego senza rilevazione dei punti mancanti.
- **Configurazione**: anche le radio collegate localmente (USB/BLE) sono configurabili da MeshLens (più semplice, nessuna chiave admin), con le stesse regole di conferma e backup. L'amministrazione remota funziona anche su più salti nella mesh.
- **PIN**: salvato come hash (argon2/bcrypt) nel database; reset da riga di comando (`meshlens reset-pin`); anche il WebSocket richiede il cookie di sessione.
- **"I miei nodi"**: le radio collegate sono marcate automaticamente; gli altri nodi a mano.
- **Chiavi MQTT aggiuntive**: inserite nelle impostazioni, salvate nel database locale in chiaro (uso personale su PC dell'utente).
- **Mappe**: incluso un fondo mondiale a basso dettaglio (zoom 0–6) più l'Italia in dettaglio; il download dei file è un passo guidato nell'app (Impostazioni → Mappe offline), non obbligatorio per l'avvio.
- **Tolleranza nazione**: 25 km dalla costa/confine più vicino.
- **Messaggi MQTT pubblici**: solo lettura.
- **Storico MQTT** (deciso dall'utente): tutto il traffico `msh/EU_868/#` è mostrato in diretta, ma nello storico si salvano **solo le nazioni scelte** nelle impostazioni (default: Italia). I nodi senza posizione si salvano solo se hanno inviato almeno un pacchetto con posizione in una nazione scelta, oppure se sono stati sentiti via RF.
- **Bluetooth** (deciso dall'utente): la fase 2 inizia con una prova rapida di `BLEInterface` su Windows con più radio; se instabile, la fase prosegue con l'USB e il Bluetooth si completa subito dopo, senza bloccare le fasi successive.
- **Volume**: le osservazioni da MQTT si aggregano per pacchetto (prima ricezione, numero di gateway, migliore SNR); le osservazioni RF si conservano tutte. Limite di spazio configurabile (default 2 GB) con pulizia dei dati più vecchi.

## 10. Lasciato al builder
- Struttura interna di moduli e componenti, scelta tra paho-mqtt/aiomqtt, ORM o SQL diretto, libreria di grafici.
- Strategia di test (unit su decodifica/decifratura/deduplica/nazione con pacchetti registrati; prove manuali con radio reali).
- Gestione dell'ambiente Python (venv) e versioni esatte delle dipendenze.

## 11. Da verificare in fase di sviluppo
- Costruzione esatta del nonce AES-CTR e topic dei map report (`/2/map/`).
- Funzionamento di `BLEInterface` (bleak) su Windows 11 con abbinamento a PIN e con più radio insieme.
- Supporto Meshtastic del T-Pager e presenza del GPS sul T-Deck dell'utente.
- Dimensione reale del file PMTiles dell'Italia e fonte tile online con uso consentito.
- Se il broker pubblico accetta ancora l'iscrizione a `msh/EU_868/#` senza restrizioni.
