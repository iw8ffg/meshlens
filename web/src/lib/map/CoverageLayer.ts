// Range Test sulla mappa: percorso punteggiato, punti per SNR, mancanti (croce in cerchio), base ambra.
import type { Map as MLMap } from 'maplibre-gl'
import { MISSING_IMAGE } from './sprites'
import { EMPTY } from './NodeLayer'
import { snrColorExpr } from './LinkLayer'
import type { MapTokens } from './tokens'

export const COVERAGE_SOURCES = ['cov-track', 'cov-missing', 'cov-points', 'cov-base'] as const

export function addCoverageLayers(map: MLMap, t: MapTokens): void {
  for (const id of COVERAGE_SOURCES) map.addSource(id, { type: 'geojson', data: EMPTY })
  map.addLayer({
    id: 'cov-track',
    type: 'line',
    source: 'cov-track',
    layout: { 'line-cap': 'round' },
    paint: { 'line-color': t.accent, 'line-width': 2, 'line-dasharray': [0.5, 2] },
  })
  map.addLayer({
    id: 'cov-missing',
    type: 'symbol',
    source: 'cov-missing',
    layout: { 'icon-image': MISSING_IMAGE, 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  })
  map.addLayer({
    id: 'cov-points',
    type: 'circle',
    source: 'cov-points',
    paint: {
      'circle-color': snrColorExpr(t),
      'circle-radius': 6,
      'circle-stroke-width': 1.5,
      'circle-stroke-color': t.outline,
    },
  })
  map.addLayer({
    id: 'cov-base',
    type: 'circle',
    source: 'cov-base',
    paint: {
      'circle-color': t.outline,
      'circle-radius': 8,
      'circle-stroke-width': 3,
      'circle-stroke-color': t.amber,
    },
  })
}
