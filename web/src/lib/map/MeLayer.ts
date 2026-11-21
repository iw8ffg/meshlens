// «Dove sono»: punto della posizione del browser con il cerchio di accuratezza, sotto il righello.
import type { Map as MLMap } from 'maplibre-gl'
import type { Feature, FeatureCollection } from 'geojson'
import { circlePolygon } from '../geo'
import { EMPTY } from './NodeLayer'
import type { MapTokens } from './tokens'

export function addMeLayers(map: MLMap, t: MapTokens): void {
  map.addSource('me', { type: 'geojson', data: EMPTY })
  map.addLayer({
    id: 'me-acc',
    type: 'fill',
    source: 'me',
    filter: ['==', ['geometry-type'], 'Polygon'],
    paint: { 'fill-color': t.accent, 'fill-opacity': 0.12 },
  })
  map.addLayer({
    id: 'me-dot',
    type: 'circle',
    source: 'me',
    filter: ['==', ['geometry-type'], 'Point'],
    paint: { 'circle-radius': 7, 'circle-color': t.accent, 'circle-stroke-color': t.outline, 'circle-stroke-width': 2 },
  })
}

export function meData(pos: { lat: number; lon: number; accuracy: number } | null): FeatureCollection {
  if (!pos) return EMPTY
  const features: Feature[] = []
  if (pos.accuracy >= 1 && pos.accuracy <= 5000) {
    features.push({ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [circlePolygon(pos.lat, pos.lon, pos.accuracy)] } })
  }
  features.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: [pos.lon, pos.lat] } })
  return { type: 'FeatureCollection', features }
}
