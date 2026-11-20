# Libreria `meshtastic` 2.7.11 + bleak 3.1.0 — note per la fase 2 (verificate sul sorgente il 2026-11-20)

Percorsi relativi a `.venv/Lib/site-packages/meshtastic/` (mi = mesh_interface.py, si = stream_interface.py).

## Costruttori (tutti BLOCCANTI → `asyncio.to_thread`)
- `SerialInterface(devPath=None, debugOut=None, noProto=False, connectNow=True, noNodes=False, timeout=300)`: apre seriale 115200 `exclusive=True`, thread "stream reader", scarica config (attesa max 30 s, mi:1131). In caso d'errore chiude e rilancia.
- **Windows 11**: `is_windows11()` (build ≥ 22000) → `_writeBytes` dorme 1 s dopo ogni scrittura (si:116). Ogni invio costa ≥ 1 s.
- Senza `devPath`: `findPorts` (VID whitelist 0x239a, 0x303a); 0 porte → oggetto mezzo inizializzato; >1 porta → `SystemExit`. **Passare sempre `devPath`**, enumerare con `serial.tools.list_ports`.
- `BLEInterface(address, noProto=False, debugOut=None, noNodes=False, timeout=300)`: scansione 10 s a ogni costruzione, un thread asyncio per client, `atexit` disconnect; match per nome o indirizzo, esattamente uno (altrimenti `BLEError`). `BLEInterface.scan()` → `List[BLEDevice]` (UUID servizio 6ba1b218-15a8-461f-9fa8-5dcae273eafd).
- `close()` bloccante (join del reader).

## Eventi (pubsub globale)
- Un solo thread globale "publishing" per tutte le interfacce: un listener lento blocca tutte le radio. `interface=` passato in ogni messaggio → distinguere le radio con `interface is iface`.
- Topic: `meshtastic.connection.established|lost(interface)`, `meshtastic.node.updated(node, interface)`, `meshtastic.receive(packet, interface)` (+ `.text/.position/.user/.telemetry/.routing/.traceroute/.admin/.rangetest/...`), `meshtastic.log.line`.
- pubsub tiene riferimenti deboli: conservare riferimenti forti ai listener. Ponte verso asyncio: `loop.call_soon_threadsafe(queue.put_nowait, (iface, packet))`.

## Pacchetto ricevuto (dict camelCase, solo campi non default)
`from` (int), `to`, `id`, `channel` (assente se 0), `rxTime`, `rxSnr`, `rxRssi`, `hopLimit`, `hopStart`, `viaMqtt`, `fromId` ("!hex"), `toId` ("^all" broadcast), `raw` (protobuf). `decoded`: `portnum` (nome stringa), `payload` (bytes), `requestId`, sotto-dict `text` (str) / `position` (con `latitude`,`longitude`) / `user` / `telemetry` / `routing.errorReason` / `traceroute`. Rimuovere `raw`/`payload` prima di serializzare.

## Nodi
`iface.nodes` (chiave "!hex") e `nodesByNum` (int) condividono gli stessi dict: `num`, `user{id,longName,shortName,hwModel,role,publicKey}`, `position{latitude,longitude,altitude,time}`, `snr`, `lastHeard`, `deviceMetrics{batteryLevel,voltage,channelUtilization,airUtilTx,uptimeSeconds}`, `hopsAway`, `viaMqtt`. `myInfo` è protobuf (`my_node_num`). `localNode`: `localConfig`, `moduleConfig`, `channels`.

## Invio
- `sendText(text, destinationId="^all", wantAck=False, wantResponse=False, onResponse=None, channelIndex=0, ..., replyId=None, hopLimit=None)` → MeshPacket (usare `.id`). Bloccante (attende connessione fino a 30 s; +1 s Win11).
- ACK: pacchetto ROUTING_APP con `decoded.requestId` == id inviato e `routing.errorReason == "NONE"`; ack dal proprio nodo = solo implicito. Più semplice: ascoltare `meshtastic.receive.routing`.
- `sendTraceRoute` stampa soltanto: usare `sendData(RouteDiscovery(), portNum=TRACEROUTE_APP, wantResponse=True, onResponse=cb)` o `meshtastic.receive.traceroute`.
- `sendPosition(...)`, `sendTelemetry(destinationId, wantResponse, channelIndex, telemetryType)`.

## Configurazione / admin
- `node.writeConfig("lora"|...)`, `beginSettingsTransaction/commitSettingsTransaction`, `requestConfig`, `reboot(secs=10)`, `setOwner`, `setFixedPosition`.
- Remoto: `iface.getNode("!hex", requestChannels=False)` (bloccante). Admin sempre PKI (`_sendAdmin`, session passkey). `security.admin_key` va modificato a mano + `writeConfig("security")`; il nodo remoto deve avere la chiave pubblica della nostra radio. Da verificare su hardware.
- Molte funzioni usano `print()` e `our_exit` (SystemExit): proteggere con try/except BaseException in executor.

## BLE su Windows
- Backend WinRT; indirizzi MAC. La libreria non chiama `pair()`: probabilmente serve abbinare prima da Impostazioni Windows (da verificare). Scansioni ripetute penalizzano connessioni multiple: alternativa = client bleak proprio sulle caratteristiche TORADIO/FROMRADIO/FROMNUM (ble_interface.py:21-26).

## Perdita di connessione
- USB staccata: thread reader muore, `connection.lost`, nessuna riconnessione; il timer heartbeat (non daemon) resta finché non si chiama `close()`. **Ricreare l'interfaccia.**
- BLE: callback di disconnessione chiama `close()` da thread WinRT → possibile deadlock/doppia chiusura (non verificato). Ricreare.
- Riavvio firmware: `connection.lost` poi `connection.established` senza chiudere.

## Insidie multi-radio
Thread di pubblicazione unico, `random.seed()` globale, `sys.exit` nel codice di libreria, molti `print()`, logger `meshtastic.*` senza contesto. Costruttori e `close()` bloccanti; non costruire più BLE insieme senza test.
