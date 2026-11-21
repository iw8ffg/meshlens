// Funzioni pure per Nodi, dettaglio e Rete (nessuna dipendenza dall'interfaccia).
import { num } from './format'
import type { SourceKind } from './ui/logic'
import type { Alert, Node } from './types'
import { alertLabel } from './alerts'

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

export const AGE_OPTIONS: { label: string; hours: number | null }[] = [
  { label: 'Tutti', hours: null },
  { label: '2 h', hours: 2 },
  { label: '24 h', hours: 24 },
  { label: '7 g', hours: 168 },
]

export const SOURCE_OPTIONS: { label: string; value: string }[] = [
  { label: 'Radio', value: 'rf' },
  { label: 'MQTT', value: 'mqtt' },
]

/** Aggiunge o toglie `v` senza modificare l'elenco. */
export function toggleIn<T>(list: T[], v: T): T[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v]
}

/** Avviso in italiano per una riga della Rete: «Batteria al 12%» / «Silenzioso da 30 h». */
export function alertText(a: Pick<Alert, 'kind' | 'value' | 'detail'>): string {
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
  if (typeof hops === 'number') return hops === 0 ? '0 (diretto)' : String(hops)
  if (typeof hopsMin === 'number' && hopsMin >= 1) return `≥ ${hopsMin}`
  return '—'
}

/** Nodi da mostrare in Rete: «solo miei» e «solo preferiti» si combinano in AND. */
export function networkNodes<T extends Pick<Node, 'is_mine' | 'is_favorite'>>(nodes: T[], onlyMine: boolean, onlyFav: boolean): T[] {
  return nodes.filter((n) => (!onlyMine || !!n.is_mine) && (!onlyFav || !!n.is_favorite))
}
