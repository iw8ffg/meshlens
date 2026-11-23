import { MQTT_CONV, isMqttConv, mqttConvBroker, mqttConvKey, splitKey } from './chat'
import { locale, t } from './i18n/index.svelte'
import type { ConvSummary, Message, Radio } from './types'

export interface ConvItem {
  key: string
  label: string
  lastTime: number
  preview: string
  unread: number
  kind: 'mqtt' | 'ch' | 'dm'
}

const PREVIEW_MAX = 80

/** Etichetta di una conversazione: «Pubblico (MQTT)», «Radio · Canale» o «Radio · DM Nome». */
export function convLabel(
  key: string,
  radios: Radio[],
  nodeName: (id: string) => string,
  brokers: { id: string; name: string }[] = [],
): string {
  if (key === MQTT_CONV) return brokers.length > 1 ? t('chat.mqttAllBrokers') : t('chat.mqttConversation')
  const bid = mqttConvBroker(key)
  if (bid) return t('chat.mqttBrokerConversation', { broker: brokers.find((b) => b.id === bid)?.name || bid })
  const [kind, rid, rest] = splitKey(key)
  const radio = radios.find((r) => r.id === rid)
  const radioName = radio?.name ?? rid
  if (kind === 'ch') {
    const ch = radio?.channels.find((c) => String(c.index) === rest)
    return t('chat.channelConversation', { radio: radioName, channel: ch?.name || t('chat.channelFallback', { index: rest }) })
  }
  return t('chat.dmConversation', { radio: radioName, name: nodeName(rest) })
}

/** Un riepilogo del server come messaggio, per calcolarne l'anteprima. */
function summaryMessage(s: ConvSummary): Message {
  return {
    key: '', from: s.last_from, from_name: null, to: '', channel: '', text: s.last_text, time: s.last_time,
    country: null, source: '', emoji: s.last_emoji,
  }
}

/** `mqtt` per primo, poi le conversazioni radio dalla più recente; a parità per etichetta. */
export function buildConversations(args: {
  radios: Radio[]
  groups: Map<string, Message[]>
  summaries: Record<string, ConvSummary>
  counts: Record<string, number>
  label: (key: string) => string
  previewOf: (m: Message) => string
  /** Broker attivi: con piu' di uno, una conversazione pubblica per ciascuno dopo «tutti i broker» */
  brokers?: { id: string }[]
}): ConvItem[] {
  const { radios, groups, summaries, counts, label, previewOf, brokers = [] } = args
  const keys = new Set<string>()
  for (const r of radios) for (const c of r.channels) keys.add(`ch:${r.id}:${c.index}`)
  for (const k of groups.keys()) keys.add(k)
  for (const k of Object.keys(summaries)) keys.add(k)
  for (const k of [...keys]) if (isMqttConv(k)) keys.delete(k)

  const items: ConvItem[] = []
  for (const key of keys) {
    const list = groups.get(key)
    const local = list && list.length ? list[list.length - 1] : null
    const s = summaries[key]
    const last = s && s.last_time > (local?.time ?? 0) ? summaryMessage(s) : local
    items.push({
      key,
      label: label(key),
      lastTime: last?.time ?? 0,
      preview: last ? previewOf(last) : '',
      unread: counts[key] ?? 0,
      kind: splitKey(key)[0] === 'dm' ? 'dm' : 'ch',
    })
  }
  items.sort((a, b) => b.lastTime - a.lastTime || a.label.localeCompare(b.label, locale()))
  const mqttItem = (key: string): ConvItem => ({ key, label: label(key), lastTime: 0, preview: '', unread: counts[key] ?? 0, kind: 'mqtt' })
  const perBroker = brokers.length > 1 ? brokers.map((b) => mqttItem(mqttConvKey(b.id))) : []
  return [mqttItem(MQTT_CONV), ...perBroker, ...items]
}

/** Minuscole e senza accenti, per la ricerca. */
function fold(s: string): string {
  return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}

/** Filtra per etichetta, anteprima e testo dei messaggi caricati; la query vuota restituisce tutto. */
export function filterConversations(items: ConvItem[], query: string, groups: Map<string, Message[]>): ConvItem[] {
  const q = fold(query.trim())
  if (!q) return items
  return items.filter(
    (i) => fold(i.label).includes(q) || fold(i.preview).includes(q) || (groups.get(i.key) ?? []).some((m) => fold(m.text).includes(q)),
  )
}

function truncate(s: string): string {
  const chars = Array.from(s)
  return chars.length > PREVIEW_MAX ? chars.slice(0, PREVIEW_MAX).join('') + '…' : s
}

/** Anteprima dell'ultimo messaggio: «Tu: …» per i propri, frase dedicata per le reazioni, al massimo 80 caratteri. */
export function previewText(m: Message, nodeName: (id: string) => string, localIds: Set<string>): string {
  const own = m.direction === 'out' || localIds.has(m.from)
  const text = m.text.replace(/\s+/g, ' ').trim()
  if (m.emoji) return truncate(own ? t('chat.ownReactionPreview', { emoji: text }) : t('chat.reactionPreview', { name: nodeName(m.from), emoji: text }))
  return truncate(own ? t('chat.ownPreview', { text }) : text)
}
