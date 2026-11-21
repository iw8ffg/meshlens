// Compositore unico «Invia via»: radio o MQTT (funzioni pure).
import { MAX_BYTES, MQTT_CONV, byteLength, splitKey, statusLabel } from './chat'
import type { Message, MessageStatus, Radio } from './types'

export const DEFAULT_MQTT_CHANNEL = 'LongFast'
export const MQTT_VIA = 'mqtt'
/** Testo della conferma alla prima pubblicazione MQTT (identico a quello del server). */
export const PUBLIC_WARNING =
  'Il messaggio sarà pubblico sul broker mqtt.meshtastic.org e potrà essere ritrasmesso via radio dai gateway'
export const NO_RADIO_REASON = 'Collega una radio'
export const MQTT_DOWN_REASON = 'MQTT non connesso'
export const MQTT_NODE_REASON = 'Imposta il tuo id nodo in Impostazioni → MQTT'

export const radioVia = (radioId: string): string => `radio:${radioId}`
export const viaRadioId = (via: string): string => (via.startsWith('radio:') ? via.slice(6) : '')

/** Contatore in byte UTF-8 (non caratteri: «è» pesa 2 byte). */
export function byteCount(text: string, max = MAX_BYTES): { bytes: number; max: number; over: boolean; remaining: number } {
  const bytes = byteLength(text)
  return { bytes, max, over: bytes > max, remaining: max - bytes }
}

export interface ViaOption {
  value: string
  label: string
  disabled: boolean
  /** Perche' e' disattivata (mostrato accanto all'opzione). */
  reason: string | null
}

export interface ViaInput {
  radios: Radio[]
  mqttConnected: boolean
  /** Impostazione mqtt_node_id (!hex) o stringa vuota. */
  mqttNodeId: string
  /** Il server ha risposto unknown_node. */
  unknownNode: boolean
  /** Nome del canale con cui la radio invierebbe (mostrato tra parentesi). */
  radioChannelName?: (r: Radio) => string | undefined
  /** Canale MQTT scelto (predefinito LongFast). */
  mqttChannel?: string
}

const NODE_ID = /^![0-9a-f]{8}$/i

/** Opzioni di «Invia via»: ogni radio e MQTT; le non disponibili restano in elenco, disattivate, col motivo. */
export function viaOptions(i: ViaInput): ViaOption[] {
  const out: ViaOption[] = []
  if (i.radios.length === 0) {
    out.push({ value: 'radio:', label: 'Radio', disabled: true, reason: NO_RADIO_REASON })
  }
  for (const r of i.radios) {
    const ok = r.state === 'connected'
    const ch = i.radioChannelName?.(r)
    out.push({ value: radioVia(r.id), label: ch ? `Radio «${r.name}» (${ch})` : `Radio «${r.name}»`, disabled: !ok, reason: ok ? null : NO_RADIO_REASON })
  }
  const identity = NODE_ID.test(i.mqttNodeId) || i.radios.some((r) => r.state === 'connected' && !!r.my_node_id)
  let reason: string | null = null
  if (!i.mqttConnected) reason = MQTT_DOWN_REASON
  else if (!identity || i.unknownNode) reason = MQTT_NODE_REASON
  out.push({ value: MQTT_VIA, label: `MQTT (${i.mqttChannel || DEFAULT_MQTT_CHANNEL})`, disabled: reason !== null, reason })
  return out
}

/**
 * Scelta di «Invia via»: resta quella dell'utente finche' e' disponibile e la conversazione non cambia;
 * altrimenti la radio della conversazione (o MQTT per il pubblico) se disponibile, poi la prima disponibile.
 */
export function pickVia(current: string, conv: string, options: ViaOption[], convChanged: boolean): string {
  const enabled = (v: string) => options.some((o) => o.value === v && !o.disabled)
  if (!convChanged && current && enabled(current)) return current
  const preferred = conv === MQTT_CONV ? MQTT_VIA : radioVia(splitKey(conv)[1])
  if (enabled(preferred)) return preferred
  return options.find((o) => !o.disabled)?.value ?? ''
}

/** Nomi dei canali per l'invio MQTT: LongFast per primo, poi quelli visti sul broker. */
export function mqttChannelNames(rows: { name: string }[]): string[] {
  const names = new Set<string>([DEFAULT_MQTT_CHANNEL])
  for (const r of rows) if (r.name) names.add(r.name)
  return [...names]
}

/**
 * Canale della radio scelta: resta quello dell'utente se esiste ancora e la scelta non e' cambiata;
 * altrimenti quello omonimo al canale della conversazione, altrimenti il primo.
 */
export function pickRadioChannel(conv: string, radios: Radio[], radioId: string, current: number, changed: boolean): number {
  const chans = radios.find((r) => r.id === radioId)?.channels ?? []
  if (chans.length === 0) return 0
  if (!changed && chans.some((c) => c.index === current)) return current
  const [kind, rid, rest] = splitKey(conv)
  if (kind === 'ch') {
    const name = radios.find((r) => r.id === rid)?.channels.find((c) => String(c.index) === rest)?.name
    const same = chans.find((c) => c.name === name)
    if (same) return same.index
  }
  return chans.some((c) => c.index === 0) ? 0 : chans[0].index
}

export interface MqttSendBody {
  text: string
  channel: string
  to?: string
  confirm_public?: boolean
}

export function mqttBody(text: string, channel: string, to: string | null, confirmPublic: boolean): MqttSendBody {
  return { text: text.trim(), channel, ...(to ? { to } : {}), ...(confirmPublic ? { confirm_public: true } : {}) }
}

export type MqttErrorKind = 'confirm' | 'unknown_node' | 'disconnected' | 'rate_limited' | 'other'

/** Interpreta la risposta d'errore di POST /api/mqtt/send (409 conferma, 400 nodo, 429 limite, 503 MQTT). */
export function classifyMqttError(e: { status: number; code: string | null; message: string; retryAfter?: number | null }): {
  kind: MqttErrorKind
  message: string
} {
  if (e.status === 409 && e.code === 'confirm_required') return { kind: 'confirm', message: PUBLIC_WARNING }
  if (e.code === 'unknown_node') return { kind: 'unknown_node', message: MQTT_NODE_REASON }
  if (e.status === 503 || e.code === 'mqtt_disconnected') return { kind: 'disconnected', message: MQTT_DOWN_REASON }
  if (e.status === 429 || e.code === 'rate_limited') {
    const msg = /attendi/i.test(e.message) ? e.message : e.retryAfter ? `Attendi ${e.retryAfter} s` : 'Troppi messaggi: riprova tra poco'
    return { kind: 'rate_limited', message: msg }
  }
  return { kind: 'other', message: e.message || 'Invio non riuscito' }
}

/** Dopo la conferma dell'utente si rimanda lo stesso messaggio con confirm_public: true. */
export function resendBody(pending: MqttSendBody): MqttSendBody {
  return { ...pending, confirm_public: true }
}

/** Etichetta accessibile dello stato: «Inviato · via MQTT». */
export function statusAria(status: MessageStatus | null | undefined, via: Message['via']): string {
  const s = statusLabel(status)
  if (!s) return via === 'mqtt' ? 'via MQTT' : ''
  return via === 'mqtt' ? `${s} · via MQTT` : s
}
