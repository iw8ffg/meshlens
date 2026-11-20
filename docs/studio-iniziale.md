# MeshLens — Studio iniziale (2026-11-20)

Legenda: **[V]** verificato su fonte, **[?]** da verificare.

## 1. Ambiente locale
Windows 11, Python 3.12.10, Node 24.19, git 2.55 già installati.

## 2. MQTT Meshtastic
- Broker pubblico `mqtt.meshtastic.org`, credenziali di default `meshdev` / `large4cats` [V]; porta 1883 [?].
- Restrizioni del server pubblico [V]: traffico zero-hop; con PSK di default passano solo NodeInfo, Text, Position, Telemetry, MapReport, Routing; **posizioni imprecise** (10–16 bit ≈ 1,5 km).
- Da ago 2024 rimosso l'abbonamento a `msh/#`; usare wildcard regionali es. `msh/EU_868/#` [V]. ([blog](https://meshtastic.org/blog/recent-public-mqtt-broker-changes/))
- Topic [V]: `msh/<REGION>/2/e/<canale>/<!nodeid>` (protobuf, cifrato), `msh/<REGION>/2/json/...` (solo se json_enabled, non nRF52), map report `msh/<REGION>/2/map/` [?] (non cifrati, ~ogni ora, firmware ≥2.3.2).
- Cifratura: AES-CTR; PSK `AQ==` = chiave di default `d4f1bb3a20290759f0bcffabcf4e6901`; nonce = packetId (u64 LE) + fromNode (u32 LE) + 4 zero [? da verificare su firmware].
- Protobuf: [meshtastic/protobufs](https://github.com/meshtastic/protobufs) (GPL-3.0). Python: inclusi nel pacchetto `meshtastic`; TS: `@meshtastic/protobufs` (JSR).
- Deduplicare per packet id (più gateway pubblicano lo stesso pacchetto) [V].

## 3. Filtro per nazione
- REGION nel topic = banda radio, non nazione. Sotto-topic tipo `msh/EU_868/IT/...` sono convenzioni libere, non standard.
- Metodo affidabile: **reverse geocoding offline** da lat/lon (poligoni Natural Earth admin-0 + point-in-polygon, oppure `reverse_geocoder` in Python). Cache per nodo.
- Limiti: nodi senza GPS → "sconosciuto"; posizioni a ~1,5 km → errori su confini/coste; messaggi di testo localizzati tramite la posizione del mittente.

## 4. Radio via USB
| Opzione | Pro | Contro |
|---|---|---|
| **A. Web Serial nel browser** (`@meshtastic/core` + `transport-web-serial`, GPL-3.0) | nessun backend per la radio | solo Chrome/Edge; selezione porta manuale; scheda deve restare aperta; librerie in forte cambiamento (v2.7 SDK refactor) |
| **B. Backend Python** (`meshtastic` 2.7.11, GPL-3.0, SerialInterface/TCP/BLE, eventi pubsub) | API più completa e documentata; logging continuo anche a browser chiuso; qualsiasi browser | serve runtime Python e bridge WebSocket/SSE |
| B'. Backend Node (`@meshtastic/core` + transport-node) | stesso linguaggio del frontend | transport-node recente, maturità non verificata |

- Una sola applicazione alla volta può aprire la porta COM (CLI, app, browser).
- Driver Windows [V]: CP210x (Silicon Labs), CH340/CH9102 (WCH CH343SER); nRF52/RP2040 di solito nessun driver. ([doc](https://meshtastic.org/docs/getting-started/serial-drivers/esp32/))
- Il nodo USB non ha internet proprio: per la mappa conviene una connessione MQTT dell'app separata dalla radio; marcare la sorgente (rf/mqtt) e deduplicare.

## 5. Hardware e normativa (Italia)
- Starter suggeriti: Heltec V3/V4 (economico, display), RAK4631 WisBlock (basso consumo, niente driver), T-Beam (GPS + batteria).
- Regione `EU_868`: 869,4–869,65 MHz, duty cycle 10%, max 27 dBm firmware [V]. Regione va impostata al primo avvio (default UNSET). Normativa nazionale specifica [?].
- Mai accendere senza antenna.

## 6. Progetti open source utili
| Progetto | Stack | Licenza | Utilità |
|---|---|---|---|
| [liamcottle/meshtastic-map](https://github.com/liamcottle/meshtastic-map) | Node, Express, Prisma, MySQL | MIT | collector MQTT + decrittazione + mappa + feed messaggi: il più vicino |
| [zenitraM/malla](https://github.com/zenitraM/malla) | Python, Flask, SQLite, Leaflet | MIT | separazione capture/web, più chiavi di decrittazione |
| [m9wav/MeshConsole](https://github.com/m9wav/MeshConsole) | Python Flask, pyserial, SQLite | MIT | radio USB + mappa; **stesso nome** del nostro progetto |
| [pablorevilla-meshtastic/meshview](https://github.com/pablorevilla-meshtastic/meshview) | Python, SQLAlchemy, Leaflet | [?] | topic configurabili, chiavi secondarie |
| [ruspea/MeshDash](https://github.com/ruspea/MeshDash) | FastAPI, SQLite, Leaflet, SSE | GPL-3.0 | USB + MQTT + mappa: funzionalità molto simili |
| [MeshAddicts/meshinfo](https://github.com/MeshAddicts/meshinfo) | FastAPI, Postgres, React | GPL-3.0 | reverse geocoding, chat |
| [brianshea2/meshmap.net](https://github.com/brianshea2/meshmap.net) | Go | AGPL-3.0 | riferimento, codice poco riusabile |
| [meshtastic/web](https://github.com/meshtastic/web) | React/TS | GPL-3.0 | client ufficiale, riferimento per Web Serial |
| [pdxlocations/contact](https://github.com/pdxlocations/contact) | Python TUI | GPL-3.0 | esempi d'uso della libreria Python |

## 7. Note su licenze e privacy
- Quasi tutte le librerie Meshtastic sono GPL-3.0: usarle rende MeshConsole GPL se distribuito (irrilevante per uso personale).
- Messaggi e posizioni sul broker pubblico sono leggibili da chiunque ma restano dati personali: limitare lo storico (GDPR se condiviso).

## 8. Punti aperti
- Scopo d'uso (osservazione, gestione rete, comunicazione offline).
- Nome: scelto **MeshLens** (verificato libero su PyPI e GitHub).
- Mappe offline sì/no.
