// Funzioni pure degli strati della mappa (E5): nessun accesso a MapLibre. I raggi di precisione
// sono punti `circle` con raggio in pixel a zoom 22 (px22): la GPU scala il cerchio con lo zoom,
// nessun poligono per nodo. I nodi ignorati non compaiono mai (visibleNodes/isIgnored).
import type { Feature, Point } from 'geojson'
import type { Map as MLMap } from 'maplibre-gl'
import type { Node } from '../types'
import { precisionRadiusM } from '../geo'
import { isIgnored } from '../filters'
import type { LayerKey, LayerState } from './layerstate'
import { addHeatLayer } from './HeatLayer'
import { addPrecisionLayer } from './PrecisionLayer'
import { addTakLayer } from './TakLayer'
import type { MapTokens } from './tokens'

export const PRECISION_MAX = 3000
export const HEAT_MAX = 20000
/** Metri per pixel a zoom 22 all'equatore: 156543.03392 / 2^22. */
export const M_PER_PX_Z22 = 0.037322767717
export const LABEL_MINZOOM = 9
export const LABEL_MINZOOM_DENSE = 11
const DENSE_LABELS = 800

const hasPos = (n: Node): n is Node & { lat: number; lon: number } => n.lat !== null && n.lon !== null && !isIgnored(n)

/** Cerchi di precisione: solo bits 1..15 con posizione; i PRECISION_MAX con il raggio maggiore. */
export function precisionCircles(nodes: Node[]): Feature<Point>[] {
  const items: { f: Feature<Point>; r: number }[] = []
  for (const n of nodes) {
    if (!hasPos(n)) continue
    const r = precisionRadiusM(n.precision_bits)
    if (r === null) continue
    const cos = Math.max(0.01, Math.cos((n.lat * Math.PI) / 180))
    const px22 = Math.round((r / (M_PER_PX_Z22 * cos)) * 1000) / 1000
    items.push({ r, f: { type: 'Feature', geometry: { type: 'Point', coordinates: [n.lon, n.lat] }, properties: { r_m: r, px22 } } })
  }
  if (items.length > PRECISION_MAX) {
    items.sort((a, b) => b.r - a.r)
    items.length = PRECISION_MAX
  }
  return items.map((i) => i.f)
}

/** Punti della mappa di calore: solo con posizione; oltre HEAT_MAX si tengono i piu' recenti. */
export function heatPoints(nodes: Node[]): Feature<Point>[] {
  let list = nodes.filter(hasPos)
  if (list.length > HEAT_MAX) {
    list = list.sort((a, b) => (b.last_heard ?? 0) - (a.last_heard ?? 0)).slice(0, HEAT_MAX)
  }
  return list.map((n) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [n.lon!, n.lat!] }, properties: {} }))
}

/** Con molte etichette si mostrano solo da zoom piu' alto. */
export const denseLabels = (featureCount: number): boolean => featureCount > DENSE_LABELS

/**
 * Aggiunge i layer degli strati: va chiamata DOPO addNodeLayers (precision/heat si inseriscono prima
 * di `precision-fill`). Ordine: precisione, calore, ATAK.
 */
export function addOverlayLayers(map: MLMap, t: MapTokens, hasGlyphs: boolean): void {
  addPrecisionLayer(map, t)
  addHeatLayer(map, t)
  addTakLayer(map, t, hasGlyphs)
}

const LAYER_IDS: Record<LayerKey, string[]> = {
  precision: ['precision-all-circle'],
  heat: ['heat-layer'],
  infra: [],
  linkLabels: ['links-labels'],
  tak: ['tak-points', 'tak-labels'],
}

/** Visibilita' dei layer in base allo stato degli strati; gli id inesistenti si ignorano. */
export function applyOverlayVisibility(map: MLMap, s: LayerState): void {
  for (const key of Object.keys(LAYER_IDS) as LayerKey[]) {
    for (const id of LAYER_IDS[key]) {
      if (map.getLayer(id)) map.setLayoutProperty(id, 'visibility', s[key] ? 'visible' : 'none')
    }
  }
}
