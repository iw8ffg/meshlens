MeshLens è uno strumento tecnico e affidabile, da sala radio moderna: denso di informazioni ma leggibile, rapido sul campo, sobrio. Il tema principale è scuro (`dark`); il chiaro (`light`) ha pari qualità per l'uso sotto il sole. L'interfaccia è in italiano.

## Contenuto

- Testi brevi, diretti, in italiano. Il pulsante dice cosa fa: «Avvia prova», «Installa e riavvia», «Ripristina».
- Dai del tu. Scrivi «Collega una radio», non «L'utente deve collegare una radio».
- Gli errori dicono cosa è successo e cosa fare: «COM6 è usata da un'altra applicazione. Chiudila e riprova.»
- Numeri in formato italiano, sempre con unità: «3,59 V», «−3,5 dB», «12 min fa», «3,4 km». Il meno è il segno tipografico «−».
- Niente punti esclamativi, niente emoji, niente gergo non spiegato. Sigle radio (SNR, RSSI, LoRa) restano com'è, con l'unità accanto.
- Nomi dei nodi e id (`!3a7f91c2`) non si traducono né si abbreviano; gli id sono sempre in `mono`.
- Casing: solo la prima parola maiuscola nei titoli e nelle etichette («Soglie degli avvisi»).

## Fondamenti visivi

**Colore.** Sfondo `bg`, pannelli `surface`, schede e popup `surface-raised`, campi `surface-sunken`. Testo `ink`, secondario `ink-muted`. Un solo colore d'azione, `accent`, con testo `on-accent` sopra. Stati: `ok`, `warn`, `danger`, ciascuno con il suo fondo `-soft`; il colore non basta mai da solo, aggiungi parola o icona. `brand-teal`, `brand-sky` e `brand-amber` sono solo del marchio.

**Colori di dato.** Gli stessi su mappa, grafici e tabelle. Ultimo contatto: `contact-fresh`, `contact-recent`, `contact-old`. SNR: `snr-good`, `snr-mid`, `snr-bad`, `snr-none`. Fonte: `src-radio`, `src-mqtt`, `src-both`. Verde e rosso non bastano per chi ha un daltonismo: SNR porta sempre segno (▲ ● ▼) e valore, la fonte si distingue dalla forma dell'anello.

**Tipografia.** `IBM Plex Sans` per il testo, `IBM Plex Mono` per id, coordinate, SNR e tensioni (cifre tabulari). Titolo di schermata `title-lg`, pannello `title`, sezione `subtitle`, testo `body`, note `caption`. Su telefono il testo non scende sotto 14 px (`text-min-phone`): lì `caption` e `data-sm` non si usano.

**Spaziatura e forme.** Passi `space-1`…`space-12` (4, 8, 12, 16, 20, 24, 32, 48 px). Pulsanti e campi `radius-md`, schede e popup `radius-lg`, modali e sheet `radius-xl`, chip e interruttori `radius-pill`. Bordi sottili `line`; il contorno di un controllo è `line-strong` (3:1).

**Ombre.** `shadow-1` appena visibile per le schede, `shadow-2` per popup e toast, `shadow-3` per modali e bottom sheet. Niente sfocature estese (`backdrop-filter`) né ombre colorate.

**Focus.** Anello solido di 2 px in `focus-ring` con distanza di 2 px, 3:1 su tutti i fondi in entrambi i temi. Non si toglie mai.

**Movimento.** Solo transizioni brevi: `duration-fast` (120 ms) per hover e pressione, `duration-base` (200 ms) per pannelli e modali. Nessuna animazione continua; il caricamento usa segnaposto fissi. Rispetta `prefers-reduced-motion`.

**Layout.** Desktop (1280–1920 px): barra superiore `topbar-h` di 48 px, mappa a tutto schermo e pannello laterale di `panel-w` (380 px, ridimensionabile da 320 a 560); le pagine lunghe (Rete, Configura, Impostazioni) occupano l'area sotto la barra. Telefono (375–430 px): mappa in alto, pannello a scomparsa (bottom sheet) e barra in basso `bottomnav-h` di 64 px con Mappa, Nodi, Chat, Copertura, Altro. Aree toccabili minime `touch-min` di 44 px.

**Stati.** Hover: bordo `ink-muted`. Premuto: bordo `accent`. Attivo/selezionato: `accent-soft` con testo `accent-ink`. Disabilitato: opacità ridotta e un testo che spiega perché.

## Mappa

- Fondo mappa: `map-land`, `map-water`, `map-road`, `map-label`, uno stile per tema. Le etichette hanno 4.5:1.
- Marker: riempimento = ultimo contatto, anello = fonte, stella `brand-amber` = «Mio nodo», contorno `marker-outline`.
- Collegamenti: 3 px, colore per SNR; tratteggio solo se vengono da un traceroute.
- Posizioni approssimate: cerchio tratteggiato col raggio d'errore.
- La mappa non ha animazioni: gli spostamenti si fanno senza transizione.
- Legenda sempre disponibile; su telefono è un pulsante che si espande.

## Icone e bandiere

Icone a tratto di 1,75 px su griglia 24, stile Lucide, sempre `currentColor` e con etichetta di testo. Le bandiere sono SVG, mai emoji.

## Marchio e Meshtastic

Il marchio MeshLens è in `assets/Logo`. Il logo Meshtastic compare solo nel badge «Compatibile con Meshtastic®» (Accesso, Informazioni, piè di pagina delle Impostazioni), mai come icona dell'app, sempre accanto alla frase: «MeshLens non è affiliato al progetto Meshtastic. Meshtastic® è un marchio registrato di Meshtastic LLC». Il file ufficiale del logo va preso da meshtastic.org e usato nel rispetto della sua trademark policy.

## Accessibilità

Testo 4.5:1 sui fondi indicati nelle note dei token, in entrambi i temi; icone, bordi dei controlli e anello di focus 3:1. Su telefono testo da 14 px e aree da 44 px. Ogni stato ha una parola o un'icona oltre al colore. Le modali «a rischio» usano `role="alertdialog"`.
