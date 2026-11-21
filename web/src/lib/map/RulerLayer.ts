// Righello sulla mappa: linea tratteggiata e due punti, sopra i nodi.
import type { Map as MLMap } from 'maplibre-gl'
import { EMPTY } from './NodeLayer'
import type { MapTokens } from './tokens'

export function addRulerLayers(map: MLMap, t: MapTokens): void {
  map.addSource('ruler', { type: 'geojson', data: EMPTY })
  map.addLayer({
    id: 'ruler-line',
    type: 'line',
    source: 'ruler',
    filter: ['==', ['geometry-type'], 'LineString'],
    layout: { 'line-cap': 'round' },
    paint: { 'line-color': t.accent, 'line-width': 2.5, 'line-dasharray': [2, 1] },
  })
  map.addLayer({
    id: 'ruler-pts',
    type: 'circle',
    source: 'ruler',
    filter: ['==', ['geometry-type'], 'Point'],
    paint: { 'circle-radius': 6, 'circle-color': t.surfaceRaised, 'circle-stroke-color': t.accent, 'circle-stroke-width': 2.5 },
  })
}
