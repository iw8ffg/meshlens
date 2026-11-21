# Changelog

Il formato segue [Keep a Changelog](https://keepachangelog.com/it-IT/1.1.0/) e il progetto usa il [versionamento semantico](https://semver.org/lang/it/).
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses [Semantic Versioning](https://semver.org/).

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

[1.0.0]: https://github.com/iw8ffg/meshlens/releases/tag/v1.0.0
