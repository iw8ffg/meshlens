// Strato ATAK (E16): contatti PLI con posizione. Le etichette richiedono i glyph.
import type { Feature, Point } from 'geojson'
import type { Map as MLMap } from 'maplibre-gl'
import type { TakContact } from '../types'
import { EMPTY, ageMinutes } from './NodeLayer'
import type { MapTokens } from './tokens'

export function addTakLayer(map: MLMap, t: MapTokens, hasGlyphs: boolean): void {
  map.addSource('tak', { type: 'geojson', data: EMPTY })
  map.addLayer({
    id: 'tak-points',
    type: 'circle',
    source: 'tak',
    paint: { 'circle-radius': 8, 'circle-color': t.amber, 'circle-stroke-color': t.outline, 'circle-stroke-width': 2 },
  })
  if (hasGlyphs) {
    map.addLayer({
      id: 'tak-labels',
      type: 'symbol',
      source: 'tak',
      minzoom: 7,
      layout: {
        'text-field': ['get', 'label'],
        'text-font': ['Noto Sans Regular'],
        'text-size': 12,
        'text-offset': [0, 1.2],
        'text-anchor': 'top',
        'text-optional': true,
      },
      paint: { 'text-color': t.ink, 'text-halo-color': t.surfaceRaised, 'text-halo-width': 1.5 },
    })
  }
}

/** Feature dei contatti con posizione; l'etichetta e' il nominativo o, se manca, il nome del nodo. */
export function takFeatures(
  contacts: TakContact[],
  nodeName: (id: string) => string,
  now: number = Date.now() / 1000,
): Feature<Point>[] {
  const out: Feature<Point>[] = []
  for (const c of contacts) {
    if (c.lat === null || c.lon === null) continue
    out.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [c.lon, c.lat] },
      properties: { id: c.node_id, label: c.callsign ?? nodeName(c.node_id), team: c.team, role: c.role, compressed: c.compressed, age_min: ageMinutes(c.time, now) },
    })
  }
  return out
}
