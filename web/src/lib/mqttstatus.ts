import { ago, num } from './format'
import type { MqttStatus } from './types'
import { t, type MsgKey } from './i18n/index.svelte'

export type MqttTone = 'ok' | 'warn' | 'ko' | 'wait'
export interface MqttSummary {
  tone: MqttTone
  title: string
  rows: { label: string; value: string }[]
}

export const DROP_KEYS: Record<string, MsgKey> = {
  empty: 'shell.mqttDropEmpty',
  unsupported_port: 'shell.mqttDropUnsupported',
  undecodable: 'shell.mqttDropUndecodable',
  json_topic: 'shell.mqttDropJson',
  not_protobuf: 'shell.mqttDropNotProtobuf',
}

/** Oltre questa quiete un broker connesso viene segnalato come sospetto. */
const QUIET_WARN_S = 120

function mins(seconds: number): string {
  return t('shell.mqttMin', { n: Math.max(1, Math.round(seconds / 60)) })
}

/** `now` in secondi epoch, come i tempi del server. */
export function mqttSummary(s: MqttStatus | null, now: number): MqttSummary {
  if (!s) return { tone: 'wait', title: t('shell.mqttWaiting'), rows: [] }
  const age = s.last_msg_age_s ?? null
  const active = (s.brokers ?? []).filter((b) => b.enabled)
  const up = active.filter((b) => b.connected).length
  let tone: MqttTone
  let title: string
  if (!s.connected || (active.length >= 2 && up === 0)) {
    tone = 'ko'
    title = t('shell.mqttNotConnected')
  } else if (active.length >= 2 && up < active.length) {
    tone = 'warn'
    title = t('shell.mqttConnectedTo', { up, total: active.length })
  } else if (age !== null && age >= QUIET_WARN_S) {
    tone = 'warn'
    title = t('shell.mqttQuiet', { mins: mins(age) })
  } else {
    tone = 'ok'
    title = t('shell.mqttConnected')
  }
  const rows: { label: string; value: string }[] = []
  const since = (t: number) => ago(Math.max(0, (now - t) / 60))
  if (s.connected && s.connected_since != null) rows.push({ label: t('shell.mqttConnectedSince'), value: since(s.connected_since) })
  if (age !== null) rows.push({ label: t('shell.mqttLastMessage'), value: ago(age / 60) })
  rows.push({ label: t('shell.mqttPerSecond'), value: num(s.msgs_per_s, 1) })
  if (s.decoded) rows.push({ label: t('shell.mqttDecoded'), value: num(s.decoded) })
  if (s.reconnects) rows.push({ label: t('shell.mqttReconnects'), value: num(s.reconnects) })
  if (s.watchdog_restarts) rows.push({ label: t('shell.mqttWatchdog'), value: num(s.watchdog_restarts) })
  if (s.last_error && tone !== 'ok') {
    rows.push({ label: t('shell.mqttLastError'), value: s.last_error })
    if (s.last_error_at != null) rows.push({ label: t('shell.mqttErrorAt'), value: since(s.last_error_at) })
  }
  for (const [k, n] of Object.entries(s.drops ?? {})) {
    if (n && n > 0) rows.push({ label: t('shell.mqttDropped', { why: DROP_KEYS[k] ? t(DROP_KEYS[k]) : k }), value: num(n) })
  }
  if (s.filtered_channel) rows.push({ label: t('shell.mqttDropChannel'), value: num(s.filtered_channel) })
  if (s.queue_dropped) rows.push({ label: t('shell.mqttOverload'), value: num(s.queue_dropped) })
  return { tone, title, rows }
}

export interface BrokerRow {
  id: string
  name: string
  tone: MqttTone
  detail: string
}

/** Una riga per broker: prima gli attivi, poi i disattivati. Vuoto con un server che non invia `brokers`. */
export function brokerRows(s: MqttStatus | null, _now: number): BrokerRow[] {
  const list = s?.brokers ?? []
  const active: BrokerRow[] = list
    .filter((b) => b.enabled)
    .map((b) => ({
      id: b.id,
      name: b.name,
      tone: b.connected ? 'ok' : 'ko',
      detail: b.connected ? `${num(b.msgs_per_s, 1)} msg/s` : (b.last_error || t('shell.mqttNotConnected')),
    }))
  const off: BrokerRow[] = list
    .filter((b) => !b.enabled)
    .map((b) => ({ id: b.id, name: b.name, tone: 'wait', detail: t('shell.brokerOff') }))
  return [...active, ...off]
}
