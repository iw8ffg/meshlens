import { getJSON, send } from './api'

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
  { min: 60, label: '1 ora' },
  { min: 240, label: '4 ore' },
  { min: 720, label: '12 ore' },
  { min: 1440, label: '24 ore' },
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
      return 'In attesa del router…'
    case 'receiving': {
      const base = job.expected != null ? `Ricevuti ${job.received} di ${job.expected}` : `Ricevuti ${job.received}`
      return job.duplicates > 0 ? `${base}, ${job.duplicates} già presenti` : base
    }
    case 'done': {
      if (job.received === 0 && job.duplicates === 0) return 'Nessun messaggio da recuperare'
      const base = `Completato: ${job.received} messaggi recuperati`
      return job.duplicates > 0 ? `${base}, ${job.duplicates} già presenti` : base
    }
    case 'failed':
      return job.error ?? ''
  }
}

export const sfRouters = () => getJSON<SfRouter[]>('/storeforward/routers')
export const sfRequest = (body: SfRequestBody) => send<SfJob>('POST', '/storeforward/request', body)
export const sfProbe = (body: SfProbeBody) => send<Record<string, never>>('POST', '/storeforward/probe', body)
export const sfJobs = () => getJSON<SfJob[]>('/storeforward/jobs')
