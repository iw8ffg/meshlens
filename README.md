<p align="center"><img src="docs/img/banner-it.svg" alt="MeshLens" width="720"></p>

<p align="center">🇬🇧 <a href="README.en.md">English</a></p>

<p align="center">
  <img alt="Licenza GPL-3.0" src="https://img.shields.io/badge/licenza-GPL--3.0-blue">
  <img alt="Piattaforma Windows" src="https://img.shields.io/badge/piattaforma-Windows%2010%2F11-0078D6">
  <img alt="Versione 1.6.0" src="https://img.shields.io/badge/versione-1.6.0-brightgreen">
</p>

**MeshLens** è un'applicazione locale per Windows che riunisce in un'unica mappa interattiva tutto ciò che accade su una rete [Meshtastic](https://meshtastic.org): i nodi sentiti da **Internet (MQTT)** e dalle **tue radio** collegate via USB o Bluetooth. Osservi la rete, gestisci i tuoi nodi e chatti via radio, anche senza Internet. Si usa dal PC e dal telefono sulla stessa Wi-Fi.

## Schermate

| | |
|---|---|
| ![Mappa con i nodi e i waypoint](docs/img/screen-map.png)<br>**Mappa** | ![Scheda Rete con selettore Nodi, Statistiche, Pacchetti](docs/img/screen-network.png)<br>**Rete** |
| ![Chat con risposte, reazioni e lucchetto PKI](docs/img/screen-chat.png)<br>**Chat** | ![Elenco delle conversazioni con non letti e bozze](docs/img/screen-chat-list.png)<br>**Conversazioni** |
| ![Waypoint sulla mappa](docs/img/screen-waypoint.png)<br>**Waypoint** | ![Copertura prevista confrontata con le misure](docs/img/screen-prediction.png)<br>**Copertura prevista** |
| ![Statistiche della rete](docs/img/screen-stats.png)<br>**Statistiche** | ![Ispettore dei pacchetti](docs/img/screen-packets.png)<br>**Pacchetti** |
| ![Dettaglio nodo](docs/img/screen-node.png)<br>**Dettaglio nodo** | ![Prova di copertura](docs/img/screen-coverage.png)<br>**Copertura sul campo** |
| ![Impostazioni](docs/img/screen-settings.png)<br>**Impostazioni** | ![Vista telefono](docs/img/screen-mobile.png)<br>**Telefono** |
| ![Interfaccia in inglese](docs/img/screen-english.png)<br>**Interfaccia in inglese** |  |

> Le schermate usano un database dimostrativo con nodi, messaggi e posizioni inventati.

## Funzioni principali

### 🗺️ Mappa e osservazione
- Nodi da MQTT e da radio fusi in un'unica vista, con colore per fonte e per ultimo contatto.
- Filtri per nazione, fonte, radio, ultimo contatto, ruolo e testo; i filtri attivi restano visibili come chip, con **"Azzera filtri"**.
- Dettaglio nodo: hardware, ruolo, firmware, posizione e precisione, batteria, SNR/RSSI/hop, traccia dei percorsi con **periodo a scelta fino a 90 giorni**; **link diretto** al nodo (`#/nodes/!id`).
- Mappa: distanze e azioni rapide nei popup, **righello**, raggruppamento dei nodi attivabile, **ricerca di un nodo**, **"Dove sono"** e **waypoint** ricevuti.
- Ordinamento dei nodi e ricerca anche per modello e ruolo; la vista viene ricordata.
- Feed dei messaggi pubblici MQTT, filtrabile per nazione, con l'indicazione del broker di provenienza.
- **Strati della mappa** dalla legenda: cerchi di precisione, densità, solo infrastruttura, **etichette SNR sui collegamenti** e contatti **ATAK**.
- **Primo avvio guidato** con checklist e pulsanti d'azione nelle pagine ancora vuote.

### 📻 Radio e chat
- Più radio insieme, via **USB** e **Bluetooth**, con riconnessione automatica.
- Messaggi su canali e diretti, con stato di consegna e un unico campo **"Invia via"**: radio oppure **MQTT** (solo testo, a nome del tuo nodo, con conferma la prima volta), con scelta del **broker** e del canale.
- Interfaccia con tema **scuro e chiaro**, pensata anche per il telefono.

### 💬 Messaggi
- **Elenco delle conversazioni** con anteprima, **ricerca** e **bozze**; contatori dei **non letti**, `(n)` nel titolo della scheda e **notifiche del browser** per i messaggi diretti.
- **Risposte e reazioni con emoji**, via radio e via MQTT.
- **Lucchetto** sui messaggi diretti cifrati con la chiave pubblica (PKI), **avviso quando la chiave di un nodo cambia** e motivo degli errori di consegna in italiano.
- **Waypoint**: quelli ricevuti compaiono sulla mappa; i tuoi si inviano solo via radio.
- **Notifiche esterne**: notifiche di Windows dall'icona nell'area di notifica e, se lo attivi, **bot Telegram** (token salvato cifrato).
- **Recupera messaggi persi** (Store & Forward): dalla scheda Radio chiedi a un nodo router lo storico dei messaggi che ti sei perso, senza duplicati.
- **Ricerca nei messaggi** (e globale con **Ctrl+K**) ed **esportazione** di una conversazione in TXT, CSV o JSON.
- **Messaggi rapidi con variabili** (batteria, posizione, ora) da inserire con un tocco.

### 🌐 Più broker MQTT e canali personalizzati
- Collega **più broker MQTT insieme**, ognuno con il proprio stato e i propri interruttori **Crittografia** e **TLS** (spenti per i broker nuovi; il broker predefinito mantiene la crittografia).
- **Canali personalizzati** per broker: aggiunti a mano, importati dalla radio collegata o da un link `meshtastic.org/e/#…`. La chiave si può mostrare solo dal PC.
- Stato MQTT spiegato (connessione, messaggi al secondo, non decodificabili, ultimo errore) e **ricollegamento automatico**.

### 📊 Gestione della rete
- Stato dei nodi, **batteria con grafico storico** e avvisi: batteria bassa, nodi silenziosi, **canale saturo**, **nodo tornato online**, **firmware vecchio**.
- "I miei nodi": marca i tuoi, viste e avvisi si concentrano su di loro.
- Mappa dei collegamenti colorata per SNR e **traceroute** a richiesta.
- Barra "connessione persa" e pulsanti **Riprova** quando qualcosa non risponde.
- Pagina **Salute rete**: batterie con **autonomia stimata** («circa N giorni», anche per i nodi solari) e **confronto fra nodi**.
- **Topologia** a grafo con nodi cerniera, hub e isolati; attivazione di Neighbor Info (con i suoi limiti).
- **Traceroute periodici** per nodo (al massimo uno ogni ora) con **storico dei percorsi**.
- **Preferiti e nodi ignorati** sincronizzati con la radio: gli ignorati spariscono da mappa, messaggi e avvisi, in modo reversibile.
- **Detection Sensor** e grafico **Paxcounter** nella scheda del nodo.

### 📈 Dati e statistiche
- **Telemetria** di ambiente, qualità dell'aria, alimentazione e statistiche locali dei nodi, da MQTT e da radio.
- **Grafici** con lettura dei valori al passaggio del mouse e **periodo a scelta** (anche uso del canale, SNR e sensori).
- **Esportazioni** in **CSV** (con `;`, adatto a Excel), **GPX**, **GeoJSON** e **KML**.
- **Statistiche della rete** e **ispettore dei pacchetti** nella pagina Rete, con impostazioni di conservazione per limitare lo spazio.

### 📡 Copertura sul campo
- Prove di copertura con il modulo Range Test: punti colorati per qualità del segnale, percorso, punti mancanti e storico delle sessioni.
- "Prepara le radio" e "Ripristina" per impostare e rimettere a posto la configurazione.

### 📡 Copertura prevista
- **Previsione della copertura** di un sito (posizione, altezza dell'antenna, potenza, guadagni) con il modello **NTIA ITM** e i dati di altitudine **Terrarium**, scaricati solo dopo la tua conferma.
- Risultato sovrapposto alla mappa e **confronto con le misure** del Range Test; avviso se la potenza supera il limite di legge EU 868.

### ⚙️ Configurazione
- Lettura e modifica della configurazione delle radio collegate e dei nodi remoti (chiavi admin PKI).
- Ogni modifica passa da un **riepilogo delle differenze**, una **conferma esplicita** e una **copia di sicurezza ripristinabile**.
- **Profili di configurazione** e **confronto fra due radio**; i profili non copiano mai chiavi, proprietario, canali, regione, WiFi e console seriale.
- **Messaggi predefiniti** di T-Deck e T-Pager (200 caratteri) e **comandi admin remoti** (riavvio, ora, azzeramento elenco nodi, spegnimento) con conferma rafforzata e chiave admin.
- **Privacy della posizione:** avviso se un canale pubblico o MQTT la diffonde con precisione migliore di circa 1,5 km.
- **Condivisione dei canali** con link e **QR**, generatore di chiavi e avviso per le **chiavi deboli**.

### 🤖 Automazioni
- **Avvisi su misura:** parola chiave in un canale, segnale debole, **ingresso o uscita da una zona** disegnata sulla mappa, soglie di batteria e silenzio per nodo.
- **Bot** opt-in canale per canale (radio e MQTT): `!ping`, `!info`, `!ora`, `!meteo` e risposte personalizzate, con prefisso `[bot]` e limiti di frequenza; si attiva solo da questo PC.
- **Webhook in uscita** su eventi scelti: solo https verso Internet, senza proxy.
- Importare impostazioni o ripristinare un backup non attiva mai bot, webhook, accesso ospite e traceroute automatici.

### 🔎 Ricerca
- **Ricerca globale (Ctrl+K)** su azioni, nodi, conversazioni, impostazioni e messaggi.

### 👤 Accesso ospite
- Un **secondo PIN** apre una vista in **sola lettura** con solo mappa, nodi e statistiche.

> **Nota sulle prove:** le funzioni che parlano con la radio (profili, comandi admin, messaggi predefiniti, preferiti e ignorati, traceroute automatici, bot) sono state provate con radio simulate, non ancora con radio reali.

### 🌍 Offline e lingua
- Mappe PMTiles scaricabili con un passo guidato: mondo a basso dettaglio, Italia e aree a scelta.
- Passaggio automatico tra mappa online e offline.
- Interfaccia disponibile in **italiano** (predefinito) e in **inglese**: la lingua si sceglie in Impostazioni.

### 🔒 Accesso dalla rete locale e HTTPS
- Di default MeshLens ascolta solo sul PC (`http://127.0.0.1:8686`). L'accesso dalla rete locale si attiva in Impostazioni ed è protetto dal PIN.
- Con l'accesso dalla rete locale il PIN ha almeno **6 cifre** (i PIN già impostati continuano a funzionare). Dopo troppi errori scatta un blocco che resiste al riavvio; il PC locale non resta mai chiuso fuori.
- In Impostazioni vedi **sessioni e dispositivi** collegati e puoi disconnetterli; puoi anche cambiare il PIN.
- **HTTPS facoltativo** (spento di default) sulla porta **8687**, con certificato autofirmato generato da MeshLens: la prima volta il browser mostrerà un avviso da accettare. Su `127.0.0.1:8686` resta HTTP.
- I token (GitHub per gli aggiornamenti, bot Telegram) sono salvati cifrati con Windows DPAPI.

### 🧰 Backup e diagnostica
- **Backup automatici** del database: prima di ogni aggiornamento e migrazione e una volta a settimana (ne restano 5). Elenco e **ripristino** da Impostazioni.
- **Esporta e importa le impostazioni** (i segreti restano esclusi salvo richiesta dal PC).
- **Pacchetto diagnostico** scaricabile (zip, senza password né chiavi) e log con rotazione.
- **Manutenzione del database:** pulizia a blocchi, statistiche e pulsante **"Compatta database"**.
- **Diagnosi del collegamento radio** guidata, con consigli concreti.
- **Spazio per tabella** e **conservazione per broker** dei messaggi MQTT; finestra **«Novità»** dopo gli aggiornamenti.
- Radio finta e strumenti di replay per chi sviluppa (prove senza hardware).

## Requisiti

- Windows 10 o 11.
- Una radio Meshtastic con firmware **2.5 o superiore** (provato con il **2.7**), se vuoi usare le radio. Per la sola osservazione MQTT non serve alcuna radio.

## Installazione

1. Scarica `MeshLens-Setup-X.Y.Z.exe` dalla pagina [Releases](https://github.com/iw8ffg/meshlens/releases) (finché il repository è privato serve l'accesso con il tuo account GitHub).
2. Controlla l'impronta con il file `.sha256` allegato (facoltativo ma consigliato): `certutil -hashfile MeshLens-Setup-X.Y.Z.exe SHA256`.
3. Avvia l'installer. È **per utente**: non servono i permessi di amministratore.
4. **SmartScreen:** l'installer non è firmato, quindi Windows può mostrare "Windows ha protetto il PC". Scegli **Ulteriori informazioni → Esegui comunque**.

MeshLens parte con un'icona nell'area di notifica (Apri MeshLens, Apri cartella dati, Avvia all'accesso, Esci). Disinstallando, i dati in `%LOCALAPPDATA%\MeshLens\data` non vengono cancellati, salvo una tua scelta esplicita.

## Primo avvio e PIN

Al primo avvio il browser si apre su `http://127.0.0.1:8686` e ti chiede di scegliere un **PIN**. Ogni dispositivo lo inserisce una volta e poi resta riconosciuto. Se lo dimentichi, chiudi MeshLens (icona di notifica → Esci) e dal Prompt dei comandi esegui `"%LOCALAPPDATA%\Programs\MeshLens\MeshLens.exe" reset-pin`: non stampa nulla e al prossimo accesso ti chiede un nuovo PIN. Da sorgente (sviluppo) resta `meshlens reset-pin`.

## Uso dal telefono

1. In **Impostazioni** attiva l'accesso dalla rete locale (di default MeshLens ascolta solo sul PC).
2. Dal telefono, collegato alla stessa Wi-Fi, apri `http://<indirizzo-del-PC>:8686` e inserisci il PIN.

L'accesso avviene di default in HTTP semplice: usalo solo su una rete di cui ti fidi. Senza HTTPS non è disponibile il GPS del telefono; le notifiche del browser per i messaggi diretti funzionano se consenti alla pagina di inviarle, ma sui telefoni di solito richiedono HTTPS. Per l'accesso dalla rete locale puoi attivare HTTPS facoltativo in **Impostazioni → Rete** (porta 8687, con certificato autofirmato generato da MeshLens: il browser chiederà di accettarlo).

## Mappe offline

In **Impostazioni → Mappe offline** scegli cosa scaricare (mondo a basso dettaglio, Italia, aree a scelta). Lo scaricamento è un passo guidato e non è obbligatorio per usare l'app. Senza connessione MeshLens passa da solo alle mappe locali.

## Aggiornamenti

MeshLens controlla da solo una volta al giorno se c'è una nuova versione (si può disattivare). Il file scaricato viene verificato con SHA-256: se non coincide viene cancellato e nulla viene installato. L'installazione parte solo dopo la tua conferma.

Finché il repository è **privato** serve un token:

1. Su GitHub: *Settings → Developer settings → Personal access tokens → Fine-grained tokens*.
2. Repository: `iw8ffg/meshlens`, permesso **Contents: Read-only**.
3. Il token deve essere creato dal **proprietario** del repository; se sei un collaboratore usa un token classico con permesso `repo`.
4. In MeshLens: **Impostazioni → Aggiornamenti**, incolla il token. Resta solo sul tuo PC e non compare mai nei log.

Quando il repository sarà pubblico il token non servirà più.

## Da sorgente (sviluppo)

Servono Python 3.12–3.14, Node 24 e git.

```bat
git clone https://github.com/iw8ffg/meshlens.git
cd meshlens
start.bat
```

`start.bat` crea l'ambiente Python, compila l'interfaccia e avvia il server (dati in `./data`). Per lo sviluppo:

```bat
.venv\Scripts\python -m pytest
cd web && npm test && npm run dev
.venv\Scripts\python tools\demo_seed.py demo-data
.venv\Scripts\meshlens run --data-dir demo-data
```

Il primo comando esegue i test del server, il secondo quelli dell'interfaccia e la avvia con ricarica a caldo. Gli ultimi due avviano MeshLens su un database dimostrativo con dati inventati.

## Privacy

- **Nessun dato viene inviato a nessuno.** Tutto resta nel database sul tuo PC.
- Su MQTT MeshLens **ascolta** e pubblica **solo i messaggi di testo che invii tu** scegliendo "Invia via MQTT" (a nome del tuo nodo, con conferma la prima volta e un limite di frequenza). Nient'altro viene mai pubblicato: né posizioni né dati dei nodi.
- Per default il server ascolta solo su `127.0.0.1`; l'accesso dalla rete locale è una tua scelta ed è protetto dal PIN.
- Lo storico ha una scadenza configurabile (default: messaggi e posizioni 90 giorni, telemetria 1 anno).
- Le uniche connessioni in uscita sono quelle che avvii tu: il broker MQTT, le mappe online, lo scaricamento delle mappe offline e il controllo degli aggiornamenti su GitHub; su richiesta, lo scaricamento dei dati di altitudine (Terrarium, dati aperti su AWS) per la copertura prevista; e, solo se li attivi, le notifiche Telegram.

## Licenza

MeshLens è software libero, rilasciato con licenza **GNU GPL-3.0**. Copyright © 2026 iw8ffg. Vedi [LICENSE](LICENSE) (testo ufficiale in inglese) e [LICENZA.md](LICENZA.md) (riassunto in italiano). Le dipendenze incluse sono elencate in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).

## Note legali

MeshLens è un progetto indipendente e **non è affiliato al progetto Meshtastic**. Meshtastic® è un marchio registrato di Meshtastic LLC. MeshLens non aggira i limiti di legge sull'uso delle frequenze (duty cycle, potenza, preset): rispettarli resta responsabilità dell'utente.

## Ringraziamenti

- [Meshtastic](https://meshtastic.org) e la sua libreria Python.
- [Protomaps](https://protomaps.com) (mappe PMTiles, stile, glifi e sprite) e go-pmtiles.
- I contributori di [OpenStreetMap](https://www.openstreetmap.org/copyright) (© OpenStreetMap contributors, ODbL).
- [OpenFreeMap](https://openfreemap.org) per la mappa online.
- [Natural Earth](https://www.naturalearthdata.com) per i confini delle nazioni.
