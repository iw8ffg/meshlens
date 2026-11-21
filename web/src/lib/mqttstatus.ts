import { ago, num } from './format'
import type { MqttStatus } from './types'

export type MqttTone = 'ok' | 'warn' | 'ko' | 'wait'
export interface MqttSummary {
  tone: MqttTone
  title: string
  rows: { label: string; value: string }[]
}

export const DROP_LABELS: Record<string, string> = {
  empty: 'vuoti',
  unsupported_port: 'tipo non gestito',
  undecodable: 'non decifrabili',
  json_topic: 'formato JSON',
  not_protobuf: 'non protobuf',
}

/** Oltre questa quiete un broker connesso viene segnalato come sospetto. */
const QUIET_WARN_S = 120

function mins(seconds: number): string {
  return `${Math.max(1, Math.round(seconds / 60))} min`
}

/** `now` in secondi epoch, come i tempi del server. */
export function mqttSummary(s: MqttStatus | null, now: number): MqttSummary {
  if (!s) return { tone: 'wait', title: 'In attesa dello stato MQTT', rows: [] }
  const age = s.last_msg_age_s ?? null
  let tone: MqttTone
  let title: string
  if (!s.connected) {
    tone = 'ko'
    title = 'Non connesso'
  } else if (age !== null && age >= QUIET_WARN_S) {
    tone = 'warn'
    title = `Connesso, nessun messaggio da ${mins(age)}`
  } else {
    tone = 'ok'
    title = 'Connesso'
  }
  const rows: { label: string; value: string }[] = []
  const since = (t: number) => ago(Math.max(0, (now - t) / 60))
  if (s.connected && s.connected_since != null) rows.push({ label: 'Connesso da', value: since(s.connected_since) })
  if (age !== null) rows.push({ label: 'Ultimo messaggio', value: ago(age / 60) })
  rows.push({ label: 'Messaggi al secondo', value: num(s.msgs_per_s, 1) })
  if (s.decoded) rows.push({ label: 'Messaggi decifrati', value: num(s.decoded) })
  if (s.reconnects) rows.push({ label: 'Ricollegamenti', value: num(s.reconnects) })
  if (s.watchdog_restarts) rows.push({ label: 'Riavvii automatici', value: num(s.watchdog_restarts) })
  if (s.last_error && tone !== 'ok') {
    rows.push({ label: 'Ultimo errore', value: s.last_error })
    if (s.last_error_at != null) rows.push({ label: 'Errore rilevato', value: since(s.last_error_at) })
  }
  for (const [k, n] of Object.entries(s.drops ?? {})) {
    if (n && n > 0) rows.push({ label: `Scartati: ${DROP_LABELS[k] ?? k}`, value: num(n) })
  }
  if (s.filtered_channel) rows.push({ label: 'Scartati: canale non ascoltato', value: num(s.filtered_channel) })
  if (s.queue_dropped) rows.push({ label: 'Persi per sovraccarico', value: num(s.queue_dropped) })
  return { tone, title, rows }
}
