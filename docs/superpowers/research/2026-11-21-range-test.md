# Range Test Meshtastic (fw 2.7.x, lib python 2.7.11) - ricerca 2026-11-21

## 1. Modulo Range Test
- Il sender trasmette su `RANGE_TEST_APP` (portnum 66, verificato in portnums_pb2) un testo UTF-8 `"seq N"` (`snprintf("seq %u", packetSequence)`, contatore da 0, +1 a ogni invio).
- La posizione NON e' nel payload: serve un pacchetto POSITION_APP separato (il sender la logga solo localmente; il receiver puo' usare il proprio GPS per il CSV).
- Pacchetto: `hop_limit = 0` (nessun relay), `want_ack = false`. Primo invio 5 s dopo l'avvio.
- Intervallo: `range_test.sender` in secondi, 0 = modalita' ricevitore. Il codice NON impone un minimo; la doc suggerisce 30-60 s (30 per LongFast, 15 per Medium/Short Fast). Invio saltato se utilizzo canale > 25% (`isTxAllowedChannelUtil`).
- Auto-disable: il sender si ferma dopo 8 ore (28800000 ms) dall'avvio.
- `enabled` deve essere true su ENTRAMBI i nodi (le app mobili mostrano i messaggi solo cosi'). `save`/CSV solo ESP32.
- Canale pubblico di default: nel sorgente di RangeTestModule.cpp non ho trovato blocchi o intervalli forzati per il canale default; la doc raccomanda solo di disattivarlo quando non serve (consuma airtime, "spam" sul canale).
- Nota: nella sorgente la scelta del canale e' in `sendToMesh` (non letto); non verificato se ci sono limiti li'.

## 2. Precisione posizione e intervalli
- Canale 0 di default: `position_precision = 13` (Channels.cpp `initDefaultChannel`), ~2,9 km secondo tabella doc (la doc pagina canali; 14 bit ~1,5 km).
- Canali con chiave pubblica (nessuna, default "AQ==", 1 byte): il firmware limita a 15 bit (~729 m) (doc canali).
- Canale privato (PSK vera): `position_precision` 32 = piena precisione, impostabile per canale (`--ch-set module_settings.position_precision 32 --ch-index N`). Invio posizione su canale secondario privato funziona solo da 2.7.1 (Configuration Tips).
- Per il test copertura serve precisione alta: usare canale privato (o come primario, o secondario con 2.7.1+).
- Smart position (default attivo): distanza minima 100 m, intervallo minimo smart 30 s (la doc si contraddice: tabella CLI dice 15 min); broadcast periodico default 15 min (`position_broadcast_secs`, 0 = default, scalato col numero di nodi online). Per tracking ~30 s: impostare `position_broadcast_secs` ~30 e `broadcast_smart_minimum_interval_secs` ~30, `smart_minimum_distance` basso; il pacchetto e' soggetto a gate utilizzo canale 25%.
- Il firmware non invia se precisione = 0.

## 3. Libreria Python (installata)
- `protocols[RANGE_TEST_APP] = KnownProtocol("rangetest", onReceive=_onTextReceive)` (`__init__.py` r.270): nessuna protobuf factory.
- Topic pubsub: `meshtastic.receive.rangetest`.
- Nel dict `packet["decoded"]`: `portnum` = "RANGE_TEST_APP", `payload` = bytes (sovrascritti in mesh_interface r.1607), `text` = payload.decode("utf-8") (se UTF-8 valido, altrimenti assente + log error). Altri campi: `packet["from"]`, `fromId`, `rxSnr`, `rxRssi`, `hopLimit`, `rxTime`. `_receiveInfoUpdate` aggiorna anche `nodes[from]["lastReceived"]`, `snr`.
- Esempio: `int(pkt["decoded"]["text"].split()[1])` per il seq.

## 4. Buone pratiche
- Canale privato dedicato (PSK propria, precisione 32) per non inquinare LongFast; sender con intervallo >= 30 s (LongFast), ricevitore con sender=0.
- hop_limit 0 e' gia' imposto dal modulo (misura solo il collegamento diretto). Ruolo CLIENT (o CLIENT_MUTE per il ricevitore fisso; evitare ROUTER). Disattivare il modulo a fine test; ricordare il timeout di 8 h.
- Correlare seq ricevuti con le posizioni del sender (POSITION_APP) via timestamp; i seq mancanti danno il packet loss.

## Fonti
- https://github.com/meshtastic/firmware/blob/master/src/modules/RangeTestModule.cpp
- https://github.com/meshtastic/firmware/blob/master/src/mesh/Channels.cpp
- https://github.com/meshtastic/firmware/blob/master/src/modules/PositionModule.cpp
- https://meshtastic.org/docs/configuration/module/range-test/
- https://meshtastic.org/docs/configuration/radio/channels/
- https://meshtastic.org/docs/configuration/radio/position/
- https://meshtastic.org/docs/configuration/tips/
- Sorgente installato: .venv/Lib/site-packages/meshtastic/__init__.py, mesh_interface.py
