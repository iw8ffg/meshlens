# Canali custom e più broker MQTT: cosa serve (per la prossima release)

Richiesta dell'utente, 2026-11-21:
1. aggiungere canali custom dal pannello Impostazioni;
2. aggiungere altri broker MQTT oltre a quello predefinito.

## Come funziona oggi

**Canali e chiavi**
- `mqtt.extra_keys` è una lista piatta di PSK base64, senza nome di canale.
- `EnvelopeDecoder` prova ogni chiave, filtrata con `channel_hash(nome, chiave)`.
- La coppia canale→chiave si impara solo dopo la prima decifratura riuscita (`channel_keys` / `Runtime.learned_keys`).
- `mqtt_channels` (filtro "Canali da ascoltare") mostra i preset e i canali visti. Un canale privato compare solo dopo che è arrivato traffico.
- L'invio via MQTT (`MqttSender.key_for`) funziona solo se la chiave è già stata imparata, oppure se il canale è un preset con AQ==. Su un canale privato appena aggiunto l'invio dà `unknown_channel_key`.
- `expand_psk` accetta PSK da 0, 1, 16 e 32 byte (AES-128 e AES-256): da questo lato non serve altro.

**Broker**
- C'è un solo oggetto `mqtt` (host, porta, utente, password, topic, extra_keys).
- C'è un solo `Runtime.connector`. `on_settings_changed` lo riavvia se l'oggetto `mqtt` cambia.
- `MqttSender` riceve un solo connettore. `/api/mqtt/status` restituisce un solo stato, e la TopBar mostra un solo msg/s.
- Non c'è TLS (manca `tls_set`): un broker privato sulla porta 8883 oggi non funziona.
- La deduplica, per (from, packet_id), è già trasversale alle fonti: due broker che consegnano lo stesso pacchetto non creano doppioni.

## Cosa serve: canali custom

1. **Impostazione nuova** `mqtt_custom_channels: [{name, psk}]`.
   - `name`: 1–11 caratteri (limite dei nomi di canale Meshtastic), senza `/ # +`.
   - `psk`: base64 validata con `expand_psk`.
   - Migrazione: le voci di `extra_keys` restano chiavi "senza nome", oppure si mostrano come canali da completare.
2. **Decoder.** Aggiungere le chiavi custom a `keys` e precaricare `channel_keys[name] = key`. Così il canale si decifra e si può usare per l'invio subito, senza aspettare traffico.
3. **Filtro canali e "Invia via".** I canali custom compaiono sempre nella lista, anche con 0 messaggi.
4. **UI Impostazioni.** Elenco con nome e PSK, pulsanti "Aggiungi" ed "Elimina". La PSK si mostra mascherata, con un pulsante per vederla.
   - Comodità facoltative:
     - importa i canali da una radio collegata, che conosce già nome e PSK;
     - incolla un link `https://meshtastic.org/e/#...` (protobuf ChannelSet in base64url).
5. **Riservatezza.** La PSK è un segreto: va salvata come `update_token` e non va scritta nei log.
6. **Test.** Validazione, decifratura con la chiave custom, invio su un canale custom senza traffico precedente.

## Cosa serve: più broker

1. **Impostazione nuova** `mqtt_brokers: [{id, name, enabled, host, port, tls, username, password, topics}]`.
   - Il broker attuale diventa il primo, "mqtt.meshtastic.org (predefinito)". Si può disattivare ma non eliminare.
   - Migrazione automatica dal vecchio oggetto `mqtt`.
   - `extra_keys` e i canali custom restano globali, condivisi da tutti i broker.
2. **Runtime.** Un connettore per ogni broker attivo, `connectors: dict[id, MqttConnector]`. Al cambio delle impostazioni si riavviano solo i broker modificati. Le chiavi imparate restano condivise.
3. **TLS.** Opzione "TLS" (`client.tls_set()` con i certificati di sistema), porta 8883 suggerita.
4. **Stato.**
   - `/api/mqtt/status` restituisce il totale più l'elenco per broker (connesso, msg/s, errori).
   - TopBar: totale msg/s; il dettaglio per broker va in un popover o in Impostazioni.
5. **Origine dei messaggi.** Aggiungere a `MeshEvent` un campo `broker` (facoltativo), per mostrare nel feed da quale broker arriva un messaggio.
6. **Invio.** Bisogna scegliere su quale broker pubblicare. Proposta: il broker "per l'invio" scelto in Impostazioni (predefinito: il primo). La radice del topic si prende dai topic di quel broker. Restano invariati il limite di frequenza e la conferma della prima volta, per ogni broker pubblico.
7. **Test.**
   - Migrazione.
   - Due connettori finti con lo stesso pacchetto: deve risultare un solo evento.
   - Il riavvio deve toccare solo il broker cambiato.
   - L'invio deve usare il broker scelto.

## Decisioni dell'utente (2026-11-21)

- **Invio:** menu a tendina del broker nel composer, accanto a "Invia via" (non un broker fisso in Impostazioni). La radice del topic viene dai topic del broker scelto. Limite di frequenza e conferma della prima volta valgono per ogni broker.
- **Ascolto:** tutti i broker attivi insieme.
- **Canali custom:** nome + PSK, più "importa dalla radio collegata" e "incolla link meshtastic.org/e/#...".
- **Canali legati a un broker:** ogni canale custom appartiene a un broker. Va nella voce del broker: `mqtt_brokers[i].channels: [{name, psk}]`. Ogni connettore ha il suo decoder con le sue chiavi. Il menu dei canali nel composer mostra quelli del broker selezionato.
- **TLS:** non è stato chiesto esplicitamente. Mia scelta: opzione TLS per broker, spenta di default.
- **Crittografia e TLS per broker (decisione utente):** due interruttori per ogni broker, "Crittografia" e "TLS", entrambi SPENTI di default.
  - Crittografia: è come `encryption_enabled` nel modulo MQTT di Meshtastic. Spenta = il testo inviato viene pubblicato in chiaro (MeshPacket `decoded`); accesa = cifrato con la PSK del canale (come oggi). In ricezione si decodificano comunque sia i pacchetti cifrati sia quelli in chiaro.
  - Attenzione: oggi l'invio sul broker predefinito è cifrato. Se la migrazione lo porta a "spento", i gateway che scartano i pacchetti in chiaro potrebbero non ritrasmetterlo. DECISO: il broker predefinito (migrato) ha la crittografia ACCESA; i broker nuovi partono con crittografia e TLS spenti.
