// Collegamenti: linea di 3 px colorata per SNR (token snr-*), tratteggio solo per i traceroute.
import type { ExpressionSpecification, Map as MLMap } from 'maplibre-gl'
import { EMPTY } from './NodeLayer'
import { LABEL_MINZOOM, LABEL_MINZOOM_DENSE } from './overlays'
import type { MapTokens } from './tokens'

/** Colore per SNR: step a -10 e 0 dB, snr-none se il valore manca. Legge la proprieta' `snr`. */
export function snrColorExpr(t: MapTokens): ExpressionSpecification {
  return [
    'case',
    ['==', ['typeof', ['get', 'snr']], 'number'],
    ['step', ['get', 'snr'], t.snrBad, -10, t.snrMid, 0, t.snrGood],
    t.snrNone,
  ]
}

export const TRACE_DASH: [number, number] = [2, 1.5]
/** Puntinato per i collegamenti di ricezione diretta vista da un gateway MQTT. */
export const GATEWAY_DASH: [number, number] = [0.5, 1.5]

/** Con i glyph disponibili aggiunge anche `links-labels` (SNR / «diretto» a meta' linea). */
export function addLinkLayers(map: MLMap, t: MapTokens, hasGlyphs = false): void {
  map.addSource('links', { type: 'geojson', data: EMPTY })
  const opacity: ExpressionSpecification = ['interpolate', ['linear'], ['get', 'age_h'], 0, 1, 24, 0.4]
  map.addLayer({
    id: 'links',
    type: 'line',
    source: 'links',
    filter: ['all', ['!=', ['get', 'source'], 'traceroute'], ['!=', ['get', 'source'], 'mqtt_gateway']],
    layout: { 'line-cap': 'round' },
    paint: { 'line-color': snrColorExpr(t), 'line-width': 3, 'line-opacity': opacity },
  })
  map.addLayer({
    id: 'links-trace',
    type: 'line',
    source: 'links',
    filter: ['==', ['get', 'source'], 'traceroute'],
    paint: { 'line-color': snrColorExpr(t), 'line-width': 3, 'line-opacity': opacity, 'line-dasharray': TRACE_DASH },
  })
  map.addLayer({
    id: 'links-gateway',
    type: 'line',
    source: 'links',
    filter: ['==', ['get', 'source'], 'mqtt_gateway'],
    paint: { 'line-color': snrColorExpr(t), 'line-width': 3, 'line-opacity': opacity, 'line-dasharray': GATEWAY_DASH },
  })
  if (hasGlyphs) {
    map.addLayer({
      id: 'links-labels',
      type: 'symbol',
      source: 'links',
      minzoom: LABEL_MINZOOM,
      filter: ['!=', ['get', 'label'], ''],
      layout: {
        'symbol-placement': 'line-center',
        'text-field': ['get', 'label'],
        'text-font': ['Noto Sans Regular'],
        'text-size': 12,
        'text-optional': true,
        'text-padding': 4,
      },
      paint: { 'text-color': t.ink, 'text-halo-color': t.surfaceRaised, 'text-halo-width': 1.5 },
    })
  }
}

/** Con molte etichette si mostrano solo da zoom piu' alto. */
export function setLinkLabelZoom(map: MLMap, dense: boolean): void {
  if (map.getLayer('links-labels')) map.setLayerZoomRange('links-labels', dense ? LABEL_MINZOOM_DENSE : LABEL_MINZOOM, 24)
}
