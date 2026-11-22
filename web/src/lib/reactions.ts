// Risposte e reazioni: raggruppamento dei messaggi di una conversazione e testi d'errore (funzioni pure).
import { it as itCatalog } from './i18n/it'
import { t, type MsgKey } from './i18n/index.svelte'
import type { Message, Node } from './types'

export const REACTIONS = ['👍', '❤️', '😂', '😮', '😢', '🙏'] as const

export interface ReactionChip {
  emoji: string
  count: number
  names: string[]
  mine: boolean
}

export interface ThreadItem {
  msg: Message
  /** Messaggio a cui questo risponde, se e' nella lista. */
  replyTo: Message | null
  /** Risponde a un messaggio che non e' nella lista. */
  replyMissing: boolean
  reactions: ReactionChip[]
  /** Reazione il cui bersaglio non e' nella lista: si mostra come riga compatta. */
  orphan: boolean
}

const isReaction = (m: Message) => !!m.emoji && m.reply_id != null

type Acc = ReactionChip & { senders: Set<string> }

/**
 * Raggruppa le reazioni sul messaggio bersaglio (stessa lista, `packet_id === reply_id`).
 * L'ordine dei messaggi in ingresso si conserva; le chip seguono l'ordine di arrivo delle reazioni.
 * Un nodo che ripete la stessa emoji conta una volta.
 */
export function threadItems(msgs: Message[], nodeName: (id: string) => string, localIds: Set<string>): ThreadItem[] {
  const byPacket = new Map<number, Message>()
  for (const m of msgs) if (m.packet_id != null && !isReaction(m)) byPacket.set(m.packet_id, m)

  const chips = new Map<number, Map<string, Acc>>()
  const arrival = msgs.filter(isReaction).sort((a, b) => a.time - b.time)
  for (const r of arrival) {
    const target = byPacket.get(r.reply_id as number)
    if (!target || target.packet_id == null) continue
    let perEmoji = chips.get(target.packet_id)
    if (!perEmoji) chips.set(target.packet_id, (perEmoji = new Map()))
    let chip = perEmoji.get(r.text)
    if (!chip) perEmoji.set(r.text, (chip = { emoji: r.text, count: 0, names: [], mine: false, senders: new Set() }))
    if (chip.senders.has(r.from)) continue
    chip.senders.add(r.from)
    chip.count++
    chip.names.push(nodeName(r.from))
    if (r.direction === 'out' || localIds.has(r.from)) chip.mine = true
  }

  const out: ThreadItem[] = []
  for (const m of msgs) {
    if (isReaction(m)) {
      if (!byPacket.has(m.reply_id as number)) out.push({ msg: m, replyTo: null, replyMissing: false, reactions: [], orphan: true })
      continue
    }
    const replyTo = m.reply_id != null ? (byPacket.get(m.reply_id) ?? null) : null
    const mine = m.packet_id != null ? [...(chips.get(m.packet_id)?.values() ?? [])] : []
    const reactions = mine.map(({ emoji, count, names, mine: me }) => ({ emoji, count, names, mine: me }))
    out.push({ msg: m, replyTo, replyMissing: m.reply_id != null && !replyTo, reactions, orphan: false })
  }
  return out
}

/** Motivo di un recapito fallito, nella lingua corrente; un codice ignoto mostra il codice. */
export function routingErrorText(code: string | null | undefined): string {
  if (!code) return t('chat.routingErrorUnknown', { code: '?' })
  const key = `chat.routing.${code}`
  return Object.hasOwn(itCatalog, key) ? t(key as MsgKey) : t('chat.routingErrorUnknown', { code })
}

const KEY_CHANGED_WINDOW_S = 7 * 86400

/** Vero se la chiave pubblica del nodo e' cambiata negli ultimi 7 giorni. */
export function keyChangedRecently(node: Node | undefined, nowS: number): boolean {
  const changed = node?.key_changed
  return changed != null && nowS - changed <= KEY_CHANGED_WINDOW_S
}
