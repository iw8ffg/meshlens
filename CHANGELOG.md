# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it-IT/1.1.0/) e il progetto usa il [versionamento semantico](https://semver.org/lang/it/).
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.4.2] - 2026-11-22

### Italiano

#### Corretto
- **Zona bianca nelle Impostazioni:** spuntando i canali da ascoltare (o le nazioni) in un elenco lungo, la pagina non salta più in fondo e non compare più una grande zona vuota.

#### Aggiunto
- **Ricerca nei canali:** con più di 6 canali compare una casella per cercarli per nome; sotto l'elenco è indicato quanti ne hai scelti.

### English

#### Fixed
- **Blank area in Settings:** ticking channels to listen to (or countries) in a long list no longer jumps the page to the bottom or adds a large empty area.

#### Added
- **Channel search:** with more than 6 channels a box lets you search them by name; below the list you see how many you have chosen.

## [1.4.1] - 2026-11-22

### Italiano

#### Corretto
- **Blocco dopo l'aggiornamento:** gli avvisi di Windows dall'icona partono ora da un canale separato e non possono più fermare il server.

#### Aggiunto
- **Diagnosi dei blocchi:** se il server resta fermo per più di 15 secondi, MeshLens scrive nella cartella dei log un file `stall-…txt` con lo stato di tutte le sue parti, da allegare a una segnalazione.
- **Pulizia dei backup:** puoi eliminare un backup dall'elenco (Impostazioni, Backup), eliminare in blocco quelli più vecchi di N giorni e scegliere di farlo in automatico (0 = mai, predefinito). Restano sempre il backup più recente e quello in attesa di ripristino.

### English

#### Fixed
- **Freeze after updating:** Windows notifications from the tray icon now go through a separate channel and can no longer stall the server.

#### Added
- **Freeze diagnostics:** if the server stops responding for more than 15 seconds, MeshLens writes a `stall-…txt` file in the logs folder with the state of all its parts, to attach to a report.
- **Backup cleanup:** you can delete a backup from the list (Settings, Backups), bulk-delete those older than N days, and have it done automatically (0 = never, the default). The most recent backup and the one scheduled for restore are always kept.

## [1.4.0] - 2026-11-22

### Italiano

#### Aggiunto
- **Messaggi non letti:** contatori sulle conversazioni, conversazioni non lette in grassetto, `(n)` nel titolo della scheda e **notifiche del browser** per i messaggi diretti.
- **Elenco delle conversazioni:** al posto del menu a tendina, con ordine per attività, anteprima dell'ultimo messaggio, **ricerca** e **bozze** che restano salvate; dalla lista si passa alla conversazione e si torna indietro.
- **Risposte e reazioni con emoji:** le ricevi e le invii, via radio e via MQTT.
- **Messaggi diretti cifrati:** un **lucchetto** indica i messaggi diretti protetti con la chiave pubblica (PKI); MeshLens **ti avvisa quando la chiave di un nodo cambia**.
- **Errori di consegna spiegati:** quando un messaggio non arriva, vedi il motivo in italiano.
- **Waypoint sulla mappa:** i waypoint ricevuti compaiono sulla mappa e puoi inviare i tuoi **via radio** (non vengono mai pubblicati su MQTT).
- **Notifiche esterne:** notifiche di Windows dall'icona nell'area di notifica e, se lo attivi, un **bot Telegram**; il token del bot è salvato cifrato.
- **Nuova telemetria:** ambiente, qualità dell'aria, alimentazione e statistiche locali dei nodi, da MQTT e da radio.
- **Grafici più ricchi:** lettura dei valori al passaggio del mouse e **periodo a scelta**, anche per uso del canale, SNR e sensori.
- **Esportazioni:** dati in **CSV** (con `;`, per aprirlo bene in Excel), percorsi e posizioni in **GPX**, **GeoJSON** e **KML**.
- **Traccia di un nodo** con periodo a scelta, **fino a 90 giorni**.
- **Statistiche della rete:** nuova vista nella pagina Rete (Nodi / Statistiche / Pacchetti).
- **Ispettore dei pacchetti:** per vedere i pacchetti ricevuti, con impostazioni di conservazione per limitare lo spazio occupato.
- **Copertura prevista:** MeshLens calcola la copertura attesa di un sito (posizione, altezza dell'antenna, potenza, guadagni) con il modello **NTIA ITM** e i dati di altitudine **Terrarium**, scaricati solo dopo la tua conferma (con la stima della dimensione). Il risultato si vede sulla mappa e si **confronta con le misure** delle prove di copertura (Range Test). Se la potenza supera il limite di legge UE 868 compare un avviso.
- **Recupera messaggi persi (Store & Forward):** dalla scheda Radio chiedi a un nodo router lo storico dei messaggi che ti sei perso; i messaggi recuperati entrano nelle conversazioni senza duplicati.
- **Interfaccia in inglese:** la lingua si sceglie in Impostazioni e viene ricordata; l'italiano resta quella predefinita.

#### Modificato
- **Migrazioni del database:** l'aggiornamento aggiunge nuove tabelle e colonne in modo automatico, **con un backup del database fatto prima**. Se torni alla 1.3.x o precedenti, ripristina un backup precedente all'aggiornamento.
- **Attribuzioni di terzi:** i dati di altitudine Terrarium (AWS Terrain Tiles) e il modello NTIA ITM sono citati in `THIRD_PARTY_NOTICES.md`.
- L'elenco delle conversazioni sostituisce il menu a tendina del canale nella chat.

### English

#### Added
- **Unread messages:** counters on conversations, unread conversations in bold, `(n)` in the browser tab title and **browser notifications** for direct messages.
- **Conversation list:** replaces the drop-down, with ordering by activity, a preview of the last message, **search** and **drafts** that stay saved; you move from the list to a conversation and back.
- **Replies and emoji reactions:** receive and send them, over radio and over MQTT.
- **Encrypted direct messages:** a **lock** marks direct messages protected with the public key (PKI); MeshLens **warns you when a node's key changes**.
- **Delivery errors explained:** when a message does not get through you see the reason in plain language.
- **Waypoints on the map:** received waypoints appear on the map and you can send your own **over radio** (they are never published to MQTT).
- **External notifications:** Windows notifications from the notification-area icon and, if you enable it, a **Telegram bot**; the bot token is stored encrypted.
- **New telemetry:** environment, air quality, power and local node statistics, from MQTT and from radio.
- **Richer charts:** values shown as you hover, and a **selectable period**, also for channel use, SNR and sensors.
- **Exports:** data as **CSV** (with `;`, so it opens correctly in Excel), tracks and positions as **GPX**, **GeoJSON** and **KML**.
- **Node track** with a selectable period, **up to 90 days**.
- **Network statistics:** a new view in the Network page (Nodes / Statistics / Packets).
- **Packet inspector:** browse the packets received, with retention settings to limit the space used.
- **Predicted coverage:** MeshLens computes the expected coverage of a site (position, antenna height, power, gains) with the **NTIA ITM** model and **Terrarium** elevation data, downloaded only after you confirm (with a size estimate shown first). The result is shown on the map and **compared with the measurements** from coverage tests (Range Test). A warning appears if the power exceeds the EU 868 legal limit.
- **Recover missed messages (Store & Forward):** from the Radio tab, ask a router node for the history of messages you missed; recovered messages enter the conversations without duplicates.
- **English interface:** the language is chosen in Settings and remembered; Italian stays the default.

#### Changed
- **Database migrations:** updating adds new tables and columns automatically, **with a database backup taken beforehand**. If you go back to 1.3.x or earlier, restore a backup made before the update.
- **Third-party attributions:** the Terrarium elevation data (AWS Terrain Tiles) and the NTIA ITM model are credited in `THIRD_PARTY_NOTICES.md`.
- The conversation list replaces the channel drop-down in chat.

## [1.3.0] - 2026-11-21

### Italiano

#### Aggiunto
- **Più broker MQTT insieme:** puoi collegare più broker contemporaneamente (fino a 8) dalla nuova sezione "Broker MQTT" in Impostazioni. Ogni broker ha il proprio stato, i propri interruttori **Crittografia** e **TLS** (spenti per i broker nuovi; il broker predefinito mantiene la crittografia) e i propri limiti di invio.
- **Canali personalizzati per broker:** aggiungili a mano, importali dalla **radio collegata** o da un **link meshtastic.org/e/#…**. La chiave (PSK) si può mostrare solo dal PC.
- **Scelta del broker nella chat:** il campo "Invia via" ti fa scegliere il broker e il canale; sui messaggi compare un'etichetta con il broker di provenienza.
- **Stato MQTT spiegato e ricollegamento automatico:** MeshLens mostra se il broker è collegato, da quanto, quanti messaggi arrivano, quanti non si possono decodificare e l'ultimo errore, e si ricollega da solo se la connessione si blocca.
- **Backup automatici:** copia del database prima di ogni aggiornamento e di ogni migrazione, e una volta a settimana (ne restano 5), con elenco e **ripristino** da Impostazioni. Esportazione e importazione delle impostazioni (senza segreti, salvo richiesta dal PC).
- **Diagnostica:** log con rotazione e **pacchetto diagnostico** scaricabile (zip, senza password né chiavi).
- **Manutenzione del database:** indici per velocità, pulizia a blocchi che non rallenta l'app, statistiche e pulsante **"Compatta database"**.
- **Accesso più sicuro:** il blocco dopo troppi PIN errati resiste al riavvio (e il PC locale non resta mai chiuso fuori); elenco di sessioni e dispositivi con possibilità di **disconnetterli**; cambio PIN; con l'accesso dalla rete locale il PIN ha almeno **6 cifre** (i PIN già impostati continuano a funzionare).
- **HTTPS facoltativo per la rete locale** sulla porta 8687, con certificato generato da MeshLens (spento di default); su `127.0.0.1:8686` resta HTTP.
- **Token GitHub cifrato** con Windows DPAPI.
- **Interfaccia:** barra "connessione persa"; filtri attivi visibili come chip con **"Azzera filtri"**; **Riprova** e suggerimenti negli stati vuoti o di errore; ordinamento dei nodi e ricerca per modello e ruolo; la vista (scheda, mappa, ordinamento) viene ricordata; **link diretti ai nodi** (`#/nodes/!id`) con pulsante "Copia link".
- **Mappa:** distanze e azioni rapide nei popup, **righello**, raggruppamento dei nodi attivabile/disattivabile, **ricerca di un nodo** e **"Dove sono"**.
- **Nuovi avvisi** per i tuoi nodi: canale saturo, nodo tornato online, firmware vecchio.
- **Icona della scheda** del browser con il logo di MeshLens.

#### Modificato
- **Prima dell'aggiornamento MeshLens crea da solo un backup** del database.
- Dopo l'aggiornamento, la vecchia impostazione con un solo broker MQTT viene **migrata nell'elenco dei broker** (diventa il broker predefinito, che si può disattivare e modificare ma non eliminare).
- **Attenzione al ritorno alla 1.2.x:** dopo l'aggiornamento un downgrade fa perdere i broker personalizzati; in tal caso ripristina un backup precedente all'aggiornamento.
- I messaggi MQTT scartati per eccesso di traffico sono ora contati e visibili; se la connessione dell'interfaccia perde dati, si risincronizza da sola.

### English

#### Added
- **Several MQTT brokers at once:** connect multiple brokers (up to 8) from the new "MQTT brokers" section in Settings. Each broker has its own status, its own **Encryption** and **TLS** toggles (off for new brokers; the default broker keeps encryption) and its own send limits.
- **Custom channels per broker:** add them manually, import them from the **connected radio** or from a **meshtastic.org/e/#… link**. The key (PSK) can only be shown from the PC.
- **Broker picker in chat:** the "Send via" field lets you choose the broker and channel; messages carry a badge with the broker they came from.
- **MQTT status explained and automatic reconnection:** MeshLens shows whether the broker is connected, since when, how many messages arrive, how many cannot be decoded and the last error, and reconnects by itself if the connection stalls.
- **Automatic backups:** a database copy before every update and migration and once a week (kept separately by type: the most recent copies of each kind), with a list and **restore** in Settings. Settings export and import (without secrets unless requested from the PC).
- **Diagnostics:** rotating logs and a downloadable **diagnostic bundle** (zip, without passwords or keys).
- **Database maintenance:** indexes for speed, chunked purge that does not slow the app down, statistics and a **"Compact database"** button.
- **Safer access:** the lockout after too many wrong PINs survives restarts (and the local PC is never locked out); list of sessions and devices with the option to **sign them out**; change PIN; with LAN access the PIN has at least **6 digits** (existing PINs keep working).
- **Optional HTTPS for the local network** on port 8687, with a certificate generated by MeshLens (off by default); `127.0.0.1:8686` stays plain HTTP.
- **GitHub token encrypted** with Windows DPAPI.
- **Interface:** "connection lost" bar; active filters shown as chips with **"Clear filters"**; **Retry** and hints in empty or error states; node sorting and search by model and role; remembered view (tab, map, sorting); **direct node links** (`#/nodes/!id`) with a "Copy link" button.
- **Map:** distances and quick actions in popups, a **ruler**, optional node clustering, **node search** and **"Where am I"**.
- **New alerts** for your nodes: channel saturated, node back online, old firmware.
- **Browser tab icon** with the MeshLens logo.

#### Changed
- **MeshLens automatically takes a database backup before updating.**
- After updating, the old single-MQTT setting is **migrated to the broker list** (it becomes the default broker, which can be disabled and edited but not deleted).
- **Downgrading to 1.2.x after the update** loses custom brokers; restore a pre-update backup instead.
- MQTT messages dropped under heavy traffic are now counted and visible; if the interface connection misses data it resynchronises by itself.

## [1.2.3] - 2026-11-21

### Italiano

#### Modificato
- La sezione "Chat" si chiama ora **"Messaggi"** (barra in basso sul telefono e schede sul PC).

### English

#### Changed
- The "Chat" section is now called **"Messaggi"** (Messages) in the phone bottom bar and the desktop tabs.

## [1.2.2] - 2026-11-21

### Italiano

#### Corretto
- **Topic MQTT senza `/#`:** un topic come `msh/EU_868/IT` non riceveva nulla (MQTT lo intende come argomento esatto). Ora MeshLens aggiunge `/#` da solo, anche ai topic già salvati.
- **Invio via MQTT:** i messaggi venivano pubblicati sempre sotto `msh/EU_868`, mentre i gateway italiani con downlink ascoltano `msh/EU_868/IT`. Ora l'invio usa la radice del primo topic che ascolti (per esempio `msh/EU_868/IT/2/e/LongFast/...`).

### English

#### Fixed
- **MQTT topics without `/#`:** a topic like `msh/EU_868/IT` received nothing (MQTT treats it as an exact topic). MeshLens now appends `/#` automatically, also to saved topics.
- **Sending over MQTT:** messages were always published under `msh/EU_868`, while Italian downlink gateways listen on `msh/EU_868/IT`. Sending now uses the root of the first subscribed topic (for example `msh/EU_868/IT/2/e/LongFast/...`).

## [1.2.1] - 2026-11-21

### Italiano

#### Corretto
- **Mappe offline:** lo scaricamento diceva "Nessuna mappa Protomaps disponibile negli ultimi 7 giorni" perché il server di Protomaps rifiuta le richieste con il nome di client predefinito di Python. Ora MeshLens si presenta con il proprio nome e la mappa del giorno viene trovata.

### English

#### Fixed
- **Offline maps:** downloading said "No Protomaps map available in the last 7 days" because the Protomaps server rejects Python's default client name. MeshLens now identifies itself by name and the daily map is found.

## [1.2.0] - 2026-11-21

### Italiano

#### Aggiunto
- **Preferiti separati da "Mio nodo":** ★ Preferito per i nodi che vuoi seguire (stella, filtro "Preferiti" in Nodi e "Solo preferiti" in Rete, nessun avviso); ⌂ Mio nodo per i nodi tuoi (casetta, avvisi di batteria e silenzio, configurazione). Un nodo può essere entrambe le cose; sulla mappa casetta a sinistra e stella a destra.
- **Collegamenti dai gateway MQTT:** quando un gateway riceve un nodo direttamente via radio, MeshLens disegna il collegamento con il suo SNR (linea puntinata, voce in legenda). Si vedono collegamenti anche senza radio collegate.

#### Corretto
- **Salti dei nodi MQTT:** il broker pubblico azzera il contatore dei salti, quindi i valori mostrati erano sbagliati. Ora: "0 (diretto)", "≥ 1" se ritrasmesso, "—" se non si può sapere; i vecchi valori vengono azzerati all'avvio.

### English

#### Added
- **Favourites separate from "My node":** ★ Favourite for nodes you follow (star, "Favourites" filter in Nodes and "Favourites only" in Network, no alerts); ⌂ My node for your own nodes (house, battery and silence alerts, configuration). A node can be both; on the map the house is on the left and the star on the right.
- **Links from MQTT gateways:** when a gateway hears a node directly over radio, MeshLens draws the link with its SNR (dotted line, legend entry). Links show up even without connected radios.

#### Fixed
- **Hops of MQTT nodes:** the public broker zeroes the hop counter, so the shown values were wrong. Now: "0 (direct)", "≥ 1" when relayed, "—" when unknown; old values are cleared at startup.

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
[1.2.0]: https://github.com/iw8ffg/meshlens/releases/tag/v1.2.0
[1.2.1]: https://github.com/iw8ffg/meshlens/releases/tag/v1.2.1
[1.2.2]: https://github.com/iw8ffg/meshlens/releases/tag/v1.2.2
[1.2.3]: https://github.com/iw8ffg/meshlens/releases/tag/v1.2.3
[1.3.0]: https://github.com/iw8ffg/meshlens/releases/tag/v1.3.0
[1.4.0]: https://github.com/iw8ffg/meshlens/releases/tag/v1.4.0
[1.4.2]: https://github.com/iw8ffg/meshlens/releases/tag/v1.4.2
[1.4.1]: https://github.com/iw8ffg/meshlens/releases/tag/v1.4.1
