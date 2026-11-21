// Waypoint: dati per il layer della mappa, validazione del modulo di invio, etichetta di scadenza.
import type { Feature, FeatureCollection, Point } from 'geojson'
import type { Waypoint } from './types'
import { T } from './strings/waypoint'

export const WP_ICONS = ['📍', '🏠', '⛺', '🚗', '🚩', '📡', '🏥', '⛽', '🔥', '💧', '🍴', '⭐'] as const

export const WP_DEFAULT_IMAGE = 'wp-default'
export const WP_NAME_MAX = 30
export const WP_DESC_MAX = 100

const bytes = (s: string) => new TextEncoder().encode(s).length

/** Nome dell'immagine di un'icona: `wp-` + codepoint esadecimale, `wp-default` se manca. */
export function wpImageName(icon: string): string {
  const cp = icon ? icon.codePointAt(0) : undefined
  return cp === undefined ? WP_DEFAULT_IMAGE : `wp-${cp.toString(16)}`
}

/** Carattere da disegnare per un nome immagine `wp-*` (la puntina se non e' un codepoint). */
export function wpImageChar(name: string): string {
  const m = /^wp-([0-9a-f]{1,6})$/.exec(name)
  const cp = m ? parseInt(m[1], 16) : NaN
  return Number.isFinite(cp) && cp >= 0x20 && cp <= 0x10ffff ? String.fromCodePoint(cp) : WP_ICONS[0]
}

/** Solo i waypoint non scaduti; `expire` null non scade mai. */
export function waypointData(list: Waypoint[], nowS: number): FeatureCollection {
  const features: Feature<Point>[] = []
  for (const w of list) {
    if (w.expire !== null && w.expire <= nowS) continue
    features.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [w.lon, w.lat] },
      properties: { id: w.id, name: w.name, img: wpImageName(w.icon), mine: w.mine },
    })
  }
  return { type: 'FeatureCollection', features }
}

export interface WaypointFormValues {
  name: string
  description: string
  lat: number
  lon: number
  expireH: number | null
}

/** Primo errore del modulo (testo da strings/waypoint), null se valido. */
export function validateWaypoint(f: WaypointFormValues): string | null {
  const name = f.name.trim()
  if (name === '') return T.errName
  if (bytes(name) > WP_NAME_MAX) return T.errNameLong
  if (bytes(f.description) > WP_DESC_MAX) return T.errDescLong
  if (!Number.isFinite(f.lat) || !Number.isFinite(f.lon) || Math.abs(f.lat) > 90 || Math.abs(f.lon) > 180) return T.errCoords
  if (f.expireH !== null && (!Number.isInteger(f.expireH) || f.expireH < 1 || f.expireH > 720)) return T.errExpire
  return null
}

export function expiryLabel(expire: number | null, nowS: number): string {
  if (expire === null) return T.noExpiry
  if (expire <= nowS) return T.expired
  const d = new Date(expire * 1000)
  return T.expiresAt(new Intl.DateTimeFormat('it-IT', { dateStyle: 'medium', timeStyle: 'short' }).format(d))
}
