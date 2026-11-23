// Bot e webhook (E15): tipi locali di WP5, validazioni per l'interfaccia e chiamate alle rotte
// dedicate. Il bot si accende solo con POST /api/bot/enable (opt-in con conferma, da questo PC);
// le altre impostazioni passano da PUT /settings.
import { getJSON, send } from './api'
import { t, locale, type MsgKey } from './i18n/index.svelte'
import type { BotCommand, BotTarget, WebhookEvent } from './settings'
import type { BotStatus, Radio } from './types'

export interface BotState extends BotStatus {
  dropped?: Record<string, number>
}

export interface BotInfo {
  status: BotState
  commands: BotCommand[]
}

export interface BotPreview {
  command: BotCommand | null
  trigger?: string | null
  reply: string | null
  sample: boolean
}

export interface WebhookResult {
  ok: boolean
  time: number
  code: string
}

export interface WebhookStatus {
  enabled: boolean
  configured: boolean
  events: WebhookEvent[]
  last: WebhookResult | null
}

export const BOT_COMMANDS: readonly BotCommand[] = ['ping', 'info', 'nodes', 'time', 'weather']
export const WEBHOOK_EVENTS: readonly WebhookEvent[] = ['message', 'alert', 'sensor', 'traceroute', 'node_new']
export const MAX_BOT_TARGETS = 16
export const MAX_BOT_REPLIES = 20
/** Il server aggiunge "[bot] " (6 byte) e taglia a 200: il testo scelto resta entro 195 byte. */
export const REPLY_MAX_BYTES = 195
export const LIMITS = {
  bot_min_interval_s: [15, 3600],
  bot_max_per_hour: [1, 120],
  bot_node_cooldown_s: [30, 86400],
} as const

const encoder = new TextEncoder()

export function utf8Bytes(s: string): number {
  return encoder.encode(s).length
}

// eslint-disable-next-line no-control-regex
const CONTROL = /[\u0000-\u001f\u007f]/

export function validateTrigger(s: string, existing: string[] = []): MsgKey | null {
  if (s.trim() !== s) return 'bot.err.triggerSpaces'
  const len = [...s].length
  if (len < 2 || len > 32) return 'bot.err.triggerLength'
  if (CONTROL.test(s)) return 'bot.err.replyControl'
  const folded = s.toLocaleLowerCase()
  if (existing.some((e) => e.toLocaleLowerCase() === folded)) return 'bot.err.triggerDup'
  return null
}

export function validateReplyText(s: string): MsgKey | null {
  if (CONTROL.test(s)) return 'bot.err.replyControl'
  const n = utf8Bytes(s)
  if (s.trim() === '' || n < 1 || n > REPLY_MAX_BYTES) return 'bot.err.replyLength'
  return null
}

export function validateLimit(key: keyof typeof LIMITS, v: number | null | undefined): boolean {
  const [lo, hi] = LIMITS[key]
  return typeof v === 'number' && Number.isInteger(v) && v >= lo && v <= hi
}

export function targetKey(tg: BotTarget): string {
  return tg.kind === 'radio' ? `radio:${tg.radio_id}:${tg.channel_index}` : `mqtt:${tg.broker}:${tg.channel}`
}

export function sameTarget(a: BotTarget, b: BotTarget): boolean {
  return targetKey(a) === targetKey(b)
}

export function targetLabel(tg: BotTarget, radios: Pick<Radio, 'id' | 'name' | 'channels'>[],
  brokers: { id: string; name: string }[]): string {
  if (tg.kind === 'radio') {
    const r = radios.find((x) => x.id === tg.radio_id)
    const ch = r?.channels.find((c) => c.index === tg.channel_index)
    const chName = ch?.name ? ch.name : t('bot.channelIndex', { n: tg.channel_index })
    return `${r?.name ?? tg.radio_id} · ${chName}`
  }
  const b = brokers.find((x) => x.id === tg.broker)
  return `${b?.name ?? tg.broker} · ${tg.channel}`
}

export interface EnableState {
  targets: BotTarget[]
  confirmedBrokers: string[]
}

/** Il bot si puo' attivare: almeno un bersaglio, ogni broker MQTT gia' confermato. */
export function canEnable(state: EnableState): { ok: boolean; reason: MsgKey | null } {
  if (state.targets.length === 0) return { ok: false, reason: 'bot.enable.noTarget' }
  if (state.targets.some((tg) => tg.kind === 'mqtt' && !state.confirmedBrokers.includes(tg.broker)))
    return { ok: false, reason: 'bot.enable.brokerNotConfirmed' }
  return { ok: true, reason: null }
}

const ERROR_KEYS: Record<string, MsgKey> = {
  duty_cycle_limit: 'bot.err.duty_cycle_limit',
  rate_limit_exceeded: 'bot.err.rate_limit_exceeded',
  send_failed: 'bot.err.send_failed',
  radio_not_connected: 'bot.err.radio_not_connected',
  mqtt_disconnected: 'bot.err.mqtt_disconnected',
  broker_not_confirmed: 'bot.err.broker_not_confirmed',
  busy: 'bot.err.busy',
  invalid: 'bot.err.invalid',
}

export function errorKey(code: string | null | undefined): MsgKey {
  return code && Object.hasOwn(ERROR_KEYS, code) ? ERROR_KEYS[code] : 'bot.err.generic'
}

/** «In pausa fino alle 14:32», vuoto se la pausa e' finita o non c'e'. */
export function pausedLabel(until: number | null | undefined, now: number): string {
  if (until == null || until <= now) return ''
  const time = new Date(until * 1000).toLocaleTimeString(locale(), { hour: '2-digit', minute: '2-digit' })
  return t('bot.pausedUntil', { time })
}

const WEBHOOK_CODES: Record<string, MsgKey> = {
  ok: 'bot.webhook.code.ok',
  timeout: 'bot.webhook.code.timeout',
  connection_refused: 'bot.webhook.code.connection_refused',
  dns: 'bot.webhook.code.dns',
  tls: 'bot.webhook.code.tls',
  redirect: 'bot.webhook.code.redirect',
  invalid_url: 'bot.webhook.code.invalid_url',
  error: 'bot.webhook.code.error',
}

export function webhookCodeLabel(code: string): string {
  const http = /^http_(\d{3})$/.exec(code)
  if (http) return t('bot.webhook.code.http', { n: http[1] })
  return t(Object.hasOwn(WEBHOOK_CODES, code) ? WEBHOOK_CODES[code] : 'bot.webhook.code.error')
}

/** Questa pagina e' aperta da questo PC (l'attivazione del bot e del webhook lo richiede). */
export function isLoopbackHost(hostname: string): boolean {
  return ['localhost', '127.0.0.1', '[::1]', '::1'].includes(hostname)
}

export const botInfo = () => getJSON<BotInfo>('/bot')
export const enableBot = (enabled: boolean) =>
  send<{ status: BotState }>('POST', '/bot/enable', enabled ? { enabled: true, confirm: true } : { enabled: false })
export const previewBot = (text: string) => send<BotPreview>('POST', '/bot/preview', { text })
export const webhookStatus = () => getJSON<WebhookStatus>('/webhook')
export const enableWebhook = (enabled: boolean) => send<WebhookStatus>('POST', '/webhook/enable', { enabled })
export const testWebhook = () => send<{ ok: boolean; code: string }>('POST', '/webhook/test', {})
