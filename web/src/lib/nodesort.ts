// Ordinamento dell'elenco Nodi: recente, nome, SNR, salti, distanza.
import { haversineM, type Origin } from './distance'
import { compareLastHeard } from './format'
import { nodeName } from './nodes'
import type { Node } from './types'

export type NodeSortKey = 'recent' | 'name' | 'snr' | 'hops' | 'distance'

export const NODE_SORTS: { key: NodeSortKey; label: string }[] = [
  { key: 'recent', label: 'Recenti' },
  { key: 'name', label: 'Nome' },
  { key: 'snr', label: 'SNR' },
  { key: 'hops', label: 'Salti' },
  { key: 'distance', label: 'Distanza' },
]

/**
 * Ordina per un valore numerico calcolato una sola volta per nodo (decorate-sort-undecorate):
 * i mancanti vanno in fondo, a parità vale l'ultimo contatto.
 */
function byValue(nodes: Node[], value: (n: Node) => number | null, cmp: (x: number, y: number) => number): Node[] {
  const keyed = nodes.map((n) => ({ n, v: value(n) }))
  keyed.sort((a, b) => {
    const x = a.v
    const y = b.v
    if (x === null && y === null) return compareLastHeard(a.n.last_heard, b.n.last_heard)
    if (x === null) return 1
    if (y === null) return -1
    return cmp(x, y) || compareLastHeard(a.n.last_heard, b.n.last_heard)
  })
  return keyed.map((k) => k.n)
}

/** Restituisce una copia ordinata di `nodes`; senza origine la distanza equivale a «recente». */
export function sortNodeList(nodes: Node[], key: NodeSortKey, origin: Origin | null): Node[] {
  switch (key) {
    case 'name':
      return [...nodes].sort(
        (a, b) => nodeName(a).localeCompare(nodeName(b), 'it') || compareLastHeard(a.last_heard, b.last_heard),
      )
    case 'snr':
      return byValue(nodes, (n) => n.last_snr, (x, y) => y - x)
    case 'hops':
      return byValue(nodes, (n) => n.hops ?? n.hops_min ?? null, (x, y) => x - y)
    case 'distance':
      if (!origin) return sortNodeList(nodes, 'recent', null)
      return byValue(
        nodes,
        (n) => (n.lat !== null && n.lon !== null ? haversineM(origin, { lat: n.lat, lon: n.lon }) : null),
        (x, y) => x - y,
      )
    case 'recent':
      return [...nodes].sort((a, b) => compareLastHeard(a.last_heard, b.last_heard))
  }
}
