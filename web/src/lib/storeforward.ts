import { getJSON, send } from './api'
import { t } from './i18n/index.svelte'
import { translateServer } from './i18n/server'

export interface SfStats {
  messages_total?: number
  messages_saved: number
  messages_max: number
  return_max: number
  return_window: number
  [k: string]: unknown
}

export interface SfRouter {
  id: string
  name: string | null
  radio_id: string
  last_seen: number
  heartbeat_period: number | null
  secondary: boolean
  stats: SfStats | null
  last_request: number | null
}

export type SfStatus = 'waiting' | 'receiving' | 'done' | 'failed'

export interface SfJob {
  id: string
  radio_id: string
  router_id: string
  window_min: number
  channel_index: number
  status: SfStatus
  expected: number | null
  received: number
  duplicates: number
  error: string | null
  started: number
  ended: number | null
}

export interface SfRequestBody {
  radio_id: string
  router_id: string
  window_min: number
  channel_index: number
}

export type SfProbeBody = Omit<SfRequestBody, 'window_min'>

export const WINDOW_OPTIONS = [
  { min: 60, get label() { return t('sf.window.60') } },
  { min: 240, get label() { return t('sf.window.240') } },
  { min: 720, get label() { return t('sf.window.720') } },
  { min: 1440, get label() { return t('sf.window.1440') } },
]
export const DEFAULT_WINDOW_MIN = 240

/** Nomi dei canali preset del firmware: usati da tutti, quindi pubblici. */
const PRESET_NAMES = new Set([
  'LongFast', 'MediumFast', 'MediumSlow', 'ShortFast', 'ShortSlow', 'LongModerate', 'LongSlow', 'ShortTurbo',
])

interface ChannelLike {
  index: number
  name?: string
  role: string
}

/** Il primo canale secondario (di solito quello privato), altrimenti 0. */
export function defaultChannel(channels: ChannelLike[]): number {
  return channels.find((c) => c.role === 'SECONDARY')?.index ?? 0
}

/** Canale primario col nome di un preset (o senza nome): i router lo rifiutano. */
export function isLikelyPublic(ch: ChannelLike): boolean {
  if (ch.role !== 'PRIMARY') return false
  const name = (ch.name ?? '').trim()
  return name === '' || PRESET_NAMES.has(name)
}

export function jobText(job: SfJob): string {
  switch (job.status) {
    case 'waiting':
      return t('sf.job.waiting')
    case 'receiving': {
      const base = job.expected != null ? t('sf.job.receivedOf', { n: job.received, total: job.expected }) : t('sf.job.received', { n: job.received })
      return job.duplicates > 0 ? t('sf.job.dup', { base, d: job.duplicates }) : base
    }
    case 'done': {
      if (job.received === 0 && job.duplicates === 0) return t('sf.job.none')
      const base = t('sf.job.done', { n: job.received })
      return job.duplicates > 0 ? t('sf.job.dup', { base, d: job.duplicates }) : base
    }
    case 'failed':
      return translateServer(job.error ?? '')
  }
}

export const sfRouters = () => getJSON<SfRouter[]>('/storeforward/routers')
export const sfRequest = (body: SfRequestBody) => send<SfJob>('POST', '/storeforward/request', body)
export const sfProbe = (body: SfProbeBody) => send<Record<string, never>>('POST', '/storeforward/probe', body)
export const sfJobs = () => getJSON<SfJob[]>('/storeforward/jobs')
