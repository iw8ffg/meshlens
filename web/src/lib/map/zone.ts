// Zona poligonale (editor delle regole geofence): funzioni pure. I punti sono coppie [lon, lat],
// come `params.polygon` delle regole di avviso (3..64 punti, chiuso implicitamente).
import type { Feature, FeatureCollection } from 'geojson'

export const ZONE_MIN = 3
export const ZONE_MAX = 64
export type ZonePoint = [number, number]
export type ZoneError = 'tooFew' | 'tooMany' | 'range' | 'selfIntersect'

const valid = (p: ZonePoint): boolean => Number.isFinite(p[0]) && Number.isFinite(p[1]) && Math.abs(p[0]) <= 180 && Math.abs(p[1]) <= 90

/** Aggiunge un vertice; rifiuta (restituisce `z`) oltre ZONE_MAX, fuori scala o uguale all'ultimo. */
export function addVertex(z: ZonePoint[], p: ZonePoint): ZonePoint[] {
  if (z.length >= ZONE_MAX || !valid(p)) return z
  const last = z[z.length - 1]
  if (last && last[0] === p[0] && last[1] === p[1]) return z
  return [...z, p]
}

export function moveVertex(z: ZonePoint[], i: number, p: ZonePoint): ZonePoint[] {
  if (!Number.isInteger(i) || i < 0 || i >= z.length || !valid(p)) return z
  return z.map((q, j) => (j === i ? p : q))
}

export function removeVertex(z: ZonePoint[], i: number): ZonePoint[] {
  if (!Number.isInteger(i) || i < 0 || i >= z.length) return z
  return z.filter((_, j) => j !== i)
}

const orient = (a: ZonePoint, b: ZonePoint, c: ZonePoint): number => {
  const v = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
  return v > 0 ? 1 : v < 0 ? -1 : 0
}
const within = (a: ZonePoint, b: ZonePoint, c: ZonePoint): boolean =>
  Math.min(a[0], b[0]) <= c[0] && c[0] <= Math.max(a[0], b[0]) && Math.min(a[1], b[1]) <= c[1] && c[1] <= Math.max(a[1], b[1])

function segmentsIntersect(a: ZonePoint, b: ZonePoint, c: ZonePoint, d: ZonePoint): boolean {
  const o1 = orient(a, b, c)
  const o2 = orient(a, b, d)
  const o3 = orient(c, d, a)
  const o4 = orient(c, d, b)
  if (o1 !== o2 && o3 !== o4) return true
  return (o1 === 0 && within(a, b, c)) || (o2 === 0 && within(a, b, d)) || (o3 === 0 && within(c, d, a)) || (o4 === 0 && within(c, d, b))
}

/** Primo problema della zona, o null se valida. Lati non adiacenti che si toccano = autointersezione. */
export function zoneError(z: ZonePoint[]): ZoneError | null {
  if (z.length < ZONE_MIN) return 'tooFew'
  if (z.length > ZONE_MAX) return 'tooMany'
  if (!z.every(valid)) return 'range'
  const n = z.length
  for (let i = 0; i < n; i++) {
    const a = z[i]
    const b = z[(i + 1) % n]
    for (let j = i + 1; j < n; j++) {
      if (j === i + 1 || (i === 0 && j === n - 1)) continue // lati adiacenti
      if (segmentsIntersect(a, b, z[j], z[(j + 1) % n])) return 'selfIntersect'
    }
  }
  return null
}

/** Poligono chiuso (da 3 punti), linea (2 punti) e i vertici come punti numerati. */
export function zoneGeoJSON(z: ZonePoint[]): FeatureCollection {
  const features: Feature[] = []
  if (z.length >= 3) {
    features.push({ type: 'Feature', geometry: { type: 'Polygon', coordinates: [[...z, z[0]]] }, properties: {} })
  } else if (z.length === 2) {
    features.push({ type: 'Feature', geometry: { type: 'LineString', coordinates: z }, properties: {} })
  }
  z.forEach((p, i) => features.push({ type: 'Feature', geometry: { type: 'Point', coordinates: p }, properties: { idx: i } }))
  return { type: 'FeatureCollection', features }
}

/** Riquadro [[minLon, minLat], [maxLon, maxLat]]; null per una zona vuota. */
export function zoneBounds(z: ZonePoint[]): [[number, number], [number, number]] | null {
  if (z.length === 0) return null
  let a = Infinity
  let b = Infinity
  let c = -Infinity
  let d = -Infinity
  for (const [lon, lat] of z) {
    a = Math.min(a, lon)
    b = Math.min(b, lat)
    c = Math.max(c, lon)
    d = Math.max(d, lat)
  }
  return [[a, b], [c, d]]
}

/**
 * Sfondo dell'editor: con mappe "offline" si usa lo stile offline (o lo sfondo a tinta unita se non
 * ci sono mappe), senza chiamate di rete; altrimenti si prova lo stile online, con ripiego sull'offline
 * (se esiste) quando non risponde o il browser e' senza rete.
 */
export type ZoneBasemap = 'online' | 'offline' | 'fallback'
export function zoneBasemap(mode: 'auto' | 'online' | 'offline', hasOffline: boolean, browserOnline: boolean): ZoneBasemap {
  if (mode === 'offline') return hasOffline ? 'offline' : 'fallback'
  if (mode === 'auto' && !browserOnline) return hasOffline ? 'offline' : 'fallback'
  return 'online'
}
