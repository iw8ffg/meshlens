// Traccia di un nodo (storico posizioni) sulla mappa.
import type { Map as MLMap } from 'maplibre-gl'
import type { Feature, FeatureCollection, LineString } from 'geojson'
import { EMPTY } from './NodeLayer'
import type { MapTokens } from './tokens'

export function trackData(track: [number, number][] | null): Feature<LineString> | FeatureCollection {
  return track && track.length > 1 ? { type: 'Feature', geometry: { type: 'LineString', coordinates: track }, properties: {} } : EMPTY
}

export function addTrackLayer(map: MLMap, t: MapTokens): void {
  map.addSource('track', { type: 'geojson', data: EMPTY })
  map.addLayer({
    id: 'track',
    type: 'line',
    source: 'track',
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': t.accent, 'line-width': 3 },
  })
}
