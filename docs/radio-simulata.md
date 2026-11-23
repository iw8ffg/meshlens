# MeshLens — Radio simulata e replay

Due strumenti in `tools/` per provare MeshLens **senza hardware**:

- `replay_record.py` salva una *sessione* (pacchetti reali con i loro tempi) dal database di MeshLens o in diretta da una radio vera;
- `fake_radio.py` è una radio finta: un server TCP locale che parla il protocollo a flusso di Meshtastic, risponde all'handshake con un nodo e dei canali sintetici e riproduce una sessione.

Servono solo Python e il pacchetto `meshtastic` già presente nell'ambiente di MeshLens. Gli script non importano `meshlens`.

## 1. A cosa serve (e cosa non è)

Serve per prove senza radio, per le regressioni (la stessa sessione riprodotta due volte dà gli stessi risultati) e per le demo.

**Non è** una simulazione della RF né un firmware: non c'è propagazione, non c'è mesh. Le conferme di consegna sono finte (spente se non le chiedi con `--ack`). Un solo nodo proprio.

## 2. Registrare una sessione

### Dal database di MeshLens

```
python tools/replay_record.py --db "%APPDATA%\meshlens\meshlens.db" --out sessione.jsonl
```

Opzioni: `--since EPOCH`, `--until EPOCH`, `--limit N`, `--no-mqtt`, `--only-decoded`, `--max-nodes N`. Il database si apre in **sola lettura**.

Avvertenze oneste:

- il registro pacchetti conserva solo il payload (`Data.payload`), troncato a **256 byte**, più le colonne (mittente, id, SNR, salti...). Il pacchetto viene **ricostruito**, non copiato bit a bit;
- i pacchetti con payload vuoto o lungo 256 byte (forse troncato) vengono saltati e contati nel riepilogo;
- il registro scrive solo in modalità «archiviati» o «tutti»: per una sessione ricca attiva la modalità **«tutti»** in Impostazioni e lascia raccogliere traffico;
- i pacchetti MQTT hanno per canale il nome, non l'indice: nella sessione diventano canale 0.

### Da una radio vera

```
python tools/replay_record.py --radio 192.168.1.20 --seconds 120 --out sessione.jsonl
```

La radio ha **una sola connessione TCP alla volta**: chiudi prima MeshLens e le altre app. La registrazione live salva i `FromRadio` veri (configurazione e pacchetti). Ctrl+C la interrompe salvando comunque. Questo strumento va lanciato a mano: i test non si collegano mai a radio vere.

### Cosa non finisce mai in una sessione

PSK dei canali (sostituite dalla chiave predefinita), sezione `security` (chiavi pubblica, privata, admin), `device_id`, password Wi-Fi e MQTT della radio, pacchetti di amministrazione (`ADMIN_APP`), log e trasferimenti di file.

## 3. Avviare la radio finta

```
python tools/fake_radio.py --session sessione.jsonl --port 4404 --speed 10
python tools/fake_radio.py --nodes 5          # senza sessione: solo handshake con 5 nodi finti
```

| Opzione | Significato |
|---|---|
| `--session FILE` | sessione da riprodurre |
| `--port N` | porta TCP, predefinita **4404** (la 8686 è vietata: è del server MeshLens) |
| `--host H` | indirizzo di ascolto, predefinito `127.0.0.1` (altri indirizzi: nessuna autenticazione, avviso a video) |
| `--speed X` | velocità della riproduzione; `0` = nessuna attesa |
| `--max-gap S` | attesa massima tra due pacchetti (predefinita 5 s) |
| `--loop` | ripete la sessione all'infinito |
| `--no-restamp` | non riscrive `rx_time` con l'ora corrente |
| `--restart-on-connect` | ricomincia dall'inizio a ogni nuova connessione (altrimenti continua) |
| `--nodes N` | nodi finti quando non c'è una sessione (predefinito 3) |
| `--ack` | conferma finta ai messaggi con richiesta di conferma |
| `--nak MOTIVO` | con `--ack`: rifiuto al posto della conferma (es. `NO_RESPONSE`) |
| `--ack-delay S` | ritardo della conferma (predefinito 0,05 s) |
| `--sent-log FILE` | accoda a FILE (JSON lines) i pacchetti ricevuti da MeshLens |
| `--name`, `--my-num HEX`, `--channel-name` | nome, numero e canale secondario del nodo finto |
| `-v` | stampa i messaggi ricevuti da MeshLens |

Ctrl+C ferma il server in modo pulito.

## 4. Collegare MeshLens

Radio → Aggiungi → **Rete (IP)** → `127.0.0.1:4404`.

- Usa un'**istanza di prova** o i dati demo (`tools/demo_seed.py`): i pacchetti riprodotti entrano nel database come veri.
- `--loop` ripete gli stessi `id` pacchetto: la deduplicazione di MeshLens li scarta. Ha senso solo con un database nuovo e `--no-restamp`.
- Mai la porta 8686.
- La prova a mano con MeshLens la esegue l'utente; i test automatici usano `RadioConnector` e la vera `TCPInterface`.

## 5. Formato della sessione (versione 1)

File JSON lines (UTF-8): una riga = un oggetto; righe vuote e righe che iniziano con `#` sono ignorate.

| Riga | Significato |
|---|---|
| `{"format":"meshlens-session","version":1,"created":"…","source":"db\|radio\|api\|synthetic","my_node_num":N,"channel_name":"…","note":"…"}` | intestazione, obbligatoria e per prima |
| `{"k":"node","b64":"…"}` | `NodeInfo` serializzato in base64 (0..n) |
| `{"k":"config","b64":"…"}` | `FromRadio` di configurazione (my_info, metadata, channel, config, moduleConfig), già ripulito (0..n) |
| `{"k":"pkt","t":0.0,"b64":"…"}` | `FromRadio` con `packet`; `t` = secondi dal primo pacchetto, non decrescente |

Un `k` sconosciuto viene ignorato (compatibilità in avanti). Errori di base64 o di protobuf danno un messaggio con il numero di riga. Per scriverne una a mano basta costruire i `FromRadio` con `meshtastic.protobuf.mesh_pb2` e usare `replay_record.write_session`.

## 6. Limiti noti

- Nessuna amministrazione: i `ToRadio` con `ADMIN_APP` vengono registrati ma non hanno risposta, quindi le modifiche alla configurazione dalla UI non vengono applicate e vanno in timeout;
- nessun store&forward, un solo nodo proprio, nessun ricalcolo di ack per i traceroute;
- la radio finta risponde a ogni pacchetto con un `queueStatus`, come un firmware.

## 7. Per gli sviluppatori

`server/tests/fakeradio.py` offre `running_fake_radio(session=None, **cfg)` (porta 0, avvio e arresto garantiti) e i costruttori di pacchetti di prova. Test mirati:

```
PYTHONPATH=server python -m pytest -q server/tests/test_fake_radio.py
```

---

# MeshLens — Fake radio and replay (English)

`tools/replay_record.py` records a *session* (real packets with timing) from the MeshLens database (read-only, payloads up to 256 bytes, packets are rebuilt rather than copied bit-for-bit; enable the packet log in "all" mode first) or live from a real radio over TCP (`--radio HOST[:PORT]`, one TCP connection at a time). Channel PSKs, `security` config, `device_id` and passwords are never written to a session.

`tools/fake_radio.py` is a local TCP server speaking the Meshtastic stream protocol: it answers the configuration handshake with a synthetic node and channels and replays a session (`--speed`, `--loop`, `--ack`, `--sent-log`...). Default port 4404 (8686 is refused). In MeshLens: Radio, Add, Network (IP), `127.0.0.1:4404` — use a test instance, replayed packets are stored as real ones. It does not simulate RF, has no admin support and its acknowledgements are fake.
