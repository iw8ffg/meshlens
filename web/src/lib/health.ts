// Salute della rete (E11): ordinamento, confronto di 2–3 nodi e chiamata HTTP. Nessun testo letterale.
import { getJSON } from './api'
import { batterySeries, voltageSeries, type Pt } from './chart'
import type { MsgKey } from './i18n/index.svelte'
import { levelOf } from './autonomy'
import type { CompareMetric, HealthNode, HealthResponse, SnrPoint, TelemetryPoint } from './types'

export const COMPARE_MAX = 3
export const COMPARE_METRICS: CompareMetric[] = ['battery', 'voltage', 'channel_util', 'air_util_tx', 'snr']
export const COMPARE_COLORS: ('accent' | 'amber' | 'teal')[] = ['accent', 'amber', 'teal']

/** Aggiunge un id (al massimo COMPARE_MAX) o lo toglie se presente; non muta. */
export function toggleCompare(ids: string[], id: string): string[] {
  if (ids.includes(id)) return ids.filter((x) => x !== id)
  return ids.length >= COMPARE_MAX ? ids : [...ids, id]
}

function rank(n: HealthNode): number {
  if (n.status === 'falling') return 0
  if (n.status === 'solar' && n.solar_trend === 'falling') return 1
  if (n.status === 'solar' && n.solar_trend !== 'charging') return 2
  if (n.status === 'external' || n.status === 'insufficient') return 4
  return 3
}

/** In cima i nodi in calo (meno giorni prima), poi i solari in calo e stabili, poi il resto per livello
 * crescente; alimentazione esterna e dati insufficienti in fondo. A parità, per nome. */
export function sortHealth(nodes: HealthNode[]): HealthNode[] {
  const key = (n: HealthNode): number => {
    if (n.status === 'falling') return n.days_left ?? 0
    if (rank(n) === 3) return levelOf(n) ?? 101
    return 0
  }
  return [...nodes].sort((a, b) => rank(a) - rank(b) || key(a) - key(b) || a.name.localeCompare(b.name))
}

/** «Da tenere d'occhio» = in calo (anche solari); il resto negli altri. */
export function splitHealth(nodes: HealthNode[]): { attention: HealthNode[]; others: HealthNode[] } {
  const sorted = sortHealth(nodes)
  const isAttention = (n: HealthNode) => n.status === 'falling' || (n.status === 'solar' && n.solar_trend === 'falling')
  return { attention: sorted.filter(isAttention), others: sorted.filter((n) => !isAttention(n)) }
}

export function compareSeries(metric: CompareMetric, tel: TelemetryPoint[], snrPts: SnrPoint[]): Pt[] {
  switch (metric) {
    case 'battery':
      return batterySeries(tel)
    case 'voltage':
      return voltageSeries(tel)
    case 'channel_util':
      return tel.map((p) => ({ t: p.time, v: p.channel_util }))
    case 'air_util_tx':
      return tel.map((p) => ({ t: p.time, v: p.air_util_tx }))
    case 'snr':
      return snrPts.filter((p) => p.source === 'rf').map((p) => ({ t: p.time, v: p.snr_avg }))
  }
}

export function compareMeta(metric: CompareMetric): { unit: string; digits: number; labelKey: MsgKey; fixedRange?: [number, number] } {
  switch (metric) {
    case 'battery':
      return { unit: '%', digits: 0, labelKey: 'health.metric.battery', fixedRange: [0, 100] }
    case 'voltage':
      return { unit: 'V', digits: 2, labelKey: 'health.metric.voltage' }
    case 'channel_util':
      return { unit: '%', digits: 1, labelKey: 'health.metric.channel_util' }
    case 'air_util_tx':
      return { unit: '%', digits: 1, labelKey: 'health.metric.air_util_tx' }
    case 'snr':
      return { unit: 'dB', digits: 1, labelKey: 'health.metric.snr' }
  }
}

/** Estremi del tempo su tutte le serie (solo punti validi); [0, 1] se non ce ne sono. */
export function extentOf(series: Pt[][]): [number, number] {
  const ts = series.flatMap((l) => l.filter((p) => p.v !== null).map((p) => p.t))
  if (ts.length === 0) return [0, 1]
  return [Math.min(...ts), Math.max(...ts)]
}

export const healthBatteries = (scope: 'mine' | 'all') => getJSON<HealthResponse>(`/health/batteries?scope=${scope}`)
