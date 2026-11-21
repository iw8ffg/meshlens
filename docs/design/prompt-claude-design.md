# Prompt per Claude Design — riprogettazione dell'interfaccia di MeshLens

> Da incollare in Claude Design. Allega anche le schermate attuali (`docs/img/screen-*.png`) e il logo (`docs/img/logo.svg`), così parte da ciò che esiste.

---

Riprogetta da zero l'interfaccia di **MeshLens**, una webapp locale per Windows che si usa dal browser del PC e del telefono sulla Wi-Fi di casa. Serve a **osservare, gestire e usare reti radio Meshtastic** (radio LoRa a bassa potenza, messaggi senza internet). L'app riunisce due fonti: il traffico pubblico MQTT di Meshtastic, cioè nodi, posizioni, messaggi e telemetria, e le radio dell'utente collegate via USB o Bluetooth. È usata da un radioamatore esperto, da solo: deve essere **densa di informazioni ma leggibile**, rapida da usare sul campo e bella da vedere.

## Obiettivo

Un design system completo e le schermate di tutta l'app, coerenti tra desktop (1280–1920 px) e telefono (375–430 px), pronti da implementare in **Svelte 5 + MapLibre GL**. Il layout attuale funziona ma è spartano: tienilo come riferimento funzionale, non estetico.

## Identità

- Nome: **MeshLens**. Il logo attuale è una lente sopra una rete di nodi, file `logo.svg` allegato: rifiniscilo o proponi un'evoluzione coerente.
- Carattere: strumento tecnico e affidabile, da "sala radio moderna". Niente estetica giocosa.
- **Tema scuro come principale**, più un tema chiaro di pari qualità (sul campo, sotto il sole, serve il chiaro).
- **Logo Meshtastic:** l'app è compatibile con Meshtastic ma **non è un prodotto ufficiale**. Integra il marchio solo come badge di compatibilità, per esempio «Compatibile con Meshtastic®», in schermata di accesso, Informazioni e piè di pagina delle impostazioni, ben separato dal marchio MeshLens. Va rispettata la trademark policy di Meshtastic (meshtastic.org): il logo non deve far pensare a un prodotto ufficiale o approvato. Prevedi la scritta «MeshLens non è affiliato al progetto Meshtastic. Meshtastic® è un marchio registrato di Meshtastic LLC». Non usare il logo Meshtastic come icona dell'app.

## Struttura dell'app

Le schede sono **Mappa, Nodi, Rete, Copertura, Chat, Radio, Impostazioni**.

- **Desktop:** mappa a tutto schermo con un pannello laterale ridimensionabile.
- **Telefono:** mappa in alto e pannello a scomparsa; navigazione in basso, che oggi è una barra a schede scorrevole. Proponi qualcosa di migliore: per esempio 4–5 voci principali più "Altro", oppure una barra con icone ed etichette.
- **Barra di stato in alto:**
  - stato MQTT (connesso o no, messaggi al secondo);
  - nodi visibili;
  - radio collegate;
  - avvisi;
  - aggiornamento disponibile.

### Schermate da disegnare

Per ognuna prevedi gli stati vuoto, caricamento ed errore.

1. **Accesso con PIN:** primo avvio (scelta del PIN) e accesso successivo, con un eventuale blocco temporaneo dopo tentativi errati.
2. **Mappa:**
   - marker dei nodi colorati per fonte (radio, MQTT, entrambe) e per ultimo contatto (verde sotto le 2 h, giallo sotto le 24 h, grigio oltre), con cluster;
   - cerchio di precisione per le posizioni approssimate;
   - linee dei collegamenti tra nodi, colorate per SNR (≥ 0 dB verde, da −10 a 0 giallo, sotto −10 rosso), tratteggiate se vengono da un traceroute;
   - traccia storica di un nodo;
   - legenda compatta;
   - controlli dei livelli (collegamenti, tracce, copertura);
   - indicatore "mappa offline".
3. **Nodi:**
   - elenco con ricerca;
   - filtri (nazione con bandiere, fonte, radio, ultimo contatto 2 h / 24 h / 7 g, ruolo);
   - per riga: nome, età del contatto, batteria e icona della fonte.
4. **Dettaglio nodo**, scheda o pannello:
   - identità: nome lungo e corto, id `!hex`, hardware, ruolo, firmware, nazione;
   - posizione e precisione;
   - batteria, tensione, utilizzo del canale e airtime;
   - **"Sentito da"**: le radio con SNR, RSSI e salti, più i gateway MQTT;
   - stella "Mio nodo";
   - **grafico** di batteria e tensione su 24 h / 7 g / 30 g, con la linea della soglia di avviso;
   - **traceroute**: pulsante, attesa fino a 60 s, percorso di andata e ritorno con l'SNR di ogni salto, storico;
   - azioni: messaggio diretto, configura, mostra percorso.
5. **Rete:**
   - tabella dei nodi "miei" o di tutti (ultimo contatto, ruolo, firmware, batteria, tensione, SNR, salti, utilizzo del canale, airtime), ordinabile e leggibile anche su telefono;
   - **avvisi**: batteria bassa e nodo silenzioso, con banner e lista.
6. **Chat:**
   - conversazioni per canale delle radio e messaggi diretti;
   - scelta della radio da cui trasmettere;
   - stato di ogni messaggio: ⏳ in invio, ✓ inviato, ✓✓ consegnato, ⚠ non consegnato;
   - vista **"Pubblico (MQTT)"** in sola lettura, con un suo filtro (nazioni, nodi senza posizione) e il canale MQTT su ogni messaggio (LongFast, MediumFast…);
   - limite di 200 byte per messaggio, con un contatore.
7. **Copertura (Range Test):**
   - **guida di preparazione** con controlli in tempo reale (✓ / ⚠ / —): radio collegata, mobile sentito, GPS recente, precisione della posizione, pacchetti Range Test;
   - avviso quando le posizioni sono approssimate e conferma esplicita per continuare;
   - pulsanti **"Prepara le radio"** e **"Ripristina"**, con anteprima delle modifiche;
   - **prova in corso**: punti, mancanti, perdita %, ultimo SNR, durata, pulsante Ferma;
   - **risultati sulla mappa**: punti colorati per SNR, punti mancanti, percorso, base, distanza massima, popup del punto;
   - storico delle prove (rinomina, note, elimina).
8. **Radio:**
   - radio collegate via USB o Bluetooth, con stato (collegata, in riconnessione, errore con messaggio in italiano), nodo locale, canali, chiave admin da copiare;
   - aggiunta di una radio: elenco delle porte COM con nome del dispositivo, oppure scansione Bluetooth.
9. **Configura nodo**, pannello grande o pagina:
   - lettura con avanzamento ("Lettura LoRa 3/25…");
   - schede semplici: Generale, Posizione (con posizione fissa), Telemetria, LoRa, Canali (8 righe, psk mascherata con "Mostra" e "Genera"), Moduli;
   - **Avanzate**: tutti gli altri campi generati da uno schema;
   - **anteprima delle differenze**: valore attuale → nuovo, righe "a rischio" evidenziate con il motivo e la casella obbligatoria "Ho capito che questa modifica può isolare il nodo";
   - avanzamento dell'applicazione ed esito ("Applicato e verificato", "La verifica non coincide", errore);
   - copie di sicurezza e ripristino;
   - riavvio;
   - guida alla chiave admin.
10. **Impostazioni:**
    - nazioni da salvare nello storico;
    - conservazione dei dati;
    - MQTT: broker e **canali da ascoltare**;
    - soglie degli avvisi;
    - accesso dalla rete locale;
    - **Mappe offline**: modalità Automatica / Solo online / Solo offline, spazio libero, scarica mondo, Italia o area visibile con stima e conferma, avanzamento con Annulla, elenco con Elimina;
    - **Aggiornamenti**: versione, token GitHub mascherato con la guida, "Controlla ora", note della release, Scarica, "Installa e riavvia" con conferma;
    - informazioni e licenze.

## Requisiti di design

- **Componenti e token:** colori semantici, tipografia, spaziature, raggi, ombre ed elevazioni, stati (hover, focus, disabilitato, attivo), icone (un set coerente, per esempio Lucide o simile, open source).
- **Componenti da definire:**
  - pulsanti (principale, secondario, distruttivo, solo icona);
  - campi, select, interruttori, checkbox, chip dei filtri, segmented control;
  - tabelle dense con colonna fissa e scorrimento orizzontale su telefono;
  - schede, pannelli a scomparsa (bottom sheet), modali di conferma (normale e "a rischio");
  - toast e banner (avviso, errore, aggiornamento);
  - barre di avanzamento;
  - badge di stato (connesso, riconnessione, errore);
  - badge SNR e batteria (con il caso "USB" quando è alimentato);
  - grafico a linee;
  - popup della mappa;
  - legenda;
  - stato vuoto.
- **Colori di dato** coerenti in tutta l'app, distinguibili anche per i daltonici, da usare in modo identico su mappa, grafici e tabelle:
  - ultimo contatto: verde / giallo / grigio;
  - SNR: verde / giallo / rosso / grigio;
  - fonte: radio / MQTT / entrambe.
- **Accessibilità:** contrasto WCAG AA, aree toccabili di almeno 44 px su telefono, testo di almeno 14 px su telefono, focus visibile.
- **Densità:** il desktop può essere compatto; il telefono è pensato per l'uso con una mano.
- **Lingua dell'interfaccia: italiano.** Testi brevi e chiari, numeri in formato italiano (virgola decimale, "3,59 V", "12 min fa").
- **Mappa:** proponi stili coerenti con il tema per il fondo mappa (chiaro e scuro); i marker devono restare leggibili su entrambi.
- **Prestazioni:** nessun effetto pesante (blur estesi, animazioni continue); animazioni brevi e sobrie.

## Cosa consegnare

1. Il design system: token (in un formato facile da convertire in variabili CSS) e libreria dei componenti con gli stati.
2. Le schermate desktop e telefono di tutte le sezioni sopra, in tema scuro e chiaro, con gli stati vuoto, caricamento ed errore dove servono.
3. Il logo MeshLens rifinito (SVG) e l'icona dell'app (16–256 px), più il badge «Compatibile con Meshtastic®» conforme alla trademark policy.
4. Brevi note di implementazione: struttura dei componenti, variabili CSS, regole per la mappa, punti di attenzione per l'uso da telefono.
