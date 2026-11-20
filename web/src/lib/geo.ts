/**
 * Raggio approssimativo (metri) dell'incertezza di posizione per `precision_bits`.
 * Formula: 23_300_000 / 2**bits, arrotondata al metro (13 bit -> 2844 m).
 * Restituisce null se la posizione e' esatta (>= 16 bit) o il valore manca/non e' valido.
 */
export function precisionRadiusM(bits: number | null): number | null {
  if (bits === null || !Number.isFinite(bits) || bits < 1 || bits >= 16) return null
  return Math.round(23_300_000 / 2 ** bits)
}

/** Testo italiano per l'incertezza: "± 710 m" sotto 1 km, altrimenti "± 1,4 km" (una cifra decimale). */
export function formatPrecision(bits: number | null): string | null {
  const r = precisionRadiusM(bits)
  if (r === null) return null
  if (r < 1000) return `± ${Math.round(r / 10) * 10} m`
  const km = (Math.round(r / 100) / 10).toString().replace('.', ',')
  return `± ${km} km`
}

/** Anello GeoJSON chiuso ([lon, lat]) che approssima un cerchio di raggio `radiusM`. */
export function circlePolygon(lat: number, lon: number, radiusM: number, steps = 64): [number, number][] {
  const dLat = radiusM / 111_320
  const dLon = radiusM / (111_320 * Math.max(0.01, Math.cos((lat * Math.PI) / 180)))
  const ring: [number, number][] = []
  for (let i = 0; i < steps; i++) {
    const a = (2 * Math.PI * i) / steps
    ring.push([lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)])
  }
  ring.push(ring[0])
  return ring
}
