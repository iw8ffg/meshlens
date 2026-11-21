<p align="center"><img src="docs/img/banner-it.svg" alt="MeshLens" width="720"></p>

<p align="center">🇬🇧 <a href="README.en.md">English</a></p>

<p align="center">
  <img alt="Licenza GPL-3.0" src="https://img.shields.io/badge/licenza-GPL--3.0-blue">
  <img alt="Piattaforma Windows" src="https://img.shields.io/badge/piattaforma-Windows%2010%2F11-0078D6">
  <img alt="Versione 1.0.0" src="https://img.shields.io/badge/versione-1.0.0-brightgreen">
</p>

**MeshLens** è un'applicazione locale per Windows che riunisce in un'unica mappa interattiva tutto ciò che accade su una rete [Meshtastic](https://meshtastic.org): i nodi sentiti da **Internet (MQTT)** e dalle **tue radio** collegate via USB o Bluetooth. Osservi la rete, gestisci i tuoi nodi e chatti via radio, anche senza Internet. Si usa dal PC e dal telefono sulla stessa Wi-Fi.

## Schermate

| | |
|---|---|
| ![Mappa con i nodi](docs/img/screen-map.png)<br>**Mappa** con i nodi da radio e MQTT | ![Dettaglio nodo](docs/img/screen-node.png)<br>**Dettaglio nodo** con grafico della batteria |
| ![Scheda Rete](docs/img/screen-network.png)<br>**Rete**: i tuoi nodi a colpo d'occhio | ![Prova di copertura](docs/img/screen-coverage.png)<br>**Copertura** sul campo |
| ![Impostazioni](docs/img/screen-settings.png)<br>**Mappe offline** e aggiornamenti | ![Vista telefono](docs/img/screen-mobile.png)<br>**Telefono** |

> Le schermate usano un database dimostrativo con nodi inventati.

## Funzioni principali

### 🗺️ Mappa e osservazione
- Nodi da MQTT e da radio fusi in un'unica vista, con colore per fonte e per ultimo contatto.
- Filtri per nazione, fonte, radio, ultimo contatto, ruolo e testo.
- Dettaglio nodo: hardware, ruolo, firmware, posizione e precisione, batteria, SNR/RSSI/hop, traccia dei percorsi.
- Feed dei messaggi pubblici MQTT, filtrabile per nazione.

### 📻 Radio e chat
- Più radio insieme, via **USB** e **Bluetooth**, con riconnessione automatica.
- Chat su canali e messaggi diretti, con scelta della radio e stato di consegna.

### 📊 Gestione della rete
- Stato dei nodi, **batteria con grafico storico** e avvisi (soglia configurabile, nodi silenziosi).
- "I miei nodi": marca i tuoi, viste e avvisi si concentrano su di loro.
- Mappa dei collegamenti colorata per SNR e **traceroute** a richiesta.

### 📡 Copertura sul campo
- Prove di copertura con il modulo Range Test: punti colorati per qualità del segnale, percorso, punti mancanti e storico delle sessioni.
- "Prepara le radio" e "Ripristina" per impostare e rimettere a posto la configurazione.

### ⚙️ Configurazione
- Lettura e modifica della configurazione delle radio collegate e dei nodi remoti (chiavi admin PKI).
- Ogni modifica passa da un **riepilogo delle differenze**, una **conferma esplicita** e una **copia di sicurezza ripristinabile**.

### 🌍 Offline
- Mappe PMTiles scaricabili con un passo guidato: mondo a basso dettaglio, Italia e aree a scelta.
- Passaggio automatico tra mappa online e offline.

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

L'accesso avviene in HTTP semplice: usalo solo su una rete di cui ti fidi. Niente HTTPS significa anche niente GPS del telefono né notifiche push del browser.

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
- MQTT è **solo in ascolto**: MeshLens non pubblica mai nulla sui broker pubblici.
- Per default il server ascolta solo su `127.0.0.1`; l'accesso dalla rete locale è una tua scelta ed è protetto dal PIN.
- Lo storico ha una scadenza configurabile (default: messaggi e posizioni 90 giorni, telemetria 1 anno).
- Le uniche connessioni in uscita sono quelle che avvii tu: il broker MQTT, le mappe online, lo scaricamento delle mappe offline e il controllo degli aggiornamenti su GitHub.

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
