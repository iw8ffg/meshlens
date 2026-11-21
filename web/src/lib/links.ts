import type { Feature, FeatureCollection, LineString } from 'geojson'
import type { Link, Node } from './types'

export function snrColor(snr: number | null): string {
  if (snr === null) return '#8a8a8a'
  if (snr >= 0) return '#2e9d4b'
  if (snr >= -10) return '#d9a400'
  return '#c8382e'
}

/**
 * Linee della mappa: A->B e B->A diventano una sola linea (SNR migliore, tempo piu' recente).
 * I link con un estremo assente o senza posizione sono saltati.
 */
export function linksToGeoJSON(
  links: Link[],
  nodes: Map<string, Node>,
  now: number = Date.now() / 1000,
): FeatureCollection<LineString> {
  const merged = new Map<string, { a: string; b: string; snr: number | null; time: number; source: Link['source'] }>()
  for (const l of links) {
    const [a, b] = l.from_id < l.to_id ? [l.from_id, l.to_id] : [l.to_id, l.from_id]
    const key = `${a}|${b}`
    const cur = merged.get(key)
    if (!cur) {
      merged.set(key, { a, b, snr: l.snr, time: l.time, source: l.source })
      continue
    }
    if (l.snr !== null && (cur.snr === null || l.snr > cur.snr)) cur.snr = l.snr
    if (l.time > cur.time) {
      cur.time = l.time
      cur.source = l.source
    }
  }
  const features: Feature<LineString>[] = []
  for (const m of merged.values()) {
    const na = nodes.get(m.a)
    const nb = nodes.get(m.b)
    if (!na || !nb || na.lat === null || na.lon === null || nb.lat === null || nb.lon === null) continue
    features.push({
      type: 'Feature',
      geometry: {
        type: 'LineString',
        coordinates: [
          [na.lon, na.lat],
          [nb.lon, nb.lat],
        ],
      },
      properties: {
        color: snrColor(m.snr),
        source: m.source,
        snr: m.snr,
        age_h: Math.max(0, (now - m.time) / 3600),
        from_id: m.a,
        to_id: m.b,
      },
    })
  }
  return { type: 'FeatureCollection', features }
}
