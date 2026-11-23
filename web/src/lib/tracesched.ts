// Traceroute periodici (E14): tipi locali di WP5, calcoli puri e chiamate alle rotte
// /api/trace-targets. Il server applica i limiti (minimo 1 ora per nodo, 1 per giro).
import { getJSON, send } from './api'
import { t, type MsgKey } from './i18n/index.svelte'
import type { TraceTarget, Traceroute } from './types'

export interface TraceHistoryItem extends Traceroute {
  route_changed: boolean
  prev_route: string | null
}

export interface TraceTargetsResponse {
  enabled: boolean
  max_per_hour: number
  targets: TraceTarget[]
}

export interface TraceTargetBody {
  enabled?: boolean
  interval_min: number
  radio_id?: string | null
}

export const MIN_INTERVAL_MIN = 60
export const MAX_INTERVAL_MIN = 10080
export const INTERVAL_OPTIONS = [60, 180, 360, 720, 1440] as const
export const HISTORY_PAGE = 20
export const MAX_PER_HOUR_RANGE = [1, 30] as const

/** Intervallo in minuti, intero, fra 60 e 10080 (7 giorni). */
export function clampInterval(n: number): number {
  if (!Number.isFinite(n)) return MIN_INTERVAL_MIN
  return Math.min(MAX_INTERVAL_MIN, Math.max(MIN_INTERVAL_MIN, Math.floor(n)))
}

/** Moltiplicatore dopo errori consecutivi (come il server). */
export function failureMultiplier(failCount: number): number {
  return failCount < 3 ? 1 : failCount < 6 ? 2 : 4
}

/** Prossimo traceroute previsto (epoch s) o null se non e' mai partito. */
export function nextRunAt(target: Pick<TraceTarget, 'last_run' | 'interval_min' | 'fail_count'>): number | null {
  if (target.last_run == null) return null
  return target.last_run + target.interval_min * 60 * failureMultiplier(target.fail_count ?? 0)
}

const STATUS_KEYS: Record<string, MsgKey> = {
  pending: 'tracesched.status.pending',
  ok: 'tracesched.status.ok',
  failed: 'tracesched.status.failed',
  timeout: 'tracesched.status.timeout',
  throttled: 'tracesched.status.throttled',
  busy: 'tracesched.status.busy',
  no_radio: 'tracesched.status.no_radio',
}

export function statusKey(status: string | null | undefined): MsgKey {
  if (status == null) return 'tracesched.status.never'
  return Object.hasOwn(STATUS_KEYS, status) ? STATUS_KEYS[status] : 'tracesched.status.unknown'
}

function hops(route: string | null | undefined): string[] {
  return (route ?? '').split('>').filter((h) => h !== '')
}

/** Salti aggiunti e tolti fra due percorsi (id uniti da ">", "" = diretto). */
export function diffRoute(prevRoute: string, curRoute: string): { added: string[]; removed: string[] } {
  const prev = hops(prevRoute)
  const cur = hops(curRoute)
  return { added: cur.filter((h) => !prev.includes(h)), removed: prev.filter((h) => !cur.includes(h)) }
}

/** Percorso leggibile: nomi dei salti, oppure «diretto». */
export function routeLabel(route: string | null | undefined, nameOf: (id: string) => string): string {
  const list = hops(route)
  if (list.length === 0) return t('tracesched.direct')
  return list.map(nameOf).join(' → ')
}

export function intervalLabel(min: number): string {
  if (min % 1440 === 0) return t('tracesched.everyDays', { n: min / 1440 })
  if (min % 60 === 0) return t('tracesched.everyHours', { n: min / 60 })
  return t('tracesched.everyMinutes', { n: min })
}

const path = (id: string) => `/trace-targets/${encodeURIComponent(id)}`

export const listTargets = () => getJSON<TraceTargetsResponse>('/trace-targets')
export const saveTarget = (id: string, body: TraceTargetBody) => send<TraceTarget>('PUT', path(id), body)
export const removeTarget = (id: string) => send<{ ok: boolean }>('DELETE', path(id), {})
export const setAutoTraceroutes = (enabled: boolean) =>
  send<TraceTargetsResponse>('POST', '/trace-targets/enable', { enabled })
export function loadHistory(id: string, before?: number): Promise<TraceHistoryItem[]> {
  const q = `limit=${HISTORY_PAGE}${before != null ? `&before=${before}` : ''}`
  return getJSON<TraceHistoryItem[]>(`${path(id)}/history?${q}`)
}
