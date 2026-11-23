# MeshLens 1.5.0 — analisi bug e proposte (2026-11-23)

Analisi in sola lettura di server (MQTT/ingest/db, radio/API/sicurezza) e interfaccia web. Nessun file modificato.
Controlli senza problemi: `svelte-check` pulito, cataloghi it/en allineati (1333 chiavi), nessun `{@html}`, nessuna perdita di listener nella mappa, callback paho/meshtastic passati correttamente al loop, migrazioni 1–6 idempotenti, path traversal in tile/backup/restore, controllo Origin del WebSocket, segreti mascherati nella diagnostica.

Legenda confidenza: **C** = confermato (test o rilettura puntuale), **P** = molto probabile dal codice, **?** = plausibile.

## Bug — priorità alta

| # | Problema | Dove | Conf. | Correzione proposta |
|---|---|---|---|---|
| B1 | Con l'accesso dalla rete attivo, chi conosce il PIN può cambiare `update_repo` verso un proprio repo GitHub e far installare un exe arbitrario (l'hash viene dalla stessa release, quindi non protegge da una sorgente ostile). | settings.py:356, api.py:1342-1348 | C (catena verificata, install non eseguito) | Repo e token aggiornamenti modificabili, e download/installa eseguibili, solo da questo PC (loopback). |
| B2 | Un backup programmato per il ripristino può essere cancellato dalla pulizia automatica prima del riavvio: il ripristino salta in silenzio. | backup.py:151 `prune()` | C (riprodotto) | `prune()` esclude il backup in attesa di ripristino. |

## Bug — priorità media

| # | Problema | Dove | Conf. | Correzione |
|---|---|---|---|---|
| B3 | Invio MQTT rifiutato (503) mentre la connessione sta cadendo, ma paho lo tiene in coda e lo pubblica alla riconnessione: messaggio che l'utente crede non partito (e rimanda → doppio). Idem per "Non confermato" su connessione mezza aperta. | mqtt_client.py:117-132 | C (rc=4 e messaggio ancora in coda) | Togliere il messaggio dalla coda paho quando si rifiuta/scade, oppure stato "incerto" invece di "fallito". |
| B4 | Dopo 20 invii senza PUBACK (broker che scarta in silenzio) i successivi restano in coda e non partono più fino alla riconnessione. | mqtt_client.py:121 | ? | Liberare lo slot al timeout. |
| B5 | Collegamento radio IP senza timeout in un thread non daemon: con radio spenta "Esci" può tenere vivo il processo oltre i 30 s dell'installer → aggiornamento silenzioso che rinuncia. "Connessione in corso" fino a 5 min se la porta risponde ma non è Meshtastic. | radio_manager.py:73-76, radio.py:280-318 | P | Sonda TCP con timeout 5 s, timeout corto a TCPInterface, thread daemon. |
| B6 | Radio IP: nessun keepalive, lo stato resta "collegata" se la radio sparisce; durante la riconnessione interna della libreria gli invii vengono persi in silenzio. | radio.py:314-481 | ? (da sorgenti libreria) | SO_KEEPALIVE / heartbeat breve; ricreare l'interfaccia invece della riconnessione interna. |
| B7 | "Mostra PSK" dei canali della radio non è limitato a questo PC (le altre rotte con segreti sì). | api.py:1180 | C | Controllo loopback come per MQTT. |
| B8 | Accesso dalla rete attivabile con PIN di 4 cifre; lo stato non autenticato rivela che il PIN è corto. | api.py:481-499, 678 | P | Rifiutare lan_access con PIN corto; non esporre `pin_short` senza login. |
| B9 | "Carica precedenti" nel feed MQTT non avanza se i messaggi più vecchi sono nascosti dal filtro nazioni o sono radio: richiede sempre la stessa pagina. | MessageFeed.svelte:98-111 | C | Cursore sul messaggio più vecchio ricevuto, non su quello mostrato. |
| B10 | Dopo riconnessione del WebSocket stati di consegna MQTT e messaggi pubblici non si riallineano (resta "Invio…" fino al ricaricamento). | App.svelte:204-222, chat.ts:104-113 | C | Ricaricare i messaggi MQTT alla riconnessione; `insertMessage` aggiorna stato/heard_by se il messaggio esiste. |
| B11 | "Carica precedenti" nelle conversazioni radio si blocca quando in memoria ci sono 2000 messaggi (quelli caricati vengono subito tagliati). | Thread.svelte:61-72, chat.ts:176-182 | C | Non tagliare lo storico richiesto esplicitamente; cursore per conversazione. |

## Bug — priorità bassa

- **B12** Chiavi di canale "imparate" diventano personalizzate al riavvio del collegamento MQTT; un canale tolto continua a decifrare (app.py ~147). Conf. P.
- **B13** Traceroute: hop sconosciuto `!ffffffff` diventa un nodo/collegamento (ingest.py:41-49). Conf. C.
- **B14** `heard_by` sovrascritto e stato riportato indietro quando il messaggio non è più in memoria (ingest.py:211-249). Conf. ?
- **B15** Dizionari interni senza limite alimentati dal traffico dei broker pubblici (ingest.py `_telemetry_time`, `_rf_hops_time`, `_channel_buckets`). Conf. ?
- **B16** Pacchetti MQTT con id 0 trattati come duplicati per 10 minuti (bridge di terze parti). Conf. ?
- **B17** Errore TCP generico ("MeshInterfaceError") se la porta risponde ma non è Meshtastic o la radio ha già un altro client.
- **B18** PSK di lunghezza non valida accettata nella configurazione canali della radio (può isolare il nodo). Conf. C.
- **B19** Durante letture/scritture admin il lock di invio blocca traceroute e messaggi per minuti senza risposta.
- **B20** Installer: nessuna pulizia dei file della versione precedente (`[InstallDelete]` per `_internal`).
- **B21** Alcune POST di modifica senza `require_json` (CSRF da altri servizi sullo stesso host).
- **B22** Paginazione `time < before` salta messaggi con lo stesso secondo al confine di pagina.
- **B23** Testo scritto durante un invio lento viene cancellato quando l'invio termina.
- **B24** Nessun rilevamento di WebSocket "mezzo aperto" dopo sospensione del PC (il server manda uno stato ogni 5 s: basta un timer).
- **B25** `localStorage` bloccato dal browser → pagina bianca (manca un accesso protetto unico).
- **B26** Minori: `last_error` MQTT mai azzerato dopo riconnessione riuscita; eventi in coda persi alla chiusura; contatori orari netstats azzerati prima di scriverli; ping di istanza singola che passa dal proxy di sistema; doppio setup PIN concorrente.

## Proposte — migliorie a ciò che c'è

| Cod. | Titolo | Cosa fa | Effort | Note |
|---|---|---|---|---|
| E1 | Primo avvio guidato | Checklist dopo il PIN (broker/radio, i tuoi nodi, mappa offline); stati vuoti con pulsante d'azione. | S | — |
| E2 | Ricerca globale (Ctrl+K) | Trova nodi, conversazioni, messaggi, impostazioni e ci salta. | M | Oggi c'è solo la ricerca nell'elenco conversazioni. |
| E3 | Preferiti/ignorati sulla radio | La stella diventa anche "favorito" nel NodeDB della radio; "Ignora nodo". | M | Serve radio 2.6+. |
| E4 | Ricerca ed esportazione messaggi | Ricerca nel testo di tutte le chat, filtri, export TXT/CSV di una conversazione. | S-M | Utile come registro di stazione. |
| E5 | Strati mappa | Precisione posizione, heatmap, solo infrastruttura, etichette SNR/hop sui collegamenti, legenda. | M | — |
| E6 | Regole di avviso personalizzate | Oltre a batteria/silenzio/chiave/occupazione canale: parola chiave in un canale, SNR sotto soglia, geofence, per nodo. | M | Estende alerts.py. |
| E7 | Profili di configurazione radio | Salvare e applicare profili ("ripetitore", "mobile"), confronto tra due radio. | M | Serve radio. |

## Proposte — nuove funzioni

| Cod. | Titolo | Cosa fa | Effort | Note |
|---|---|---|---|---|
| E8 | Grafo topologia | I collegamenti Neighbor Info sono già sulla mappa: aggiungere vista a grafo, nodi cerniera/isolati, abilitazione del modulo sulla propria radio. | M | — |
| E9 | Sensori: Detection, Paxcounter | Eventi porta/PIR e conteggio persone sul nodo, con grafico e avviso (oggi solo configurabili). | M | Dipende da nodi che li inviano. |
| E10 | Messaggi rapidi | Risposte pronte con variabili ({batteria}, {posizione}) nel composer; sync con i canned di T-Deck/T-Pager. | S-M | Sync con radio reale. |
| E11 | Salute rete e autonomia | Batterie in calo con stima di autonomia, tensione/corrente, confronto di più nodi sullo stesso grafico. | M | Dati già raccolti. |
| E12 | Controllo privacy posizione | Avvisa se si trasmette posizione precisa su canali pubblici o con uplink MQTT, con correzione guidata. | S | — |
| E13 | Canali e admin remoto | Generatore PSK, export QR/link dei canali (oggi solo import), avviso chiavi deboli, comandi remoti (riavvio, ora). | M | Sicurezza. |
| E14 | Traceroute periodico | Traceroute automatico verso nodi scelti con storico dei percorsi. | M | Traffico radio: limite di frequenza. |
| E15 | Bot e automazioni | Risposte automatiche opt-in (`!ping` con SNR/hop), webhook in uscita. | M | Rischio spam: limiti. |
| E16 | ATAK/PLI in visualizzazione | Contatti ATAK sulla mappa. | L | Nicchia, difficile da testare. |

## Proposte — affidabilità

| Cod. | Titolo | Cosa fa | Effort |
|---|---|---|---|
| E17 | Radio simulata e replay | Registra pacchetti reali e li riproduce con una radio finta (seriale/TCP) per i test. | M |
| E18 | Firma e "Novità" | Firma del codice (SmartScreen), note di rilascio mostrate dopo l'aggiornamento, canale beta. | S-M (+ costo certificato) |
| E19 | Accesso ospite | PIN secondario in sola lettura (mappa e messaggi, niente invio/config). | M |
| E20 | Diagnosi collegamento radio | Spiega perché una radio non si collega (porta occupata, driver, BLE, IP) con passi concreti. | S-M |
| E21 | Conservazione per tipo | Tempi diversi per posizioni/telemetria/pacchetti, spazio per tabella, archivio prima della pulizia. | M |

## Raccomandazione

1. **Release 1.5.1 di correzioni**: B1, B2, B3, B5, B7, B8, B9, B10, B11 (+ i bassi rapidi B13, B17, B18, B20, B23, B24).
2. **Release 1.6.0 di funzioni**, mia scelta: E1, E6, E11, E4, E12, E17 (dati già presenti o effort basso, nessuna radio reale indispensabile). Poi E3/E10/E7 quando si può provare con le radio.
