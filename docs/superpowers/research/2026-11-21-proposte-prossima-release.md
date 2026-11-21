# Proposte per la prossima release (analisi del 2026-11-21)

## Da dove vengono le proposte

Quattro analisi in parallelo:
1. confronto con app simili: client web Meshtastic, meshtastic-map di Liam Cottle, Malla, meshview, PotatoMesh;
2. funzioni del protocollo Meshtastic 2.5–2.7 non ancora usate;
3. usabilità dell'interfaccia;
4. solidità del server.

Ho ricontrollato a mano i punti chiave. Le analisi si basano sulla lettura del codice: niente è stato misurato.

## Cosa è già in programma

- Favicon con il logo.
- Canali personalizzati legati a un broker: inseriti a mano, importati dalla radio o da un link meshtastic.org.
- Più broker MQTT ascoltati insieme, con interruttori Crittografia e TLS e il menu del broker nel composer.

## Legenda

- Impegno: **P** = piccolo (ore), **M** = medio (1–2 giorni), **G** = grande.
- Ogni proposta ha un codice: per scegliere basta indicarlo (per esempio "A1, A3, B2").

---

## A. Interventi rapidi ad alto valore (P)

| # | Proposta | Perché |
|---|---|---|
| A1 | **Avviso "connessione persa"** quando la pagina perde il collegamento con il server. Oggi ritenta in silenzio e i dati restano fermi senza che tu lo sappia. | Oggi una pagina ferma sembra "rete morta" |
| A2 | **Filtri attivi visibili e pulsante "Azzera filtri"** quando mappa o elenco sono vuoti. I tuoi nodi e le tue radio non vengono mai nascosti dal filtro nazione. | Oggi, con un nodo fuori dall'Italia, la mappa appare vuota senza spiegazione |
| A3 | **"Riprova" e suggerimenti** negli stati di errore o vuoti: server non raggiungibile, feed, "Nessun messaggio" che porta a Radio o MQTT. | Ogni vicolo cieco diventa un'azione |
| A4 | **Stato MQTT spiegato.** Ultimo errore, connesso da, secondi dall'ultimo messaggio, riconnessioni, motivi di scarto dei pacchetti. Se non arriva nulla per N secondi, MeshLens si ricollega da sola. | Risponde a "perché non ricevo niente?" (come il caso del topic senza /#) |
| A5 | **Distanza nei popup.** Lunghezza del collegamento e distanza dalla tua radio. Nel popup del nodo, pulsanti "Messaggio diretto", "Dettagli" e "Copia id/coordinate". | Info chiave per chi fa radio, a costo minimo |
| A6 | **Ordinamento e ricerca in Nodi.** Ordina per recente, nome, SNR, salti o distanza. Cerca anche per modello e ruolo. | Oggi si ordina solo in Rete, nascosta in "Altro" sul telefono |
| A7 | **Ricorda la vista.** Scheda aperta, centro e zoom della mappa, ultima conversazione, ordinamento di Rete. Link diretto a un nodo (`#/nodes/!abc123`) da condividere. | Riaprire l'app e ritrovare tutto com'era |
| A8 | **Avvisi su dati già raccolti.** Utilizzo del canale alto (oltre il 25 %), nodo tornato online, firmware vecchio. | Si riusano i dati già salvati |
| A9 | **Indici del database e pulizia a piccoli blocchi.** Oggi la pulizia giornaliera cancella milioni di righe in un colpo solo, nello stesso processo che riceve i pacchetti. | Evita blocchi dell'interfaccia; più veloce all'avvio |
| A10 | **Log con rotazione.** Il file `meshlens.log` esiste ma cresce senza limite e registra solo gli errori gravi. Diventa 1 MB × 5 file, con un livello di dettaglio utile. | Per capire i problemi quando succedono |

## B. Funzioni nuove (M)

| # | Proposta | Perché |
|---|---|---|
| B1 | **Messaggi non letti e notifiche.** Contatore sulla scheda Messaggi, conversazioni in grassetto, `(n)` nel titolo della scheda del browser. Notifica del browser per i messaggi diretti a finestra nascosta (facoltativa). | Oggi un messaggio diretto che arriva mentre sei sulla mappa passa inosservato |
| B2 | **Elenco conversazioni al posto del menu a tendina.** Ordinato per ultima attività, con anteprima e ricerca. Sul telefono: lista, poi conversazione (come WhatsApp). Ogni conversazione ricorda la propria bozza. | Il menu attuale mescola feed, canali e messaggi diretti senza ordine |
| B3 | **Risposte e reazioni emoji.** Le mostra quando arrivano, così una reazione non appare più come un messaggio con la sola emoji. Si possono anche inviare. | Le app ufficiali lo fanno già |
| B4 | **Telemetria ambientale e di rete.** Temperatura, umidità, pressione, qualità dell'aria, potenza. Le "statistiche locali" dei nodi: pacchetti, duplicati, nodi online. Oggi si leggono solo batteria e tensione, il resto viene scartato. | Le stazioni meteo sono molto diffuse; i duplicati rivelano reti congestionate |
| B5 | **Grafici più ricchi.** Utilizzo del canale, airtime e SNR oltre a batteria e tensione, con valore al passaggio del mouse e periodo a scelta. | Dati già salvati e mai mostrati |
| B6 | **Esportazione dei dati.** CSV della tabella Rete, GPX del percorso di un nodo, GeoJSON/KML/CSV di una sessione di copertura. | Per Google Earth, QGIS, relazioni del club |
| B7 | **Percorso storico di un nodo con periodo a scelta.** Oggi è fisso alle ultime 24 h, mentre le posizioni restano salvate per 90 giorni. | Nodi mobili, escursioni, palloni |
| B8 | **Statistiche della rete.** Nodi online nel tempo, pacchetti all'ora, distribuzione di SNR e salti, nodi più attivi, modelli e ruoli. | È la mancanza più evidente rispetto ai siti tipo Malla e meshview |
| B9 | **Chiave pubblica dei nodi (PKI).** Lucchetto sui messaggi diretti cifrati. Avviso se la chiave di un nodo cambia (possibile falso nodo o reset). Errori di consegna spiegati in italiano. | Sicurezza e chiarezza sulla consegna |
| B10 | **Backup automatico del database e delle impostazioni** prima di ogni aggiornamento e ogni settimana. Esporta e importa le impostazioni (segreti nascosti). | Oggi un database rovinato o un aggiornamento fallito fa perdere tutto |
| B11 | **Waypoint.** Mostra sulla mappa i punti inviati dalla rete e permette di inviarne di propri. | Esercitazioni, protezione civile, eventi |
| B12 | **Notifiche esterne.** Notifica di Windows, poi eventualmente Telegram, per eventi come un tuo nodo spento, un nodo nuovo, una parola chiave in chat. | Monitorare senza tenere l'app aperta |
| B13 | **Strumenti mappa.** Righello, ricerca di un nodo sulla mappa, pulsante "dove sono", raggruppamento dei nodi disattivabile. | Uso sul campo |

## C. Progetti grandi (G)

| # | Proposta | Perché |
|---|---|---|
| C1 | **Copertura prevista.** Previsione dell'area raggiungibile da un nodo con il modello ITM e i dati di altitudine, da confrontare con le prove di copertura già misurate. | Nessun'altra app mette insieme copertura prevista e misurata: sarebbe la funzione distintiva |
| C2 | **Store & Forward.** Recupero dei messaggi persi da un nodo "router" quando il PC era spento. | Utile ma complesso |
| C3 | **Interfaccia in inglese.** | Per quando il repository diventa pubblico |
| C4 | **Ispettore dei pacchetti.** Filtri per nodo, tipo, segnale e tempo; contenuto grezzo, percorso. | Diagnosi avanzata |

## D. Sicurezza e solidità (per chi usa l'accesso dalla rete locale)

| # | Proposta | Impegno |
|---|---|---|
| D1 | **Blocco dei tentativi PIN che resta dopo il riavvio**, attese crescenti, PIN di almeno 6 cifre con l'accesso dalla rete locale, scadenza delle sessioni, elenco dei dispositivi collegati con revoca. | M |
| D2 | **HTTPS facoltativo** con certificato locale, per l'accesso dalla rete locale: oggi PIN e cookie viaggiano in chiaro sulla rete di casa. | M |
| D3 | **Token GitHub cifrato** con le funzioni di Windows (DPAPI) invece che in chiaro nel database. | P |
| D4 | **Coda limitata tra MQTT e app** con conteggio degli scarti; meno memoria per la deduplica doppia, che oggi tiene 2 × 200 000 voci. | M |
| D5 | **Avviso alla pagina quando perde eventi** (client lento), così ricarica i dati invece di restare indietro in silenzio. | P |

## Esclusa

- **Aggiornamento del firmware delle radio dall'app.** Rischioso e già coperto dagli strumenti ufficiali.

---

## La mia proposta per la 1.3.0, oltre a quanto già in programma

- **Tutto il gruppo A**: A1–A10, ognuno piccolo, insieme valgono molto.
- **B1 + B2**: messaggi non letti ed elenco conversazioni. Completano il lavoro sui messaggi e sui broker.
- **B4 + B5**: telemetria ambientale e grafici.
- **B10**: backup automatico prima degli aggiornamenti.

Da valutare per la release dopo: B3, B6, B7, B8, D1–D2 e C1 come progetto a sé.
