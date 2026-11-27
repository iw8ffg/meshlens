# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it-IT/1.1.0/) e il progetto usa il [versionamento semantico](https://semver.org/lang/it/).
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

## [1.6.3] - 2026-11-27

### Italiano

#### Aggiunto
- **Chiudi gli avvisi:** ogni avviso (in Rete → Nodi e nell'elenco in alto) ha una «×» per nasconderlo. Resta nascosto, anche dopo un riavvio e senza nuove notifiche, finché la situazione dura; se finisce e poi si ripresenta, l'avviso torna. «Avvisi nascosti: N — Mostra» li fa ricomparire.
- **Accetta la nuova chiave:** quando la chiave pubblica di un nodo cambia (ad esempio perché l'hai rigenerata tu), il pulsante «Accetta la nuova chiave» sull'avviso, nella scheda del nodo e nella conversazione toglie la segnalazione ovunque. Se la chiave cambia di nuovo, l'avviso ricompare.

### English

#### Added
- **Dismiss alerts:** every alert (in Network → Nodes and in the list at the top) has a "×" to hide it. It stays hidden, even after a restart and without new notifications, while the situation lasts; if it ends and happens again, the alert comes back. "Hidden alerts: N — Show" brings them back.
- **Accept the new key:** when a node's public key changes (for example because you regenerated it), the "Accept the new key" button on the alert, in the node card and in the conversation clears the warning everywhere. If the key changes again, the warning returns.

## [1.6.2] - 2026-11-25

### Italiano

#### Aggiunto
- **Salto rapido nelle Impostazioni:** in cima alla pagina un pulsante per ogni sezione porta direttamente lì; la sezione raggiunta è evidenziata. Sul telefono i pulsanti stanno in una riga fissa che scorre di lato. Anche la ricerca (Ctrl+K) porta alla sezione giusta.
- **Avviso dopo un aggiornamento:** se MeshLens si aggiorna mentre la pagina è aperta, compare un avviso con il pulsante «Ricarica» per passare alla nuova interfaccia.

#### Corretto
- **Pagina vecchia dopo l'aggiornamento:** la pagina principale non viene più tenuta nella cache del browser.

### English

#### Added
- **Quick jump in Settings:** at the top of the page a button for each section takes you straight there; the section you reach is highlighted. On phones the buttons sit in a fixed row that scrolls sideways. Search (Ctrl+K) also jumps to the right section.
- **Notice after an update:** if MeshLens is updated while the page is open, a notice with a "Reload" button lets you switch to the new interface.

#### Fixed
- **Old page after updating:** the main page is no longer kept in the browser cache.

## [1.6.1] - 2026-11-25

### Italiano

#### Modificato
- **Grafico della topologia per reti grandi:** i nodi non si schiacciano più contro i bordi; il gruppo principale sta al centro e i gruppi piccoli in una griglia ordinata a lato. L'area cresce con la rete, con zoom dalla rotellina (o con due dita), trascinamento e «Adatta».
- **Etichette leggibili:** i nomi compaiono per cerniere, hub, il nodo sotto il puntatore e i suoi vicini; ingrandendo compaiono gli altri, sempre senza sovrapporsi.
- **Disposizione geografica:** un interruttore mette i nodi con posizione GPS nel punto reale; gli altri vanno vicino ai loro collegamenti.
- **Focus su un nodo:** scegli un nodo e vedi solo lui e i vicini entro 1, 2 o 3 salti; «Mostra tutta la rete» torna alla vista completa.
- **Solo il gruppo principale:** nasconde i gruppi staccati; il limite di 400 nodi si riempie dal gruppo principale.
- **Più veloce:** il grafo si calcola in una frazione di secondo e mentre si calcola compare «Calcolo della disposizione…».

### English

#### Changed
- **Topology graph for large networks:** nodes no longer pile up against the edges; the main group sits in the middle and small groups in a tidy grid beside it. The area grows with the network, with wheel (or two-finger) zoom, dragging and "Fit".
- **Readable labels:** names appear for hinge nodes, hubs, the node under the pointer and its neighbours; zooming in shows the others, never overlapping.
- **Geographic layout:** a switch places nodes with a GPS position at their real location; the others go near their links.
- **Focus on a node:** pick a node and see only it and its neighbours within 1, 2 or 3 hops; "Show the whole network" goes back to the full view.
- **Main group only:** hides detached groups; the 400-node limit is filled from the main group.
- **Faster:** the graph is laid out in a fraction of a second, showing "Computing the layout…" meanwhile.

## [1.6.0] - 2026-11-24

### Italiano

> **Nota:** le funzioni che parlano con la radio (profili, comandi admin, messaggi predefiniti, preferiti e ignorati, traceroute automatici, bot) sono state provate con radio simulate, non ancora con radio reali. Provale prima su un nodo di prova e segnalaci ogni differenza.

#### Aggiunto
- **Primo avvio guidato e stati vuoti:** al primo avvio una lista di passi (collega una radio o un broker, scegli i canali, segna i tuoi nodi) ti accompagna; le pagine ancora vuote mostrano pulsanti per fare il passo successivo invece di una schermata bianca.
- **Ricerca globale (Ctrl+K):** da qualsiasi pagina trovi al volo azioni, nodi, conversazioni, impostazioni e messaggi.
- **Ricerca nei messaggi ed esportazione:** cerchi nel testo dei messaggi e salti al punto della conversazione; ogni conversazione si esporta in **TXT, CSV o JSON**.
- **Messaggi rapidi con variabili:** risposte pronte con segnaposto ({batteria}, {posizione}, {ora}) da inserire con un tocco; si gestiscono da Impostazioni.
- **Avvisi su misura:** crei regole tue: parola chiave in un canale, segnale debole, **ingresso o uscita da una zona disegnata sulla mappa**, soglie di batteria e di silenzio per singolo nodo. Dopo un avviso la regola resta in pausa per non ripeterlo di continuo.
- **Detection Sensor e Paxcounter:** gli eventi dei sensori di rilevamento compaiono nella scheda del nodo e il conteggio dei dispositivi del Paxcounter ha il suo grafico.
- **Pagina «Salute rete»:** stato delle batterie con **autonomia stimata** («circa N giorni»; per i nodi a pannello solare si tiene conto dell'andamento) e **confronto fra nodi**.
- **Strati della mappa:** cerchi di precisione della posizione, mappa di densità, solo infrastruttura (router e ripetitori), **etichette SNR sui collegamenti** e contatti **ATAK**.
- **Grafico della topologia:** in Rete vedi la rete come grafo, con nodi **cerniera** (se cadono dividono la rete), **hub** e **isolati**. Puoi attivare Neighbor Info sulla tua radio; ha dei limiti: si invia al massimo ogni 4 ore e passa in radio solo con un canale primario non predefinito.
- **Preferiti e nodi ignorati sincronizzati con la radio:** segni un nodo come preferito o da ignorare e lo stato passa alla radio. I nodi ignorati spariscono da mappa, elenchi, messaggi e avvisi; l'operazione si annulla in ogni momento. Un tuo nodo si ignora solo in MeshLens, mai sulle radio.
- **Profili di configurazione e confronto fra radio:** salvi la configurazione di una radio come profilo, la applichi a un'altra con anteprima delle differenze e confronti due radio. I profili **non copiano mai** chiavi, nome proprietario, canali, regione, WiFi e console seriale.
- **Messaggi predefiniti per T-Deck e T-Pager:** leggi e modifichi le frasi pronte della radio (fino a 200 caratteri).
- **Avviso sulla privacy della posizione:** se un canale pubblico o MQTT diffonde la posizione con precisione migliore di circa 1,5 km, MeshLens avvisa e propone una correzione guidata.
- **Condivisione dei canali:** link di condivisione e **codice QR** del canale (solo da questo PC), generatore di chiavi (PSK) e **avviso per le chiavi deboli**.
- **Comandi admin remoti:** riavvio, impostazione dell'ora, azzeramento dell'elenco nodi e spegnimento, con **conferma rafforzata** e, per i nodi remoti, solo se la tua chiave pubblica è tra le loro chiavi admin.
- **Traceroute periodici:** programmi un traceroute automatico per nodo (al massimo uno ogni ora per nodo) e consulti lo **storico dei percorsi** con i cambi di strada.
- **Bot (a scelta, canale per canale):** risponde via radio e MQTT a `!ping`, `!info`, `!ora`, `!meteo` e a risposte personalizzate. Le risposte iniziano con `[bot]` e ci sono limiti di frequenza. È spento finché non lo attivi; attivazione e canali si cambiano solo da questo PC.
- **Webhook in uscita:** invia eventi scelti a un indirizzo tuo, solo **https verso Internet**, senza proxy; non raggiunge questo PC né la rete locale.
- **Finestra «Novità»:** dopo un aggiornamento mostra le note della nuova versione.
- **Diagnosi del collegamento radio:** una procedura guidata controlla porta, rete e risposta della radio e dà consigli concreti. Si prova solo su radio già salvate.
- **Spazio per tabella e conservazione per broker:** in Manutenzione vedi quanto spazio occupa ogni tabella e imposti per quanto tempo tenere i messaggi MQTT di ciascun broker; lo storico dei traceroute resta 365 giorni.
- **Accesso ospite con un secondo PIN:** chi lo inserisce vede solo mappa, nodi e statistiche, in **sola lettura**. Si attiva da Impostazioni, solo da questo PC.
- **Per chi sviluppa:** radio finta e strumenti di replay dei pacchetti per provare MeshLens senza hardware.

#### Modificato
- **Importazione impostazioni e ripristino backup:** non attivano mai da soli bot, webhook, accesso ospite e traceroute automatici.
- **Ispettore dei pacchetti:** mostra i tipi Sensore, Paxcounter e ATAK.
- **Nodi aggiornati:** i pacchetti Detection, Paxcounter e ATAK ora aggiornano anche il nodo (ultimo contatto e dati).

#### Corretto
- **Decifratura:** in rari casi un'impostazione cifrata non leggibile poteva risultare letta correttamente.
- **Icona nell'area di notifica:** alla chiusura vengono mostrati i toast già in coda (al massimo 2 secondi).
- **Messaggi predefiniti:** una lettura senza risposta non mostra più il testo precedente.
- **Traceroute automatici:** dopo un errore del database non vengono ripetuti a raffica, e l'intervallo resta se il nodo viene riaggiunto; tetto orario, intervallo minimo e pausa del bot restano dopo il riavvio.
- **Zone e ricerca:** le zone non scattano più su posizioni riprodotte dallo storico; ricerca più robusta.
- **Profili:** non copiano i campi che possono scollegare la radio e mostrano un'anteprima con avviso.
- **Interfaccia:** le graffe scritte a mano non bloccano più l'invio; le variabili dei messaggi rapidi si azzerano cambiando conversazione; grafo della topologia più stabile; correzioni di accessibilità.

#### Sicurezza
- **Documentazione automatica di FastAPI disattivata** (`/docs`, `/redoc`, `/openapi.json`).
- **Accesso ospite:** negato per impostazione predefinita su ogni rotta; l'ospite non vede mai testi liberi di sensori né avvisi personalizzati; massimo 20 sessioni ospite.
- **Bot e webhook:** con la funzione attiva, la configurazione non si cambia dalla rete locale.
- **Nodi:** non si ignora un nodo con una sessione admin aperta.

### English

> **Note:** features that talk to the radio (profiles, admin commands, canned messages, favorites and ignored nodes, automatic traceroutes, bots) were tested with simulated radios, not yet with real hardware. Try them on a spare node first and tell us about any difference.

#### Added
- **Guided first start and empty states:** on first launch a checklist (connect a radio or broker, pick channels, mark your nodes) guides you; pages that are still empty show buttons for the next step instead of a blank screen.
- **Global search (Ctrl+K):** from any page, quickly find actions, nodes, conversations, settings and messages.
- **Message search and export:** search message text and jump to the spot in the conversation; any conversation exports as **TXT, CSV or JSON**.
- **Quick replies with variables:** ready-made replies with placeholders ({batteria}, {posizione}, {ora}) inserted with one tap; managed in Settings.
- **Custom alerts:** create your own rules: a keyword in a channel, weak signal, **entering or leaving a zone drawn on the map**, per-node battery and silence thresholds. After an alert the rule pauses so it does not repeat constantly.
- **Detection Sensor and Paxcounter:** detection sensor events appear in the node page and the Paxcounter device count has its own chart.
- **Network "Health" page:** battery status with **estimated autonomy** ("about N days"; for solar nodes the trend is taken into account) and **node comparison**.
- **Map layers:** position precision circles, density map, infrastructure only (routers and repeaters), **SNR labels on links** and **ATAK** contacts.
- **Topology graph:** in Network you see the mesh as a graph, with **hinge** nodes (if they fail the network splits), **hubs** and **isolated** nodes. You can enable Neighbor Info on your radio; it has limits: it is sent at most every 4 hours and goes over the air only with a non-default primary channel.
- **Favorites and ignored nodes synced with the radio:** mark a node as favorite or ignored and the state is sent to the radio. Ignored nodes disappear from the map, lists, messages and alerts; this can be undone at any time. One of your own nodes is ignored only in MeshLens, never on the radios.
- **Configuration profiles and radio comparison:** save a radio's configuration as a profile, apply it to another radio with a preview of the differences, and compare two radios. Profiles **never copy** keys, owner name, channels, region, WiFi or the serial console.
- **Canned messages for T-Deck and T-Pager:** read and edit the radio's ready phrases (up to 200 characters).
- **Position privacy warning:** if a public or MQTT channel shares your position with precision better than about 1.5 km, MeshLens warns you and offers a guided fix.
- **Channel sharing:** share link and **QR code** for a channel (from this PC only), key (PSK) generator and **weak key warning**.
- **Remote admin commands:** reboot, set the time, reset the node list and shut down, with **strong confirmation** and, for remote nodes, only if your public key is among their admin keys.
- **Periodic traceroute:** schedule an automatic traceroute per node (at most one per hour per node) and browse the **route history** with path changes.
- **Bots (opt-in, channel by channel):** replies over radio and MQTT to `!ping`, `!info`, `!ora`, `!meteo` and to custom replies. Replies start with `[bot]` and rate limits apply. It stays off until you enable it; enabling and channel scope can only be changed from this PC.
- **Outgoing webhooks:** send chosen events to an address of yours, **https to the Internet only**, no proxy; it cannot reach this PC or the local network.
- **"What's new" window:** after an update it shows the notes of the new version.
- **Radio connection diagnosis:** a guided procedure checks port, network and radio response and gives concrete advice. It only runs on saved radios.
- **Storage per table and per-broker retention:** in Maintenance see how much space each table uses and set how long MQTT messages are kept for each broker; traceroute history is kept for 365 days.
- **Guest access with a second PIN:** whoever enters it sees only the map, nodes and statistics, **read-only**. Enable it in Settings, from this PC only.
- **For developers:** a fake radio and packet replay tools to try MeshLens without hardware.

#### Changed
- **Settings import and backup restore:** they never turn on bots, webhooks, guest access or automatic traceroutes by themselves.
- **Packet inspector:** shows the Sensor, Paxcounter and ATAK types.
- **Updated nodes:** Detection, Paxcounter and ATAK packets now also update the node (last contact and data).

#### Fixed
- **Decryption:** in rare cases an unreadable encrypted setting could appear to be read correctly.
- **Notification-area icon:** on exit, toasts already queued are shown (2 seconds at most).
- **Canned messages:** a read with no answer no longer shows the previous text.
- **Automatic traceroutes:** after a database error they are not repeated in a burst, and the interval is kept if the node is added again; the bot's hourly cap, minimum interval and pause survive a restart.
- **Zones and search:** zones no longer trigger on positions replayed from history; more robust search.
- **Profiles:** they do not copy fields that could disconnect the radio and show a preview with a warning.
- **Interface:** hand-typed braces no longer block sending; quick-reply variables reset when you switch conversation; steadier topology graph; accessibility fixes.

#### Security
- **FastAPI automatic documentation disabled** (`/docs`, `/redoc`, `/openapi.json`).
- **Guest access:** denied by default on every route; the guest never sees free-text sensor events or custom alerts; at most 20 guest sessions.
- **Bots and webhooks:** while the feature is on, its configuration cannot be changed from the local network.
- **Nodes:** a node with an open admin session cannot be ignored.

## [1.5.1] - 2026-11-23

### Italiano

#### Corretto
- **Invii MQTT:** un messaggio segnalato come non inviato o «Non confermato» non parte più di nascosto alla riconnessione, e dopo molti invii senza conferma i nuovi partono ancora.
- **Stato dei messaggi dopo una disconnessione:** «Invio…» e «Accettato dal broker» si aggiornano quando l'app si ricollega, senza ricaricare la pagina; anche i messaggi pubblici arrivati nel frattempo compaiono.
- **«Carica precedenti»:** non si blocca più nel feed MQTT quando i messaggi più vecchi sono nascosti dal filtro nazioni, né nelle conversazioni radio con molti messaggi; non salta i messaggi arrivati nello stesso secondo.
- **Radio via rete (IP):** una radio spenta o irraggiungibile dà errore in pochi secondi invece di bloccare la chiusura dell'app; una radio che sparisce dalla rete viene rilevata in meno di un minuto e ricollegata; messaggio chiaro se la porta risponde ma non è Meshtastic o la radio ha già un altro collegamento.
- **Radio occupata:** durante una lettura o scrittura della configurazione, messaggi e traceroute rispondono subito «Radio occupata, riprova tra poco» invece di restare in attesa per minuti.
- **Backup:** il backup scelto per il ripristino non viene più cancellato dalla pulizia automatica prima del riavvio.
- **Sicurezza:** la chiave dei canali della radio si mostra solo da questo PC; l'accesso dalla rete richiede un PIN di almeno 6 cifre; le richieste che modificano dati accettano solo JSON; due impostazioni del PIN contemporanee non si sovrascrivono.
- **Canali:** una chiave di canale di lunghezza non valida viene rifiutata prima di scriverla sulla radio; un canale personalizzato tolto smette di decifrare.
- **Traceroute:** i passaggi sconosciuti non creano più un nodo «!ffffffff» né collegamenti inventati.
- **Varie:** testo scritto durante un invio lento non viene più cancellato; l'app si accorge di una connessione caduta dopo la sospensione del PC; funziona anche nei browser che bloccano i dati dei siti; l'installer rimuove i file della versione precedente; minore uso di memoria con broker molto trafficati.

### English

#### Fixed
- **MQTT sends:** a message reported as not sent or "Not confirmed" is no longer sent silently on reconnect, and after many unconfirmed sends new ones still go out.
- **Message status after a disconnection:** "Sending…" and "Accepted by the broker" update when the app reconnects, without reloading the page; public messages received meanwhile appear too.
- **"Load older":** no longer stuck in the MQTT feed when older messages are hidden by the country filter, nor in radio conversations with many messages; messages within the same second are no longer skipped.
- **Radio over the network (IP):** a radio that is off or unreachable fails within seconds instead of holding up the app's exit; a radio that drops off the network is detected within a minute and reconnected; clear message when the port answers but is not Meshtastic or the radio already has another connection.
- **Busy radio:** while the configuration is being read or written, messages and traceroutes answer "Radio busy, try again shortly" right away instead of waiting for minutes.
- **Backups:** the backup chosen for restore is no longer deleted by automatic cleanup before the restart.
- **Security:** radio channel keys are shown only from this PC; network access requires a PIN of at least 6 digits; requests that change data accept JSON only; two simultaneous PIN setups cannot overwrite each other.
- **Channels:** a channel key of invalid length is rejected before it is written to the radio; a removed custom channel stops decrypting.
- **Traceroute:** unknown hops no longer create a "!ffffffff" node or invented links.
- **Other:** text typed during a slow send is no longer cleared; the app notices a dropped connection after the PC sleeps; it works in browsers that block site data; the installer removes files from the previous version; lower memory use with very busy brokers.

## [1.5.0] - 2026-11-23

### Italiano

#### Aggiunto
- **Radio via rete (IP):** in Radio → Aggiungi radio c'è la scheda «Rete (IP)» per collegare una radio con WiFi o Ethernet attivo, indicando indirizzo e porta (di solito 4403).
- **Esito degli invii MQTT:** ogni messaggio inviato via MQTT mostra «Invio…», poi «Accettato dal broker» quando il broker lo conferma e «Sentito in radio da …» quando un altro gateway o una tua radio lo ricevono: è la prova che è andato davvero in onda. Se il broker non conferma entro 15 secondi compare «Non confermato».
- **Sottoscrizioni rifiutate:** se un broker accetta la connessione ma rifiuta l'ascolto di qualche topic, Impostazioni → MQTT e lo stato in alto lo segnalano con l'elenco dei topic rifiutati.

#### Modificato
- **Id nodo per MQTT:** il campo non mostra più un id di esempio, che si poteva scambiare per un valore vero; il suggerimento spiega che deve essere l'id di una tua radio.

### English

#### Added
- **Radio over the network (IP):** Radio → Add radio has a "Network (IP)" tab to connect a radio with WiFi or Ethernet enabled, by address and port (usually 4403).
- **MQTT send outcome:** every message sent over MQTT shows "Sending…", then "Accepted by the broker" once the broker confirms it and "Heard on radio by …" when another gateway or one of your radios receives it: proof it really went on air. If the broker does not confirm within 15 seconds it shows "Not confirmed".
- **Refused subscriptions:** if a broker accepts the connection but refuses some topics, Settings → MQTT and the top status show it with the list of refused topics.

#### Changed
- **MQTT node ID:** the field no longer shows an example ID that could be mistaken for a real value; the hint explains it must be the ID of one of your radios.

## [1.4.5] - 2026-11-23

### Italiano

#### Corretto
- **Canale nella conversazione di un broker:** in «Pubblico · <broker>» la casella di invio mostra di nuovo la scelta del canale MQTT; resta nascosta solo la scelta del broker, già deciso dalla conversazione.

### English

#### Fixed
- **Channel in a broker conversation:** in "Public · <broker>" the send box shows the MQTT channel choice again; only the broker choice stays hidden, since the conversation already sets it.

## [1.4.4] - 2026-11-23

### Italiano

#### Aggiunto
- **Pubblico per broker:** con più broker MQTT, in Messaggi trovi «Pubblico · tutti i broker» e una conversazione pubblica per ciascun broker. Ognuna mostra solo i messaggi di quel broker e invia su quel broker, senza doverlo scegliere.
- **Casella di invio a sinistra:** con Messaggi a tutta pagina, la casella per scrivere sta nella colonna di sinistra sotto le conversazioni; la parte centrale resta tutta per la lettura.

#### Corretto
- **Messaggi pubblici precedenti:** «Carica precedenti» compare anche quando il feed non ha ancora messaggi in arrivo.
- **Avvio di sviluppo (`start.bat`):** se MeshLens è già attivo apre il browser invece di dare errore, e avvisa che è la versione di sviluppo con dati separati.

### English

#### Added
- **Public per broker:** with several MQTT brokers, Messages shows "Public · all brokers" and one public conversation per broker. Each shows only that broker's messages and sends on that broker, with no need to pick it.
- **Send box on the left:** with full-page Messages, the box for writing sits in the left column below the conversations; the centre stays free for reading.

#### Fixed
- **Older public messages:** "Load older" also appears when the feed has no incoming messages yet.
- **Development start (`start.bat`):** if MeshLens is already running it opens the browser instead of failing, and warns that it is the development version with separate data.

## [1.4.3] - 2026-11-22

### Italiano

#### Aggiunto
- **Messaggi a tutta pagina:** su computer il pulsante Espandi, accanto alla ricerca delle conversazioni, porta Messaggi a tutta pagina con l'elenco delle conversazioni a sinistra e quella aperta a destra. La scelta viene ricordata; Riduci riporta il pannello accanto alla mappa. Su telefono non cambia nulla.
- **Scheda del nodo sopra la chat:** a tutta pagina, il clic sul nome di chi scrive apre la scheda del nodo senza lasciare la conversazione; «Mostra sulla mappa» torna alla vista con la mappa centrata sul nodo.

### English

#### Added
- **Full-page messages:** on desktop the Expand button, next to the conversation search, turns Messages into a full page with the conversation list on the left and the open one on the right. The choice is remembered; Shrink brings back the panel next to the map. Nothing changes on phones.
- **Node details over the chat:** in full page, clicking a sender's name opens the node details without leaving the conversation; "Show on map" goes back to the map view centred on the node.

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
[1.6.3]: https://github.com/iw8ffg/meshlens/releases/tag/v1.6.3
[1.6.2]: https://github.com/iw8ffg/meshlens/releases/tag/v1.6.2
[1.6.1]: https://github.com/iw8ffg/meshlens/releases/tag/v1.6.1
[1.6.0]: https://github.com/iw8ffg/meshlens/releases/tag/v1.6.0
[1.5.1]: https://github.com/iw8ffg/meshlens/releases/tag/v1.5.1
[1.5.0]: https://github.com/iw8ffg/meshlens/releases/tag/v1.5.0
[1.4.5]: https://github.com/iw8ffg/meshlens/releases/tag/v1.4.5
[1.4.4]: https://github.com/iw8ffg/meshlens/releases/tag/v1.4.4
[1.4.3]: https://github.com/iw8ffg/meshlens/releases/tag/v1.4.3
[1.4.2]: https://github.com/iw8ffg/meshlens/releases/tag/v1.4.2
[1.4.1]: https://github.com/iw8ffg/meshlens/releases/tag/v1.4.1
