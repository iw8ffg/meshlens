import { conversationKey } from './chat'
import { markConversationRead } from './api'
import type { ConvSummary, Message } from './types'

/** Non letti per conversazione e ultimo istante letto (secondi epoch). */
export const unread = $state({ counts: {} as Record<string, number>, reads: {} as Record<string, number> })

// Conversazione aperta: variabile semplice, non reattiva (la legge solo l'handler dei messaggi).
let activeConv: string | null = null

export function setActiveConv(key: string | null): void {
  activeConv = key
}

export function getActiveConv(): string | null {
  return activeConv
}

export function applySummaries(list: ConvSummary[]): void {
  const counts: Record<string, number> = {}
  const reads: Record<string, number> = {}
  for (const s of list) {
    counts[s.key] = s.unread
    reads[s.key] = s.read_time
  }
  unread.counts = counts
  unread.reads = reads
}

/** Conta un messaggio in arrivo; restituisce la chiave contata, o null se non conta. */
export function noteIncoming(m: Message, localIds: Set<string>, active: string | null, visible: boolean): string | null {
  if (m.direction === 'out' || m.emoji || localIds.has(m.from) || !m.radio_id) return null
  const key = conversationKey(m, localIds)
  if (visible && active === key) return null
  if (m.time <= (unread.reads[key] ?? 0)) return null
  unread.counts[key] = (unread.counts[key] ?? 0) + 1
  return key
}

export function applyRead(key: string, time: number): void {
  unread.counts[key] = 0
  if (time > (unread.reads[key] ?? 0)) unread.reads[key] = time
}

export async function markRead(key: string, time: number): Promise<void> {
  applyRead(key, time)
  try {
    await markConversationRead(key, time)
  } catch {
    /* il server si riallinea al prossimo caricamento */
  }
}

export function totalUnread(counts: Record<string, number>): number {
  let n = 0
  for (const v of Object.values(counts)) n += v
  return n
}
