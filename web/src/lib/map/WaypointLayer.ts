// Layer dei waypoint: icone emoji disegnate su canvas (font di sistema), nessun elemento HTML per punto.
import type { Map as MLMap } from 'maplibre-gl'
import type { MapTokens } from './tokens'
import { EMPTY } from './NodeLayer'
import { WP_DEFAULT_IMAGE, wpImageChar } from '../waypoints'

const SIZE = 48
export const WP_IMAGE_RE = /^wp-/

/** Disegna l'emoji in un cerchio (sfondo `surfaceRaised`, bordo `accent` se `mine`) e la registra. */
export function ensureWaypointImage(map: MLMap, name: string, tk: MapTokens, mine = false): void {
  if (map.hasImage(name)) return
  const canvas = document.createElement('canvas')
  canvas.width = SIZE
  canvas.height = SIZE
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const c = SIZE / 2
  ctx.beginPath()
  ctx.arc(c, c, c - 2, 0, Math.PI * 2)
  ctx.fillStyle = tk.surfaceRaised
  ctx.fill()
  ctx.lineWidth = mine ? 3 : 1.5
  ctx.strokeStyle = mine ? tk.accent : tk.outline
  ctx.stroke()
  ctx.font = `24px system-ui, "Segoe UI Emoji", "Apple Color Emoji", "Noto Color Emoji", sans-serif`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = tk.ink
  ctx.fillText(name === WP_DEFAULT_IMAGE ? wpImageChar('') : wpImageChar(name), c, c + 1)
  map.addImage(name, ctx.getImageData(0, 0, SIZE, SIZE), { pixelRatio: 2 })
}

/** Registra una volta per mappa il gestore delle immagini mancanti (sopravvive a `setStyle`). */
export function bindWaypointImages(map: MLMap, getTokens: () => MapTokens): void {
  map.on('styleimagemissing', (e: { id: string }) => {
    if (WP_IMAGE_RE.test(e.id)) ensureWaypointImage(map, e.id, getTokens())
  })
}

export function addWaypointLayers(map: MLMap, tk: MapTokens, hasGlyphs = false): void {
  map.addSource('waypoints', { type: 'geojson', data: EMPTY })
  // anello dei miei waypoint: l'immagine e' una sola per icona, quindi il bordo e' un layer a parte
  map.addLayer({
    id: 'wp-mine',
    type: 'circle',
    source: 'waypoints',
    filter: ['==', ['get', 'mine'], true],
    paint: { 'circle-radius': 13, 'circle-color': tk.accent, 'circle-opacity': 0, 'circle-stroke-color': tk.accent, 'circle-stroke-width': 2.5 },
  })
  map.addLayer({
    id: 'wp-icons',
    type: 'symbol',
    source: 'waypoints',
    layout: {
      'icon-image': ['get', 'img'],
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
      ...(hasGlyphs
        ? {
            'text-field': ['get', 'name'],
            'text-font': ['Noto Sans Regular'],
            'text-size': 12,
            'text-offset': [0, 1.6],
            'text-anchor': 'top',
            'text-optional': true,
          }
        : {}),
    },
    paint: hasGlyphs ? { 'text-color': tk.ink, 'text-halo-color': tk.outline, 'text-halo-width': 1.2 } : {},
  })
}
