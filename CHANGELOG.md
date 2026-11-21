# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it-IT/1.1.0/) e il progetto usa il [versionamento semantico](https://semver.org/lang/it/).
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.1.0] - 2026-11-21

### Italiano

#### Aggiunto
- **Nuova interfaccia** completa, progettata con Claude Design: tema scuro e chiaro (Auto / Scuro / Chiaro), caratteri IBM Plex e icone inclusi nell'app (funziona anche senza internet), bandiere vere, colori dei dati leggibili anche per i daltonici (SNR con ▲ ● ▼, fonte riconoscibile dalla forma dell'anello).
- **Telefono:** barra in basso (Mappa, Nodi, Chat, Copertura, Altro) e pannello che sale dal basso; sul PC pannello laterale ridimensionabile.
- **Mappa** nei due temi: marker per età del contatto, anello per la fonte, stella per i tuoi nodi, legenda e popup nuovi. La mappa compare subito anche con una rete lenta.
- **Invio dei messaggi via radio o via MQTT** da un unico campo "Invia via". Via MQTT si pubblica solo il testo, a nome del tuo nodo (la radio collegata o l'id impostato in Impostazioni → MQTT), con conferma la prima volta e un limite di un messaggio ogni 10 secondi e 30 all'ora.

#### Modificato
- La regola "nessuna pubblicazione su MQTT" diventa "solo i messaggi di testo che invii tu".

### English

#### Added
- **New interface**, designed with Claude Design: dark and light themes (Auto / Dark / Light), IBM Plex fonts and icons bundled (works offline), real flags, data colours readable with colour blindness (SNR with ▲ ● ▼, source shown by ring shape).
- **Phone:** bottom bar (Map, Nodes, Chat, Coverage, More) and a bottom sheet; resizable side panel on desktop.
- **Map** in both themes: markers by contact age, ring by source, star for your nodes, new legend and popups. The map appears immediately even on a slow network.
- **Send messages over radio or MQTT** from a single "Send via" field. Over MQTT only text is published, as your own node (the connected radio or the id set in Settings → MQTT), with a confirmation the first time and a limit of one message every 10 seconds and 30 per hour.

#### Changed
- The "never publish to MQTT" rule becomes "only the text messages you send".

## [1.0.2] - 2026-11-21

### Italiano

#### Corretto
- **Aggiornamento dall'app:** dopo "Installa e riavvia" non succedeva nulla, perché l'installer partiva mentre MeshLens era ancora aperto e in modalità silenziosa rinunciava. Ora l'installer parte solo dopo la chiusura di MeshLens, e l'installer stesso aspetta fino a 30 secondi che MeshLens si chiuda, così l'aggiornamento funziona anche dalle versioni precedenti.

### English

#### Fixed
- **In-app update:** after "Install and restart" nothing happened, because the installer started while MeshLens was still running and gave up in silent mode. The installer now starts only after MeshLens exits, and it also waits up to 30 seconds for MeshLens to close, so updating works from earlier versions too.

## [1.0.1] - 2026-11-21

### Italiano

#### Corretto
- **Feed dei messaggi:** il feed pubblico MQTT usava il filtro della mappa (default solo Italia) e scartava i mittenti senza nazione, quindi sembrava vuoto. Ora ha un filtro suo: di default mostra tutte le nazioni, compresi i nodi senza posizione; si può limitare a nazioni scelte e escludere i nodi senza posizione. Il filtro è ricordato e viene indicato quanti messaggi nasconde. Ogni messaggio mostra il canale MQTT e la bandiera del mittente ("?" se sconosciuta).

#### Aggiunto
- **Scelta dei canali MQTT:** in Impostazioni, "Canali da ascoltare" permette di ascoltare tutti i canali o solo quelli scelti (LongFast, MediumFast, MediumSlow, ShortFast, ShortSlow, LongModerate, LongSlow, ShortTurbo e quelli visti) con il numero di messaggi dell'ultima ora. I canali non scelti sono ignorati del tutto; la radio non è mai filtrata. Nuova API `GET /api/mqtt/channels` e impostazione `mqtt_channels`.

### English

#### Fixed
- **Message feed:** the public MQTT feed used the map's country filter (default Italy only) and dropped senders with an unknown country, so it looked empty. It now has its own filter: by default it shows all countries, including nodes without a position; it can be restricted to chosen countries and can exclude nodes without a position. The filter is remembered and the feed says how many messages it hides. Each message shows its MQTT channel and the sender's flag ("?" if unknown).

#### Added
- **MQTT channel selection:** Settings, "Channels to listen to" lets you listen to all channels or only chosen ones (LongFast, MediumFast, MediumSlow, ShortFast, ShortSlow, LongModerate, LongSlow, ShortTurbo and any seen) with the last hour's message count. Unselected channels are ignored entirely; the radio is never filtered. New `GET /api/mqtt/channels` API and `mqtt_channels` setting.

## [1.0.0] - 2026-11-21

### Italiano

#### Aggiunto
- **Base (fase 1):** server locale con database SQLite; ricezione MQTT in sola lettura con decodifica, decifratura, deduplica e nazione dei nodi; mappa, elenco nodi, feed dei messaggi, filtri; accesso con PIN.
- **Radio (fase 2):** più radio insieme via USB e Bluetooth con riconnessione automatica; fusione del traffico RF con MQTT; chat su canali e messaggi diretti con stato di consegna.
- **Rete (fase 3):** stato dei nodi, "i miei nodi", grafico storico della batteria, avvisi in app, mappa dei collegamenti e traceroute.
- **Copertura (fase 4):** prove di copertura con Range Test, punti colorati per segnale, percorso, punti mancanti e storico delle sessioni.
- **Configurazione (fase 5):** lettura e modifica della configurazione di radio collegate e nodi remoti (chiavi admin), con riepilogo delle differenze, conferma e copia di sicurezza ripristinabile; "Prepara le radio" e "Ripristina" per la copertura.
- **Offline (fase 6):** mappe PMTiles (mondo, Italia, aree a scelta) con scaricamento guidato, passaggio automatico online/offline, glifi e sprite inclusi; rifinitura per telefono.
- **Rilascio (fase 7):** installer Windows per utente con icona nell'area di notifica e avvio automatico facoltativo; aggiornamento dall'app con controllo, download verificato (SHA-256) e installazione; documentazione bilingue, logo e licenza GPL-3.0.

### English

#### Added
- **Foundation (phase 1):** local server with SQLite database; listen-only MQTT ingestion with decoding, decryption, deduplication and node country lookup; map, node list, message feed, filters; PIN login.
- **Radios (phase 2):** several radios at once over USB and Bluetooth with automatic reconnection; RF traffic merged with MQTT; chat on channels and direct messages with delivery status.
- **Network (phase 3):** node status, "my nodes", battery history chart, in-app alerts, link map and traceroute.
- **Coverage (phase 4):** Range Test coverage sessions, points colored by signal, route, missing points and session history.
- **Configuration (phase 5):** read and edit configuration of connected radios and remote nodes (admin keys), with diff summary, confirmation and restorable backup; "Prepare radios" and "Restore" for coverage tests.
- **Offline (phase 6):** PMTiles maps (world, Italy, chosen areas) with guided download, automatic online/offline switching, bundled glyphs and sprites; phone polish.
- **Release (phase 7):** per-user Windows installer with notification-area icon and optional autostart; in-app update with check, verified download (SHA-256) and install; bilingual documentation, logo and GPL-3.0 license.

[1.0.1]: https://github.com/iw8ffg/meshlens/releases/tag/v1.0.1
[1.0.0]: https://github.com/iw8ffg/meshlens/releases/tag/v1.0.0
[1.0.2]: https://github.com/iw8ffg/meshlens/releases/tag/v1.0.2
[1.1.0]: https://github.com/iw8ffg/meshlens/releases/tag/v1.1.0
