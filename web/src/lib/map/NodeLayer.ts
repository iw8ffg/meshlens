// Layer dei nodi: riempimento = ultimo contatto, anello = fonte (immagini dello sprite),
// stella ambra = «Mio nodo», cluster con conteggio, selezione e cerchio di precisione.
import type { ExpressionSpecification, Map as MLMap } from 'maplibre-gl'
import type { Feature, FeatureCollection, Point, Polygon } from 'geojson'
import { circlePolygon, precisionRadiusM } from '../geo'
import type { Node } from '../types'
import { RING_IMAGE, STAR_IMAGE } from './sprites'
import type { RingKind } from './sprites'
import type { MapTokens } from './tokens'

export const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

/** Soglie del colore di contatto, in minuti (come contactClass). */
export const FRESH_MIN = 120
export const RECENT_MIN = 1440
/** Valore di `age_min` per i nodi mai sentiti. */
export const NEVER_MIN = 1e9

/** Fonte per l'anello: solo RF, solo MQTT, entrambe. */
export function ringKind(n: Pick<Node, 'sources'>): RingKind {
  const rf = n.sources.includes('rf')
  const other = n.sources.some((s) => s !== 'rf')
  return rf && other ? 'both' : rf ? 'radio' : 'mqtt'
}

export function ageMinutes(lastHeard: number | null, now: number): number {
  return lastHeard === null ? NEVER_MIN : Math.max(0, (now - lastHeard) / 60)
}

export function isMine(n: Pick<Node, 'is_mine' | 'is_local_radio'>): boolean {
  return !!(n.is_mine || n.is_local_radio)
}

export function nodeFeatures(nodes: Node[], now: number): Feature<Point>[] {
  const out: Feature<Point>[] = []
  for (const n of nodes) {
    if (n.lat === null || n.lon === null) continue
    out.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [n.lon, n.lat] },
      properties: { id: n.id, age_min: ageMinutes(n.last_heard, now), origin: ringKind(n), mine: isMine(n) },
    })
  }
  return out
}

export function selectionData(n: Node | undefined, now: number): FeatureCollection {
  if (!n || n.lat === null || n.lon === null) return EMPTY
  return {
    type: 'FeatureCollection',
    features: [
      { type: 'Feature', geometry: { type: 'Point', coordinates: [n.lon, n.lat] }, properties: { age_min: ageMinutes(n.last_heard, now) } },
    ],
  }
}

export function precisionData(n: Node | undefined): FeatureCollection {
  if (!n || n.lat === null || n.lon === null) return EMPTY
  const r = precisionRadiusM(n.precision_bits)
  if (r === null) return EMPTY
  const f: Feature<Polygon> = {
    type: 'Feature',
    geometry: { type: 'Polygon', coordinates: [circlePolygon(n.lat, n.lon, r)] },
    properties: {},
  }
  return { type: 'FeatureCollection', features: [f] }
}

/** circle-color con `step` sull'eta' del contatto: contact-fresh | recent | old. */
export function contactColorExpr(t: MapTokens): ExpressionSpecification {
  return ['step', ['get', 'age_min'], t.contactFresh, FRESH_MIN, t.contactRecent, RECENT_MIN, t.contactOld]
}

export function addNodeLayers(map: MLMap, t: MapTokens, hasGlyphs: boolean): void {
  map.addSource('nodes', { type: 'geojson', data: EMPTY, cluster: true, clusterMaxZoom: 7, clusterRadius: 40 })
  map.addSource('selected', { type: 'geojson', data: EMPTY })
  map.addSource('precision', { type: 'geojson', data: EMPTY })
  map.addLayer({ id: 'precision-fill', type: 'fill', source: 'precision', paint: { 'fill-color': t.srcMqtt, 'fill-opacity': 0.13 } })
  map.addLayer({
    id: 'precision-line',
    type: 'line',
    source: 'precision',
    paint: { 'line-color': t.srcMqtt, 'line-width': 1.5, 'line-dasharray': [2, 2] },
  })
  map.addLayer({
    id: 'clusters',
    type: 'circle',
    source: 'nodes',
    filter: ['has', 'point_count'],
    paint: {
      'circle-color': t.surfaceRaised,
      'circle-stroke-color': t.accent,
      'circle-stroke-width': 2,
      'circle-radius': ['step', ['get', 'point_count'], 15, 20, 19, 100, 25],
    },
  })
  if (hasGlyphs) {
    map.addLayer({
      id: 'cluster-count',
      type: 'symbol',
      source: 'nodes',
      filter: ['has', 'point_count'],
      layout: { 'text-field': ['get', 'point_count_abbreviated'], 'text-font': ['Noto Sans Regular'], 'text-size': 13 },
      paint: { 'text-color': t.ink },
    })
  }
  const single: ExpressionSpecification = ['!', ['has', 'point_count']]
  map.addLayer({
    id: 'points-ring',
    type: 'symbol',
    source: 'nodes',
    filter: single,
    layout: {
      'icon-image': ['match', ['get', 'origin'], 'both', RING_IMAGE.both, 'mqtt', RING_IMAGE.mqtt, RING_IMAGE.radio],
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
  })
  map.addLayer({
    id: 'points',
    type: 'circle',
    source: 'nodes',
    filter: single,
    paint: {
      'circle-color': contactColorExpr(t),
      'circle-radius': 6,
      'circle-stroke-width': 1.5,
      'circle-stroke-color': t.outline,
    },
  })
  map.addLayer({
    id: 'points-mine',
    type: 'symbol',
    source: 'nodes',
    filter: ['all', single, ['==', ['get', 'mine'], true]],
    layout: { 'icon-image': STAR_IMAGE, 'icon-offset': [9, -9], 'icon-allow-overlap': true, 'icon-ignore-placement': true },
  })
  map.addLayer({
    id: 'selected',
    type: 'circle',
    source: 'selected',
    paint: {
      'circle-color': contactColorExpr(t),
      'circle-radius': 11,
      'circle-stroke-width': 3,
      'circle-stroke-color': t.accent,
    },
  })
}
