// Ispettore dei pacchetti: filtri, interrogazione e testi.
import type { Node } from './types'

export type PacketFilters = {
  node: string
  kind: string
  source: '' | 'rf' | 'mqtt'
  status: string
  /** Un `<input type="number">` con bind:value dà numero o null (vuoto). */
  minSnr: number | null
  period: '1h' | '6h' | '24h' | 'all'
}

export const PAGE_SIZE = 100

const PERIOD_HOURS: Record<PacketFilters['period'], number | null> = { '1h': 1, '6h': 6, '24h': 24, all: null }

export const STATUS_LABEL: Record<string, string> = {
  ok: 'Decodificato',
  encrypted: 'Cifrato',
  unsupported: 'Tipo non gestito',
  undecodable: 'Non decodificabile',
  empty: 'Vuoto',
}

/** Parametri della richiesta: i campi vuoti si omettono; `nodeId` è il nodo già risolto. */
export function packetQuery(f: PacketFilters, now: number, beforeId: number | null, nodeId: string | null, afterId: number | null = null): string {
  const q = new URLSearchParams()
  if (nodeId) q.set('node', nodeId)
  if (f.kind) q.set('kind', f.kind)
  if (f.source) q.set('source', f.source)
  if (f.status) q.set('status', f.status)
  if (typeof f.minSnr === 'number' && Number.isFinite(f.minSnr)) q.set('min_snr', String(f.minSnr))
  const h = PERIOD_HOURS[f.period]
  if (h !== null) q.set('since', String(Math.floor(now - h * 3600)))
  if (beforeId !== null) q.set('before_id', String(beforeId))
  if (afterId !== null) q.set('after_id', String(afterId))
  q.set('limit', String(PAGE_SIZE))
  return q.toString()
}

const HEX8 = /^[0-9a-f]{8}$/i

/** Id nodo da un testo: `!xxxxxxxx`, otto cifre esadecimali, nome breve o parte del nome lungo. */
export function resolveNode(text: string, nodes: Iterable<Node>): string | null {
  const t = text.trim()
  if (t === '') return null
  const bare = t.startsWith('!') ? t.slice(1) : t
  if (HEX8.test(bare)) return `!${bare.toLowerCase()}`
  const low = t.toLowerCase()
  for (const n of nodes) {
    if (n.short_name?.toLowerCase() === low) return n.id
    if (n.long_name && n.long_name.toLowerCase().includes(low)) return n.id
  }
  return null
}

/** Righe di `width` byte: scostamento, byte esadecimali e ASCII stampabile («·» per gli altri). */
export function hexDump(hex: string, width = 16): { offset: string; hex: string; ascii: string }[] {
  const bytes: number[] = []
  for (let i = 0; i + 1 < hex.length; i += 2) {
    const b = parseInt(hex.slice(i, i + 2), 16)
    if (Number.isNaN(b)) break
    bytes.push(b)
  }
  const rows: { offset: string; hex: string; ascii: string }[] = []
  for (let o = 0; o < bytes.length; o += width) {
    const chunk = bytes.slice(o, o + width)
    rows.push({
      offset: o.toString(16).padStart(4, '0'),
      hex: chunk.map((b) => b.toString(16).padStart(2, '0')).join(' '),
      ascii: chunk.map((b) => (b >= 0x20 && b <= 0x7e ? String.fromCharCode(b) : '·')).join(''),
    })
  }
  return rows
}

/** Nodi il cui ultimo byte dell'id coincide con il ritrasmettitore; 0 o assente = nessuno. */
export function relayCandidates(relay: number | null, nodes: Iterable<Node>): Node[] {
  if (relay === null || relay === 0) return []
  return [...nodes].filter((n) => (n.num & 0xff) === relay)
}

export function hopsText(p: { hops: number | null; hop_start: number | null; hop_limit: number | null }): string {
  if (p.hops !== null) return p.hops === 1 ? '1 salto' : `${p.hops} salti`
  if (p.hop_start !== null) return `partito con ${p.hop_start}, rimasti ${p.hop_limit ?? '–'}`
  return '–'
}
