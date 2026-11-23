// Ricerca nel testo dei messaggi (WP1: E2/E4): client dell'API e funzioni di supporto per i componenti.
import { getJSON } from './api'
import { MQTT_CONV, mqttConvKey } from './chat'
import type { ConvExportFormat } from './export'
import { addMqttHistory, addRadioHistory } from './stores.svelte'
import type { Message, MessageSearchHit, MessageSearchResult } from './types'

/** Marcatori di inizio/fine corrispondenza negli snippet del server. */
export const SNIP_OPEN = '\x02'
export const SNIP_CLOSE = '\x03'

export interface NodeHit {
  id: string
  long_name: string | null
  short_name: string | null
  hw_model: string | null
  last_heard: number | null
  is_mine: boolean
  is_favorite: boolean
}

export interface GlobalSearchResult {
  nodes: NodeHit[]
  messages: MessageSearchHit[]
  engine: string
}

/**
 * Segmenti di uno snippet: i tratti tra i marcatori sono `hit`. Mai HTML: i componenti rendono i
 * segmenti con `<mark>` e testo semplice. Marcatori sbilanciati non lanciano errori.
 */
export function snippetParts(snippet: string | null): { text: string; hit: boolean }[] {
  if (!snippet) return []
  const out: { text: string; hit: boolean }[] = []
  let hit = false
  let buf = ''
  const flush = () => {
    if (buf) out.push({ text: buf, hit })
    buf = ''
  }
  for (const ch of snippet) {
    if (ch === SNIP_OPEN) {
      flush()
      hit = true
    } else if (ch === SNIP_CLOSE) {
      flush()
      hit = false
    } else buf += ch
  }
  flush()
  return out
}

export interface SearchParams {
  q: string
  conv?: string | null
  sender?: string | null
  since?: number | null
  until?: number | null
  cursor?: string | null
  limit?: number
}

/** Percorso (senza `/api`) della ricerca; i parametri vuoti si omettono. */
export function searchPath(p: SearchParams): string {
  const parts = [`q=${encodeURIComponent(p.q)}`]
  const add = (k: string, v: string | number | null | undefined) => {
    if (v !== null && v !== undefined && v !== '') parts.push(`${k}=${encodeURIComponent(String(v))}`)
  }
  add('conv', p.conv)
  add('sender', p.sender)
  add('since', p.since)
  add('until', p.until)
  add('cursor', p.cursor)
  add('limit', p.limit)
  return `/messages/search?${parts.join('&')}`
}

export const searchMessages = (p: SearchParams) => getJSON<MessageSearchResult>(searchPath(p))

export const globalSearch = (q: string, limit?: number) =>
  getJSON<GlobalSearchResult>(`/search?q=${encodeURIComponent(q)}${limit ? `&limit=${limit}` : ''}`)

/** Chiave di conversazione di un risultato: quella del server, altrimenti il pubblico MQTT (del broker, se noto). */
export function hitConvKey(hit: MessageSearchHit): string {
  if (hit.conv) return hit.conv
  return hit.message.broker ? mqttConvKey(hit.message.broker) : MQTT_CONV
}

export type PeriodKind = 'all' | 'day' | 'week' | 'month'
const PERIOD_SECONDS: Record<Exclude<PeriodKind, 'all'>, number> = { day: 86400, week: 7 * 86400, month: 30 * 86400 }

/** Intervallo `since`/`until` (secondi epoch) di un periodo che termina adesso (`now` in secondi). */
export function periodRange(kind: PeriodKind, now: number): { since: number | null; until: number | null } {
  if (kind === 'all') return { since: null, until: null }
  return { since: now - PERIOD_SECONDS[kind], until: null }
}

/**
 * Porta nello store il messaggio trovato e, per i messaggi radio, la pagina di storico che lo
 * precede, cosi' la conversazione lo mostra. Errori di rete ignorati: resta il solo messaggio.
 */
export async function loadHitContext(hit: MessageSearchHit): Promise<void> {
  const m = hit.message
  if (!m.radio_id) {
    addMqttHistory([m])
    return
  }
  addRadioHistory([m])
  try {
    const page = await getJSON<Message[]>(`/messages/radio?before=${Math.floor(m.time) + 1}&limit=50`)
    addRadioHistory(page)
  } catch {
    /* si prosegue col solo messaggio */
  }
}

/** Mittenti distinti dei risultati, ordinati per nome (selettore «mittente»). */
export function senderOptions(hits: MessageSearchHit[]): { id: string; name: string }[] {
  const seen = new Map<string, string>()
  for (const h of hits) if (!seen.has(h.message.from)) seen.set(h.message.from, h.message.from_name || h.message.from)
  return [...seen].map(([id, name]) => ({ id, name })).sort((a, b) => a.name.localeCompare(b.name))
}

/** Accoda una pagina di risultati senza duplicati (per chiave del messaggio). */
export function mergePages(prev: MessageSearchHit[], next: MessageSearchHit[]): MessageSearchHit[] {
  const keys = new Set(prev.map((h) => h.message.key))
  return [...prev, ...next.filter((h) => !keys.has(h.message.key))]
}

/** Tipo MIME del file esportato. */
export function exportMime(format: ConvExportFormat): string {
  return format === 'csv' ? 'text/csv' : format === 'json' ? 'application/json' : 'text/plain'
}
