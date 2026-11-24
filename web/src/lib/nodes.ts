import { visibleNodes } from './filters'
// Funzioni pure per Nodi, dettaglio e Rete (nessuna dipendenza dall'interfaccia).
import { num } from './format'
import type { SourceKind } from './ui/logic'
import type { Alert, Node, RadioFlagResult, RadioFlags } from './types'
import { alertLabel } from './alerts'
import { t, type MsgKey } from './i18n/index.svelte'
import { translateServer } from './i18n/server'
import { getJSON, send } from './api'

// ---- 1.6 (WP4): nodi ignorati e flag nel NodeDB delle radio collegate ----
const flagPath = (id: string) => `/nodes/${encodeURIComponent(id)}`

/** Ignora/ripristina in MeshLens (e, con radio, anche sulle radio collegate). */
export const setIgnored = (id: string, ignored: boolean, radio = true) =>
  send<{ node: Node; radios: RadioFlagResult[]; warning?: string | null }>('PUT', `${flagPath(id)}/ignored`, { ignored, radio })
/** Avviso del server (es. un tuo nodo ignorato solo in MeshLens, mai sulle radio), tradotto. */
export function ignoreWarning(res: { warning?: string | null }): string {
  return res.warning ? translateServer(res.warning) : ''
}
export const getRadioFlags = (id: string) => getJSON<{ radios: RadioFlags[] }>(`${flagPath(id)}/radio-flags`)
export const setRadioFlags = (id: string, flags: { favorite?: boolean; ignored?: boolean }, radioId?: string | null) =>
  send<{ radios: RadioFlagResult[] }>('PUT', `${flagPath(id)}/radio-flags`, { ...flags, radio_id: radioId ?? null })
/** Tutti i nodi ignorati, anche quelli non piu' in memoria (elenco per ripristinarli). */
export const getIgnoredNodes = () => getJSON<Node[]>('/nodes/ignored')

/** Nodi ignorati ordinati per nome (unica vista che li mostra: il ripristino). */
export function ignoredNodes(nodes: Iterable<Node>): Node[] {
  return [...nodes]
    .filter((n) => n.is_ignored)
    .sort((a, b) => nodeName(a).toLowerCase().localeCompare(nodeName(b).toLowerCase()) || a.num - b.num)
}

export const nodeName = (n: Pick<Node, 'long_name' | 'short_name' | 'id'>): string => n.long_name || n.short_name || n.id

/** Fonte da mostrare nell'anello: radio, MQTT o entrambe; `null` se il nodo non ne ha. */
export function sourceKind(n: Pick<Node, 'sources' | 'mqtt_gateways'>): SourceKind | null {
  const rf = n.sources.includes('rf')
  const mqtt = n.sources.includes('mqtt')
  if (rf && mqtt) return 'both'
  if (rf) return 'radio'
  if (mqtt) return 'mqtt'
  return n.mqtt_gateways > 0 ? 'mqtt' : null
}

/** 101 = alimentazione esterna (non e' una percentuale). */
export function batteryView(b: number | null): { pct: number; usb: boolean } | null {
  if (b === null || !Number.isFinite(b)) return null
  return b > 100 ? { pct: 100, usb: true } : { pct: b, usb: false }
}

/** Minuti dall'ultimo contatto, `null` se mai sentito (mai negativo). */
export function contactMinutes(lastHeard: number | null, now: number): number | null {
  if (lastHeard === null || !Number.isFinite(lastHeard)) return null
  return Math.max(0, (now - lastHeard) / 60)
}

/** Periodi del filtro «Ultimo contatto»; `labelKey` si traduce con t() al momento di mostrarlo. */
export const AGE_OPTIONS: { labelKey: MsgKey; hours: number | null }[] = [
  { labelKey: 'nodes.ageAll', hours: null },
  { labelKey: 'nodes.age2h', hours: 2 },
  { labelKey: 'nodes.age24h', hours: 24 },
  { labelKey: 'nodes.age7d', hours: 168 },
]

export const SOURCE_OPTIONS: { labelKey: MsgKey; value: string }[] = [
  { labelKey: 'nodes.sourceRadio', value: 'rf' },
  { labelKey: 'nodes.sourceMqtt', value: 'mqtt' },
]

/** Aggiunge o toglie `v` senza modificare l'elenco. */
export function toggleIn<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
}

/** Avviso (nella lingua corrente) per una riga della Rete: «Batteria al 12%» / «Silenzioso da 30 h». */
export function alertText(a: Pick<Alert, 'kind' | 'value' | 'detail'> & { node_name?: string }): string {
  return alertLabel(a)
}

/** Avvisi per nodo: id -> elenco. */
export function alertsByNode(alerts: Alert[]): Map<string, Alert[]> {
  const out = new Map<string, Alert[]>()
  for (const a of alerts) {
    const l = out.get(a.node_id)
    if (l) l.push(a)
    else out.set(a.node_id, [a])
  }
  return out
}

/** Numero con `decimals` cifre, trattino se assente; unita' opzionale. */
export function fmtOpt(v: number | null | undefined, decimals = 1, unit = ''): string {
  return v === null || v === undefined ? '–' : `${num(v, decimals)}${unit}`
}

/** Salti per l'interfaccia: «0 (diretto)», numero, «≥ 1» (noto solo che non e' diretto) o «—». */
export function hopsLabel(hops: number | null | undefined, hopsMin?: number | null): string {
  if (typeof hops === 'number') return hops === 0 ? t('nodes.hopsDirect') : String(hops)
  if (typeof hopsMin === 'number' && hopsMin >= 1) return `≥ ${hopsMin}`
  return '—'
}

/** Nodi da mostrare in Rete: «solo miei» e «solo preferiti» si combinano in AND; mai gli ignorati. */
export function networkNodes<T extends Pick<Node, 'is_mine' | 'is_favorite' | 'is_ignored'>>(nodes: T[], onlyMine: boolean, onlyFav: boolean): T[] {
  return visibleNodes(nodes).filter((n) => (!onlyMine || !!n.is_mine) && (!onlyFav || !!n.is_favorite))
}
