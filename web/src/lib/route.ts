// Route nell'hash dell'indirizzo: #/<scheda> oppure #/nodes/!xxxxxxxx (link diretto a un nodo).
import type { Tab } from './shell/nav'

export type Route = { tab: Tab | null; nodeId: string | null }

/** Schede raggiungibili dall'hash: tutte tranne «Altro», che è solo un menu del telefono. */
export const ROUTE_TABS: readonly Tab[] = ['map', 'nodes', 'network', 'coverage', 'chat', 'radio', 'settings']

const NONE: Route = { tab: null, nodeId: null }
const NODE_ID = /^!?[0-9a-fA-F]{8}$/

export function isRouteTab(t: unknown): t is Tab {
  return typeof t === 'string' && (ROUTE_TABS as readonly string[]).includes(t)
}

export function parseHash(hash: string): Route {
  const parts = hash.replace(/^#\/?/, '').split('/')
  if (parts.length === 1 && isRouteTab(parts[0])) return { tab: parts[0], nodeId: null }
  if (parts.length === 2 && parts[0] === 'nodes' && NODE_ID.test(parts[1])) {
    return { tab: 'nodes', nodeId: '!' + parts[1].replace(/^!/, '').toLowerCase() }
  }
  return { ...NONE }
}

/** Il nodo vince sulla scheda; senza scheda né nodo la stringa è vuota. */
export function formatHash(r: Route): string {
  if (r.nodeId) return `#/nodes/${r.nodeId}`
  return r.tab ? `#/${r.tab}` : ''
}

export function nodeLink(id: string, loc: Pick<Location, 'origin' | 'pathname'>): string {
  return `${loc.origin}${loc.pathname}#/nodes/${id}`
}
