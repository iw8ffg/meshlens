// Righello: due punti sulla mappa (liberi o agganciati a un nodo), distanza e direzione.
import type { Feature, FeatureCollection } from 'geojson'
import { bearingDeg, cardinal, haversineM } from '../distance'
import { formatMeters } from '../geo'

export type RulerPoint = { lon: number; lat: number; nodeId: string | null }

/** Aggiunge un punto (massimo 2): il terzo ricomincia da solo. */
export function addRulerPoint(pts: RulerPoint[], p: RulerPoint): RulerPoint[] {
  return pts.length >= 2 ? [p] : [...pts, p]
}

export function rulerGeoJSON(pts: RulerPoint[]): FeatureCollection {
  const features: Feature[] = pts.map((p, idx) => ({
    type: 'Feature',
    geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
    properties: { idx },
  }))
  if (pts.length === 2) {
    features.push({
      type: 'Feature',
      geometry: { type: 'LineString', coordinates: pts.map((p) => [p.lon, p.lat]) },
      properties: {},
    })
  }
  return { type: 'FeatureCollection', features }
}

export function rulerText(pts: RulerPoint[], name: (id: string) => string): string {
  if (pts.length === 0) return 'Tocca il primo punto sulla mappa'
  if (pts.length === 1) return 'Tocca il secondo punto'
  const [a, b] = pts
  const deg = bearingDeg({ lat: a.lat, lon: a.lon }, { lat: b.lat, lon: b.lon })
  let s = `${formatMeters(haversineM({ lat: a.lat, lon: a.lon }, { lat: b.lat, lon: b.lon }))} · ${Math.round(deg) % 360}° ${cardinal(deg)}`
  if (a.nodeId && b.nodeId) s += ` · da ${name(a.nodeId)} a ${name(b.nodeId)}`
  return s
}
