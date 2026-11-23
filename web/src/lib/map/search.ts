// Ricerca di un nodo sulla mappa: senza maiuscole né accenti, solo nodi con posizione.
import type { Node } from '../types'
import { isIgnored } from '../filters'

const norm = (s: string | null | undefined): string =>
  (s ?? '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()

function score(n: Node, q: string, qid: string): number {
  const id = norm(n.id)
  const short = norm(n.short_name)
  const long = norm(n.long_name)
  if (id === qid || id === `!${qid}`) return 0
  if (short.startsWith(q)) return 1
  if (long.startsWith(q)) return 2
  if (long.includes(q) || short.includes(q)) return 3
  if ([id, norm(n.hw_model), norm(n.role)].some((s) => s.includes(q))) return 4
  return -1
}

export function searchNodes(nodes: Iterable<Node>, q: string, limit = 8): Node[] {
  const query = norm(q.trim())
  if (!query) return []
  const qid = query.replace(/^!/, '')
  const hits: { n: Node; s: number }[] = []
  for (const n of nodes) {
    if (n.lat === null || n.lon === null || isIgnored(n)) continue
    const s = score(n, query, qid)
    if (s >= 0) hits.push({ n, s })
  }
  hits.sort((a, b) => a.s - b.s || (b.n.last_heard ?? 0) - (a.n.last_heard ?? 0))
  return hits.slice(0, limit).map((h) => h.n)
}
