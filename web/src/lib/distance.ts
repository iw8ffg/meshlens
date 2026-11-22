import type { Node, Radio } from './types'
import { t, type MsgKey } from './i18n/index.svelte'

const R = 6_371_000
const rad = (d: number) => (d * Math.PI) / 180

type P = { lat: number; lon: number }

/** Distanza in metri sulla sfera (haversine). */
export function haversineM(a: P, b: P): number {
  const dLat = rad(b.lat - a.lat)
  const dLon = rad(b.lon - a.lon)
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** Direzione iniziale da a verso b, 0–360 gradi rispetto al nord. */
export function bearingDeg(a: P, b: P): number {
  const dLon = rad(b.lon - a.lon)
  const y = Math.sin(dLon) * Math.cos(rad(b.lat))
  const x = Math.cos(rad(a.lat)) * Math.sin(rad(b.lat)) - Math.sin(rad(a.lat)) * Math.cos(rad(b.lat)) * Math.cos(dLon)
  return ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
}

const SECTORS: MsgKey[] = ['nodes.card.n', 'nodes.card.ne', 'nodes.card.e', 'nodes.card.se', 'nodes.card.s', 'nodes.card.sw', 'nodes.card.w', 'nodes.card.nw']

export function cardinal(deg: number): string {
  return t(SECTORS[Math.round((((deg % 360) + 360) % 360) / 45) % 8])
}

/** `kind`: da dove si misura (radio collegata, radio locale, posizione del browser); `label` e' il testo nella lingua corrente. */
export type Origin = { lat: number; lon: number; label: string; kind: 'radio' | 'local' | 'browser' }

const placed = (n: Node | undefined): n is Node & { lat: number; lon: number } => !!n && n.lat !== null && n.lon !== null

/** Punto da cui misurare le distanze: radio connessa, radio locale, posizione del browser. */
export function myOrigin(nodes: Map<string, Node>, radios: Radio[], browser: P | null): Origin | null {
  for (const r of radios) {
    if (r.state !== 'connected' || !r.my_node_id) continue
    const n = nodes.get(r.my_node_id)
    if (placed(n)) return { lat: n.lat, lon: n.lon, label: t('nodes.fromRadio', { name: r.name }), kind: 'radio' }
  }
  for (const n of nodes.values()) {
    if (n.is_local_radio && placed(n)) return { lat: n.lat, lon: n.lon, label: t('nodes.fromYourRadio'), kind: 'local' }
  }
  if (browser) return { lat: browser.lat, lon: browser.lon, label: t('nodes.fromYourPosition'), kind: 'browser' }
  return null
}
