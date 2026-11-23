// Ricerca globale Ctrl+K (WP1: E2): logica pura. Azioni, nodi, conversazioni, impostazioni; i
// messaggi arrivano dal server (`msgsearch.ts`) e li aggiunge il componente.
import { buildConversations, convLabel, previewText } from './conversations'
import { groupMessages, localNodeIds } from './chat'
import { visibleNodes } from './filters'
import type { MsgKey } from './i18n/index.svelte'
import type { ConvSummary, Message, Node, Radio } from './types'

/** Minuscole e senza diacritici: «Perché CITTÀ» → «perche citta». */
export function normalize(s: string): string {
  return s.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLowerCase()
}

export type ResultGroup = 'action' | 'node' | 'conversation' | 'setting' | 'message'

export interface SearchResult {
  group: ResultGroup
  id: string
  title: string
  subtitle?: string
  snippet?: string | null
  run: () => void
}

export type NodeLike = Pick<Node, 'id' | 'long_name' | 'short_name' | 'is_ignored'>

/** Massimo di risultati per gruppo e ordine dei gruppi. */
export const GROUP_LIMITS: { group: Exclude<ResultGroup, 'message'>; limit: number }[] = [
  { group: 'action', limit: 4 },
  { group: 'node', limit: 8 },
  { group: 'conversation', limit: 5 },
  { group: 'setting', limit: 4 },
]

/** Sezioni della scheda Impostazioni: la voce apre la scheda (non scorre alla sezione). */
export const SETTINGS_ENTRIES: { id: string; titleKey: MsgKey }[] = [
  { id: 'alerts', titleKey: 'settings.alerts.title' },
  { id: 'net', titleKey: 'settings.net.title' },
  { id: 'mqtt', titleKey: 'settings.mqtt.title' },
  { id: 'chan', titleKey: 'settings.chan.title' },
  { id: 'dev', titleKey: 'settings.dev.title' },
  { id: 'diag', titleKey: 'settings.diag.title' },
  { id: 'db', titleKey: 'settings.db.title' },
  { id: 'about', titleKey: 'settings.about.title' },
]

/** Voci delle impostazioni pronte per `rankLocal`: «Impostazioni › Sezione». */
export function settingsItems(label: (key: MsgKey) => string, prefix: string): { id: string; title: string }[] {
  return SETTINGS_ENTRIES.map((e) => ({ id: e.id, title: `${prefix} › ${label(e.titleKey)}` }))
}

/**
 * Punteggio di corrispondenza di `q` (gia' normalizzata) con i campi: 0 = un campo inizia con la
 * query o una sua parola, 1 = la contiene altrove, null = nessuna corrispondenza.
 */
function score(q: string, fields: (string | null | undefined)[]): number | null {
  let best: number | null = null
  for (const f of fields) {
    if (!f) continue
    const n = normalize(f)
    const i = n.indexOf(q)
    if (i < 0) continue
    const s = i === 0 || /[\s›·\-_:(]/.test(n[i - 1]) ? 0 : 1
    if (best === null || s < best) best = s
    if (best === 0) break
  }
  return best
}

export interface RankSource {
  nodes: NodeLike[]
  conversations: { key: string; label: string }[]
  settings: { id: string; title: string }[]
  actions: { id: string; title: string; run: () => void }[]
}

export interface RankHandlers {
  node: (id: string) => void
  conversation: (key: string) => void
  setting: (id: string) => void
}

function pick<T>(items: { item: T; s: number }[], limit: number): T[] {
  return items
    .map((x, i) => ({ ...x, i }))
    .sort((a, b) => a.s - b.s || a.i - b.i)
    .slice(0, limit)
    .map((x) => x.item)
}

/**
 * Risultati locali (istantanei) per la query. Query vuota: solo le azioni. I nodi ignorati non
 * compaiono mai. Corrispondenza per sottostringa normalizzata, prima quelle a inizio parola.
 */
export function rankLocal(q: string, src: RankSource, on: Partial<RankHandlers> = {}): SearchResult[] {
  const nq = normalize(q.trim())
  const lim = (g: ResultGroup) => GROUP_LIMITS.find((x) => x.group === g)?.limit ?? 0
  const out: SearchResult[] = []

  const actions = src.actions.map((a) => ({ item: a, s: nq ? score(nq, [a.title]) : 0 })).filter((x): x is { item: RankSource['actions'][number]; s: number } => x.s !== null)
  for (const a of pick(actions, lim('action'))) out.push({ group: 'action', id: a.id, title: a.title, run: a.run })
  if (!nq) return out

  const nodeQ = nq.replace(/^!/, '')
  const nodes = visibleNodes(src.nodes)
    .map((n) => {
      const idbare = n.id.replace(/^!/, '')
      const s = score(nq, [n.long_name, n.short_name]) ?? (nodeQ.length >= 2 ? score(nodeQ, [idbare]) : null)
      return { item: n, s }
    })
    .filter((x): x is { item: NodeLike; s: number } => x.s !== null)
  for (const n of pick(nodes, lim('node'))) {
    out.push({ group: 'node', id: n.id, title: n.long_name || n.short_name || n.id, subtitle: n.short_name && n.long_name ? `${n.short_name} · ${n.id}` : n.id, run: () => on.node?.(n.id) })
  }

  const convs = src.conversations.map((c) => ({ item: c, s: score(nq, [c.label]) })).filter((x): x is { item: { key: string; label: string }; s: number } => x.s !== null)
  for (const c of pick(convs, lim('conversation'))) out.push({ group: 'conversation', id: c.key, title: c.label, run: () => on.conversation?.(c.key) })

  const sets = src.settings.map((c) => ({ item: c, s: score(nq, [c.title]) })).filter((x): x is { item: { id: string; title: string }; s: number } => x.s !== null)
  for (const c of pick(sets, lim('setting'))) out.push({ group: 'setting', id: c.id, title: c.title, run: () => on.setting?.(c.id) })
  return out
}

/** Unisce i nodi locali con quelli del server senza duplicati (locali per primi); gli id in `ignored` si scartano. */
export function mergeNodeHits<T extends { id: string }>(local: T[], remote: T[], ignored: ReadonlySet<string> = new Set()): T[] {
  const seen = new Set(local.map((n) => n.id))
  return [...local, ...remote.filter((n) => !seen.has(n.id) && !ignored.has(n.id))]
}

/** Indice attivo dopo uno spostamento con le frecce (circolare); `-1` senza risultati. */
export function moveActive(index: number, delta: number, count: number): number {
  if (count <= 0) return -1
  if (index < 0) return delta >= 0 ? 0 : count - 1
  return (((index + delta) % count) + count) % count
}

/** Conversazioni cercabili: stesso calcolo e stesse etichette dell'elenco della chat. */
export function searchableConversations(i: {
  radios: Radio[]
  radioMessages: Message[]
  summaries: Record<string, ConvSummary>
  counts: Record<string, number>
  nodes: { get(id: string): Pick<Node, 'long_name' | 'short_name'> | undefined }
  brokers: { id: string; name: string }[]
}): { key: string; label: string }[] {
  const localIds = localNodeIds(i.radios)
  const nodeName = (id: string) => i.nodes.get(id)?.long_name || i.nodes.get(id)?.short_name || id
  return buildConversations({
    radios: i.radios,
    groups: groupMessages(i.radioMessages, localIds),
    summaries: i.summaries,
    counts: i.counts,
    label: (k) => convLabel(k, i.radios, nodeName, i.brokers),
    previewOf: (m) => previewText(m, nodeName, localIds),
    brokers: i.brokers,
  }).map((c) => ({ key: c.key, label: c.label }))
}
