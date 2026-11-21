import type { Node } from './types'

export type SortKey =
  | 'name'
  | 'last_heard'
  | 'role'
  | 'firmware'
  | 'battery'
  | 'voltage'
  | 'snr'
  | 'hops'
  | 'channel_util'
  | 'air_util_tx'

function value(n: Node, key: SortKey): string | number | null {
  switch (key) {
    case 'name':
      return n.long_name || n.short_name || n.id
    case 'snr':
      return n.last_snr
    default:
      return n[key]
  }
}

/** Ordina senza modificare l'input; i valori null restano sempre in fondo. */
export function sortNodes(nodes: Node[], key: SortKey, dir: 'asc' | 'desc'): Node[] {
  const sign = dir === 'asc' ? 1 : -1
  return [...nodes].sort((a, b) => {
    const va = value(a, key)
    const vb = value(b, key)
    if (va === null && vb === null) return 0
    if (va === null) return 1
    if (vb === null) return -1
    if (typeof va === 'string' && typeof vb === 'string') return sign * va.localeCompare(vb)
    return sign * ((va as number) - (vb as number))
  })
}

/** 101 = alimentazione esterna. */
export function batteryLabel(b: number | null): string {
  if (b === null) return '—'
  return b === 101 ? 'USB' : `${b}%`
}
