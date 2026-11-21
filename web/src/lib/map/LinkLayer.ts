// Collegamenti: linea di 3 px colorata per SNR (token snr-*), tratteggio solo per i traceroute.
import type { ExpressionSpecification, Map as MLMap } from 'maplibre-gl'
import { EMPTY } from './NodeLayer'
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

export function addLinkLayers(map: MLMap, t: MapTokens): void {
  map.addSource('links', { type: 'geojson', data: EMPTY })
  const opacity: ExpressionSpecification = ['interpolate', ['linear'], ['get', 'age_h'], 0, 1, 24, 0.4]
  map.addLayer({
    id: 'links',
    type: 'line',
    source: 'links',
    filter: ['!=', ['get', 'source'], 'traceroute'],
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
}
