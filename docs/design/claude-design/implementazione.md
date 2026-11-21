# Note di implementazione

Per Svelte 5 e MapLibre GL, sull'app locale per Windows usata da browser di PC e telefono.

## Token e variabili CSS

- `tokens.css` (generato da `tokens.json`) va importato una volta in `app.css`. I colori sono variabili su `:root` e su `[data-theme="light"]`; il tema scuro è il predefinito.
- Imposta `data-theme` su `<html>`. Parti da `prefers-color-scheme`, lascia un interruttore manuale (Auto / Scuro / Chiaro) e salvalo in `localStorage`. Aggiungi `color-scheme: dark light` e `<meta name="color-scheme">` per le barre di scorrimento e i campi nativi.
- Tutte le dimensioni vengono da `space-*`, `radius-*`, `size-*`: nessun valore fisso nei componenti. Le variabili `--touch-min`, `--control-h-desktop`, `--control-h-phone` decidono altezze e aree toccabili.
- Desktop e telefono si distinguono con una classe sul contenitore (`vp-phone`) decisa da `matchMedia('(max-width: 820px)')`, non con tanti media query sparsi.

## Struttura dei componenti (Svelte)

```
src/lib/ui/        Button, Field, Select, Switch, Check, Segmented, Chip, Badge,
                   SnrBadge, BatteryBadge, SourceMark, Flag, Table, Card, Banner,
                   Toast, Progress, Empty, Skeleton, Modal, Sheet, Icon
src/lib/map/       Map, NodeLayer, LinkLayer, TrackLayer, CoverageLayer, Legend,
                   MapControls, NodePopup
src/lib/shell/     TopBar, TabBar, BottomNav, Panel (con grip), Page
src/routes/        accesso, mappa, nodi, nodo/[id], rete, chat, copertura, radio,
                   configura/[radio], impostazioni
```

- `Modal` ha una variante `risk`: bordo `danger`, `role="alertdialog"`, pulsante di conferma disabilitato finché la casella non è spuntata, focus iniziale su «Annulla».
- `Sheet` ha tre punti di fermo (chiuso, 40%, 78%); si trascina dalla maniglia con eventi `pointer` e supporta anche i pulsanti per chi non trascina.
- `Panel` su desktop è ridimensionabile (320–560 px) dal bordo sinistro; salva la larghezza in `localStorage`.
- I testi con formato italiano passano da un solo modulo (`format.ts`): `Intl.NumberFormat('it-IT')` per i numeri, età relative con soglie (ora, min, h, g).

## Regole per la mappa (MapLibre)

- Una sola sorgente GeoJSON per i nodi con `cluster: true`. Marker come layer, non come elementi HTML: con centinaia di nodi i marker HTML rallentano.
  - Riempimento: `circle-color` con `step` sull'età del contatto (120 min, 1440 min) → `contact-fresh | recent | old`.
  - Anello: layer `symbol` con tre immagini nello sprite (pieno, tratteggiato, doppio), perché `circle-stroke` non si tratteggia. Le immagini si ricolorano a ogni cambio di tema.
  - Stella «Mio nodo»: layer `symbol` separato, filtrato su `mine`.
- Collegamenti: layer `line` con `line-color` a `step` sull'SNR (0 e −10 dB), `line-dasharray` `[2,1.5]` per i traceroute, `line-width` 3.
- Cerchio di precisione: poligono generato dal raggio in metri (per esempio con turf), non `circle-radius` in pixel; riempimento `src-mqtt` al 13%, bordo tratteggiato.
- Cluster: cerchio `surface-raised` con bordo `accent` e conteggio in `mono`.
- Range Test: sorgente a parte; punti colorati per SNR, mancanti come simbolo «croce in cerchio», linea del percorso punteggiata, base con anello `brand-amber`.
- Stile del fondo: due file JSON (`map-dark.json`, `map-light.json`) che usano i valori di `map-land`, `map-water`, `map-road`, `map-label`. Al cambio di tema si fa `setStyle` e si riaggiungono sorgenti e layer.
- Modalità Automatica / Solo online / Solo offline: l'indicatore «Mappa offline» compare quando i tile arrivano dalla copia locale (PMTiles); mostra la data della copia.
- Popup e legenda sono HTML sopra la mappa, non markup MapLibre, così seguono i token.
- Attribuzione «© OpenStreetMap contributors · Protomaps» sempre visibile su desktop e nella scheda Informazioni su telefono.
- Niente `fadeDuration` e niente animazioni continue: `fadeDuration: 0`, `flyTo` solo su richiesta.

## Uso da telefono

- Testo minimo 14 px, campi a 16 px (evita lo zoom automatico di iOS), pulsanti e righe di almeno 44 px.
- Usa `100dvh` e `env(safe-area-inset-*)` per barra in basso e sheet; la tastiera non deve coprire il compositore della chat (usa `visualViewport`).
- Campi PIN e numerici con `inputmode="numeric"`; PIN con `autocomplete="current-password"`.
- La tabella Rete scorre in orizzontale in un contenitore con `overflow-x: auto`; la colonna Nodo è `position: sticky; left: 0`.
- Il contatore della chat conta byte (UTF-8), non caratteri: «è» pesa 2 byte.
- Le operazioni lunghe (traceroute fino a 60 s, lettura LoRa, download mappe) mostrano avanzamento e continuano se la schermata si blocca: lo stato vive sul server locale, il telefono lo rilegge alla riapertura.
- Durante la prova di copertura valuta `navigator.wakeLock` per tenere lo schermo acceso.

## Font, icone, bandiere

- Il PC può non avere internet: scarica `IBM Plex Sans` (400, 500, 600) e `IBM Plex Mono` (400, 500) in WOFF2 e servili in locale con `@font-face`; i token elencano le famiglie con fallback di sistema.
- Icone: `lucide-svelte` o `@lucide/svelte`, importate una per una.
- Bandiere: pacchetto SVG (per esempio `flag-icons`, forma 4x3), mai emoji.

## Accessibilità

- Contrasto: i token sono verificati a coppie; non introdurre colori fuori dai token.
- Ogni stato porta testo o icona oltre al colore. Lo stato dei messaggi ha etichette accessibili («Consegnato», «Non consegnato»).
- Focus sempre visibile (`:focus-visible`, anello `focus-ring`).
- `prefers-reduced-motion`: azzera le transizioni.
