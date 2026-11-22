import type { Message, MessageStatus, Radio } from './types'
import { t } from './i18n/index.svelte'

export const MAX_BYTES = 200
export const BROADCAST = '!ffffffff'
export const MQTT_CONV = 'mqtt'

/** Lunghezza in byte UTF-8 (limite del payload Meshtastic). */
export function byteLength(text: string): number {
  return new TextEncoder().encode(text).length
}

/** `ch:<radio>:<indice>` per i canali, `dm:<radio>:<altro nodo>` per i diretti, `mqtt` senza radio. */
export function conversationKey(msg: Message, localIds: Set<string>): string {
  if (!msg.radio_id) return MQTT_CONV
  if (msg.to === BROADCAST) return `ch:${msg.radio_id}:${msg.channel_index ?? 0}`
  const outgoing = msg.direction === 'out' || localIds.has(msg.from)
  return `dm:${msg.radio_id}:${outgoing ? msg.to : msg.from}`
}

/** Messaggi radio raggruppati per conversazione, ciascun gruppo dal piu' vecchio al piu' recente. */
export function groupMessages(msgs: Message[], localIds: Set<string>): Map<string, Message[]> {
  const out = new Map<string, Message[]>()
  for (const m of msgs) {
    if (!m.radio_id) continue
    const k = conversationKey(m, localIds)
    const list = out.get(k)
    if (list) list.push(m)
    else out.set(k, [m])
  }
  for (const list of out.values()) list.sort((a, b) => a.time - b.time)
  return out
}

/** Id dei nodi che sono radio collegate. */
export function localNodeIds(radios: Radio[]): Set<string> {
  return new Set(radios.map((r) => r.my_node_id).filter((x): x is string => !!x))
}

export function statusIcon(status: MessageStatus | null | undefined): string {
  switch (status) {
    case 'sending':
      return '⏳'
    case 'sent':
      return '✓'
    case 'acked':
      return '✓✓'
    case 'failed':
      return '⚠'
    default:
      return ''
  }
}

export function statusLabel(status: MessageStatus | null | undefined): string {
  switch (status) {
    case 'sending':
      return t('chat.status.sending')
    case 'sent':
      return t('chat.status.sent')
    case 'acked':
      return t('chat.status.acked')
    case 'failed':
      return t('chat.status.failed')
    default:
      return ''
  }
}

/**
 * Inserisce un messaggio nella lista: ignora i duplicati, sostituisce il provvisorio indicato da
 * `replaces` e ricorda in `replaced` le chiavi sostituite (la risposta HTTP puo' arrivare dopo il WS).
 */
export function insertMessage(list: Message[], m: Message, replaced: Set<string>): void {
  if (replaced.has(m.key)) return
  if (m.replaces) {
    replaced.add(m.replaces)
    const i = list.findIndex((x) => x.key === m.replaces)
    if (i >= 0) list.splice(i, 1)
  }
  if (list.some((x) => x.key === m.key)) return
  list.push(m)
}

/**
 * Radio di invio: la scelta manuale resta finche' la radio e' connessa e la conversazione non cambia;
 * altrimenti la radio della conversazione (se connessa) oppure la prima connessa.
 */
export function pickSendRadio(current: string, convRadio: string, connectedIds: string[], convChanged: boolean): string {
  if (!convChanged && current && connectedIds.includes(current)) return current
  return connectedIds.includes(convRadio) ? convRadio : (connectedIds[0] ?? '')
}

// "dm:r1:!abcd" -> ['dm', 'r1', '!abcd']
export function splitKey(key: string): [string, string, string] {
  const a = key.indexOf(':')
  const b = key.indexOf(':', a + 1)
  return [key.slice(0, a), key.slice(a + 1, b), key.slice(b + 1)]
}

export interface SendTarget {
  radio: Radio
  index: number
}

/**
 * Radio che possono inviare nella conversazione: per un canale `ch:A:i` solo le radio connesse con un
 * canale dello stesso nome (e il loro indice); per i diretti qualunque radio connessa.
 */
export function sendTargets(radios: Radio[], conv: string): SendTarget[] {
  const connected = radios.filter((r) => r.state === 'connected')
  const [kind, rid, rest] = splitKey(conv)
  if (kind !== 'ch') return connected.map((radio) => ({ radio, index: 0 }))
  const name = radios.find((r) => r.id === rid)?.channels.find((c) => String(c.index) === rest)?.name
  if (name === undefined) return []
  const out: SendTarget[] = []
  for (const radio of connected) {
    const ch = radio.channels.find((c) => c.name === name)
    if (ch) out.push({ radio, index: ch.index })
  }
  return out
}

export const MAX_RADIO_MESSAGES = 2000
export const MAX_REPLACED = 500

/** Tiene solo gli ultimi `max` elementi inseriti in un Set (ordine di inserimento). */
export function pruneSet<T>(set: Set<T>, max: number): void {
  for (const v of set) {
    if (set.size <= max) break
    set.delete(v)
  }
}

/** Rimuove da `list` la copia con la stessa chiave (arrivata prima senza radio_id, es. dal feed MQTT). */
export function removeByKey(list: Message[], key: string): boolean {
  const i = list.findIndex((x) => x.key === key)
  if (i < 0) return false
  list.splice(i, 1)
  return true
}

/**
 * Unisce messaggi radio (live o storici) nella lista: dedup, `replaces`, ordine per tempo crescente,
 * conserva solo i `max` piu' recenti.
 */
export function mergeRadioMessages(list: Message[], incoming: Message[], replaced: Set<string>, max = MAX_RADIO_MESSAGES): void {
  for (const m of incoming) insertMessage(list, m, replaced)
  pruneSet(replaced, MAX_REPLACED)
  list.sort((a, b) => a.time - b.time)
  if (list.length > max) list.splice(0, list.length - max)
}

/** Destinatario di una reazione via MQTT: a un diretto si risponde a chi lo ha scritto
 *  (o al suo destinatario, se e' mio), mai in broadcast; altrimenti vale la conversazione aperta. */
export function reactionDest(target: Pick<Message, 'from' | 'to' | 'direction'>, dmTo: string | null): string | null {
  if (!target.to || target.to === BROADCAST) return dmTo
  return target.direction === 'out' ? target.to : target.from
}
