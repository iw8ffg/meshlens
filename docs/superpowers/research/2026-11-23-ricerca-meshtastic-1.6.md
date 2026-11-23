# Ricerca Meshtastic per MeshLens 1.6

Fonte primaria: libreria `meshtastic` 2.7.11 in `.venv/Lib/site-packages/meshtastic/` (node.py, mesh_interface.py, __init__.py, protobuf/*.pyi).
Legenda: [S] verificato nel sorgente; [D] da documentazione (meshtastic.org); [I] incerto / conoscenza del firmware non verificata qui.
Nota: il sorgente del firmware NON e disponibile localmente: tutto cio che riguarda il comportamento del firmware e [D] o [I].

## 1. E3 Preferiti / ignorati sulla radio
- [S] AdminMessage (admin_pb2): `set_favorite_node`=39, `remove_favorite_node`=40, `set_ignored_node`=47, `remove_ignored_node`=48, `toggle_muted_node`=49 (uint32 node num). Richiedono session_passkey.
- [S] Helper lib (node.py): `Node.setFavorite(nodeId)` r.834, `removeFavorite` r.848, `setIgnored` r.862, `removeIgnored` r.876. Nessun helper per `toggle_muted_node` (costruire l'AdminMessage a mano, `ensureSessionKey()` e `node._sendAdmin(p)`).
- [S] Lettura: `NodeInfo` (mesh_pb2) ha `is_favorite`=10, `is_ignored`=11, `is_key_manually_verified`=12, `is_muted`=13. Nel dict `iface.nodes[...]` compaiono in camelCase (`isFavorite`, ecc.; mesh_interface.py usa "isFavorite").
- [S] Sono flag del NodeDB DELLA RADIO CONNESSA: per i nodi remoti si legge solo cio che la radio locale ha marcato; non si leggono i preferiti di un altro nodo. Il pb dice "persiste fra le pulizie del NodeDB".
- [S] `nodedb_reset` (100): il commento pb dice che con true i preferiti sono preservati.
- [I] Versione firmware: favorite/ignored da 2.3.x; `is_muted`/`toggle_muted_node` e recente (probabilmente 2.7.x): fare feature-detect (campo assente => nascondere).
- FATTIBILE: si.

## 2. E7 Profili di configurazione
- [S] Scrivibili via admin: `set_config` (device, position, power, network, display, lora, bluetooth, security; `device_ui` esiste nel pb ma non in writeConfig), `set_module_config` (mqtt, serial, external_notification, store_forward, range_test, telemetry, canned_message, audio, remote_hardware, neighbor_info, ambient_lighting, detection_sensor, paxcounter, traffic_management). Il pb ha anche `statusmessage` e `tak`, MA `Node.writeConfig` della lib 2.7.11 NON li gestisce: serve costruire l'AdminMessage a mano. Inoltre `set_owner` (User), `set_channel` (8 slot), `set_canned_message_module_messages`, `set_ringtone_message`, `set_fixed_position`, `store_ui_config`.
- [S] Transazione: `begin_edit_settings`=64 / `commit_edit_settings`=65; lib: `Node.beginSettingsTransaction()` e `commitSettingsTransaction()` (node.py r.705/719). Il pb: ritarda il salvataggio su filesystem e il reboot fino al commit (config, module config, owner, canali). Consigliato per applicare un profilo con un solo reboot.
- [S] DA NON COPIARE tra radio (SecurityConfig): `private_key`, `public_key` (identita del nodo; copiarle clona l'identita e rompe PKI/DM), `admin_key` (chiavi autorizzate), e con cautela `is_managed`, `admin_channel_enabled`, `serial_enabled`, `debug_log_api_enabled`. Escludere TUTTO `security` oppure copiare solo i flag non-chiave.
- [S per i nomi campo, I per la raccomandazione] Anche da escludere/trattare con cautela: `owner` (nomi, id, macaddr, public_key), `network.wifi_ssid/wifi_psk`, `mqtt.address/username/password`, `channels[].settings.psk` (segreti), `lora.region` (regolatorio: copiare solo per stesso paese), `lora.tx_power`, `lora.override_duty_cycle`, `lora.override_frequency`, `lora.fem_lna_mode`/`pa_fan_disabled`/`sx126x_rx_boosted_gain` (dipendono dall'hardware: Heltec V3/V4 e T-Deck/T-Pager hanno front-end diversi), pin GPIO (`device.button_gpio`/`buzzer_gpio`, `position.rx_gpio/tx_gpio`, `canned_message.inputbroker_pin_*`, `detection_sensor.monitor_pin`, `external_notification.output*`), posizione fissa.
- FATTIBILE: si come "profilo parziale" con whitelist di sezioni e blacklist esplicita di security/owner/psk/wifi/mqtt-secret; applicare dentro begin/commit.

## 3. E9 Detection Sensor e Paxcounter (+ External Notification)
- [S] portnum `DETECTION_SENSOR_APP`=10 ("come Text Message ma originato dal Detection Sensor"). La lib lo tratta come testo (`__init__.py` r.273: KnownProtocol("detectionsensor", onReceive=_onTextReceive)): payload testo UTF-8, il decoded espone `text`. [D] Il testo e il Friendly Name (max 20 car.) + " detected"; con `send_bell` aggiunge il carattere BEL (0x07).
- [S] `PAXCOUNTER_APP`=34, protobuf `Paxcount`: `wifi`(1,uint32), `ble`(2,uint32), `uptime`(3,uint32 s). La lib lo decodifica in `decoded["paxcounter"]` (r.301). `PaxcounterConfig`: enabled, paxcounter_update_interval, wifi_threshold, ble_threshold. [I] Richiede ESP32 (Heltec V3/V4, T-Deck sono ESP32-S3).
- [S] `DetectionSensorConfig`: enabled, minimum_broadcast_secs, state_broadcast_secs, send_bell, name, monitor_pin, detection_trigger_type (LOGIC_LOW/HIGH, FALLING/RISING_EDGE, EITHER_EDGE_ACTIVE_LOW/HIGH), use_pullup.
- MQTT: [S] il pb portnums dice che DETECTION_SENSOR_APP "non e inviato al public MQTT da firmware 2.2.9". [I] Su broker privato: con `encryption_enabled` il ServiceEnvelope contiene `packet.encrypted` decifrabile solo con la chiave del canale; senza cifratura il pacchetto e in chiaro (`decoded`). [S] `mqtt.json_enabled` e nel pb "Deprecated: JSON packet support on MQTT was removed, and this field is ignored": NON contare sul formato JSON su 2.7.
- [S] `ExternalNotificationConfig`: enabled, output_ms, output, output_vibra, output_buzzer, active, alert_message(+_vibra/_buzzer), alert_bell(+_vibra/_buzzer), use_pwm, nag_timeout, use_i2s_as_buzzer. Ringtone RTTTL: `get_ringtone_request`(14)/`set_ringtone_message`(37); lib `Node.get_ringtone/set_ringtone` (r.542/568).
- FATTIBILE: si (ricezione testo + Paxcount, e configurazione).

## 4. E10 Messaggi predefiniti (canned)
- [S] Admin: `get_canned_message_module_messages_request`=10 -> `..._response`=11 (string); `set_canned_message_module_messages`=36 (string). `CannedMessageConfig`: enabled, rotary1/updown1, inputbroker_*, allow_input_source, send_bell.
- [S] Lib: `Node.get_canned_message()` r.620 (controlla `module_available(CANNEDMSG_CONFIG)`; attende con busy-wait SENZA timeout) e `Node.set_canned_message(message)` r.649.
- [S] Limiti nella lib: `len(message) > 200` => `our_exit(...)` (sys.exit: in webapp prevalidare PRIMA); il codice spezza in chunk da 200 ma invia solo il primo (`return` dentro il for): di fatto max 200 caratteri. [D] Documentazione: totale fino a 200 BYTE, separatore `|`, nessun massimo esplicito di messaggi. Validare in UTF-8 (accenti/emoji > 1 byte).
- [I] La risposta e una stringa unica separata da `|`; nessun helper di split nella lib. UI: lista -> join con `|` (vietare `|` nei testi) -> len(utf8)<=200.
- FATTIBILE: si.

## 5. E13 URL/QR canali e comandi admin remoti
- [S] `Node.getURL(includeAll=True)` (r.374): `apponly_pb2.ChannelSet` (`settings`=1 repeated ChannelSettings, `lora_config`=2 LoRaConfig), serializzato, base64 urlsafe senza padding, prefisso `https://meshtastic.org/e/#`. Include PRIMARY e (se includeAll) SECONDARY. Contiene PSK in chiaro e la config LoRa. QR: generare PNG/SVG dall'URL lato server. `setURL(url, addOnly=False)` (r.433) accetta `/#` o `/?add=true#`; `our_exit` se invalido. Esiste `getContactURL(node_id)` -> `https://meshtastic.org/v/#...` (SharedContact) e AdminMessage `add_contact`=66.
- [S] Comandi (node.py): `reboot(secs)` -> `reboot_seconds`=97; `shutdown(secs)` -> `shutdown_seconds`=98; `setTime(timeSec=0)` -> `set_time_only`=43; `factoryReset(full=False)` -> `factory_reset_config`=99 / `factory_reset_device`=94; `resetNodeDb()` -> `nodedb_reset`=100; `removeNode` -> `remove_by_nodenum`=38; `rebootOTA`, `enterDFUMode`. Tutti chiamano `ensureSessionKey()`; per nodi remoti attendono ACK/NAK (`onAckNak`).
- [S] Admin remoto nella lib: `_sendAdmin` invia ADMIN_APP con `pkiEncrypted=True`, `wantAck=True`, sul canale `localNode._getAdminChannelIndex()` (canale chiamato "admin", altrimenti 0); inserisce `session_passkey` da `iface._getOrCreateByNum(nodeid)["adminSessionPassKey"]`; `ensureSessionKey()` la richiede con `get_config_request=SESSIONKEY_CONFIG`.
- [S] pb `session_passkey`: generata dal nodo, inviata con le risposte get_x; il client DEVE includerla in ogni set_x; scade dopo 300 s. Quindi tutti i comandi di scrittura/reboot/shutdown/reset la richiedono (anche in locale; la lib la gestisce).
- [D] Admin remoto 2.5+: il nodo remoto deve avere la NOSTRA PUBLIC KEY in `security.admin_key` (max 3); il canale "admin" legacy vale solo per nodi <=2.4 (in 2.5+ solo con `admin_channel_enabled`). Errori Routing [S]: `ADMIN_PUBLIC_KEY_UNAUTHORIZED`(37), `NOT_AUTHORIZED`(33), `ADMIN_BAD_SESSION_KEY`(36), `PKI_UNKNOWN_PUBKEY`(35).
- FATTIBILE: URL/QR si; comandi locali si; remoti solo verso nodi che hanno la nostra chiave in admin_key. Factory reset: doppia conferma.

## 6. E16 ATAK
- [S] `ATAK_PLUGIN`=72 (TAKPacket v1); esistono anche `ATAK_PLUGIN_V2`=78 ("TAKPacketV2 con compressione zstd a dizionario") e `ATAK_FORWARDER`=257. La lib 2.7.11 NON registra ATAK_PLUGIN in `protocols`: i byte restano in `decoded.payload`; decodificare a mano con `atak_pb2.TAKPacket.FromString(payload)`.
- [S] TAKPacket: `is_compressed`(1), `contact`(2: callsign, device_callsign), `group`(3: role, team), `status`(4: battery), `pli`(5: latitude_i, longitude_i [x1e-7], altitude (HAE), speed, course), `chat`(6 GeoChat), `detail`(7 bytes, CoT XML, "puo essere compresso/troncato dal mittente"). `TAKConfig`: team, role.
- [S] `is_compressed`: "le stringhe dei payload sono compresse per LoRa". [I] Probabile unishox2: callsign/chat potrebbero non essere leggibili senza decompressore; i campi numerici del PLI si leggono comunque. V2 richiede zstd + dizionario del plugin [I].
- [I] Via MQTT: ServiceEnvelope normale; decodificabile se si decifra con la chiave del canale (o se pubblicato in chiaro).
- FATTIBILE: parziale. PLI sulla mappa, battery, team/role si; callsign/chat dipende dalla compressione; V2 da non promettere.

## 7. E14 Traceroute e E8 NeighborInfo
- [D] Traceroute: il nodo mittente permette 1 traceroute ogni 30 s; se superato il pacchetto NON viene trasmesso, nessun errore in mesh, solo notifica locale al client; il rispondente non ha limite. [I] La pagina non indica la versione di introduzione; non verificato nel firmware. [S] Esiste `Routing.Error.RATE_LIMIT_EXCEEDED`=38. MeshLens: limite client-side >= 30 s (consigliato 60 s+). Lib: `iface.sendTraceRoute(dest, hopLimit, channelIndex)` (mesh_interface.py r.669).
- [S] `NeighborInfoConfig`: enabled, `update_interval` ("minimo 14400, cioe 4 ore"), `transmit_over_lora`. [D] Minimo 4 h, default 6 h. Di default NeighborInfo va solo a MQTT e all'app; `transmit_over_lora` (>=2.5.13) lo invia anche in LoRa sul canale primario, NON disponibile se il primario ha nome e chiave di default. Portnum NEIGHBORINFO_APP=71, protobuf `NeighborInfo` (node_id, last_sent_by_id, node_broadcast_interval_secs, neighbors[node_id, snr, last_rx_time, node_broadcast_interval_secs]); la lib lo decodifica come `decoded["neighborinfo"]`.
- FATTIBILE: si, ma i pacchetti sono rari (4-6 h).

## 8. E15 Bot, limiti firmware, duty cycle EU_868
- [S] Codici Routing per il bot: `DUTY_CYCLE_LIMIT`=9 ("non si puo inviare ora per rispetto del duty cycle"), `RATE_LIMIT_EXCEEDED`=38, `TOO_LARGE`=7, `MAX_RETRANSMIT`=5, `NO_CHANNEL`=6. Gestire il NAK con backoff, mai retry in loop.
- [S] `LoRaConfig.override_duty_cycle`: "se true i limiti di duty cycle vengono superati... possibile violazione delle norme locali; nessun effetto se il duty cycle della regione e 100%"; `hop_limit` max 7.
- [I] EU_868: la tabella regioni del firmware ha duty cycle 10% (sotto-banda 869.4-869.65) e il firmware rifiuta/ritarda la TX oltre il tetto di airtime e di channel utilization. Non verificato nel sorgente firmware. Il bot NON deve attivare `override_duty_cycle`.
- [I] Nessun rate limit documentato sul `sendText` da client API oltre a duty cycle/channel utilization/coda TX; testo max ~230 byte (`TOO_LARGE`). Consiglio: coda con intervallo minimo >= 10-15 s, max N risposte/ora, anti-loop (non rispondere a se stesso o ad altri bot), whitelist mittenti, risposte brevi.
- [S/D] Admin: passkey valida 300 s; non fare raffiche di comandi admin.
- FATTIBILE: si, con coda/rate limit client-side, rispetto di DUTY_CYCLE_LIMIT, anti-loop.

## Note di implementazione (lib 2.7.11)
- `our_exit()` (sys.exit) e chiamato in `set_canned_message`, `setURL`, `setOwner`, `getContactURL`: prevalidare gli input o catturare SystemExit.
- `get_canned_message`/`get_ringtone` hanno busy-wait senza timeout: eseguirli in thread con timeout.
- `Node.writeConfig` non copre `statusmessage` e `tak`.
