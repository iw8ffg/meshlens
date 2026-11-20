import type { Message, MessageStatus, Radio } from './types'

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
      return 'In invio'
    case 'sent':
      return 'Inviato'
    case 'acked':
      return 'Consegnato'
    case 'failed':
      return 'Non consegnato'
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
