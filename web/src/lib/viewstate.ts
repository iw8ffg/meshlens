// Vista ricordata tra un'apertura e l'altra (localStorage `meshlens.view`, versione 1).
import type { SortKey } from './network'
import type { NodeSortKey } from './nodesort'
import { NODE_SORTS } from './nodesort'
import type { Tab } from './shell/nav'
import { isRouteTab } from './route'

export const VIEW_KEY = 'meshlens.view'

export type NetView = 'nodes' | 'stats' | 'packets' | 'health' | 'topology'
/** health/topology sono valori validi da salvare; se la vista non e' pronta NetworkPage ricade su nodes. */
const NET_VIEWS: readonly NetView[] = ['nodes', 'stats', 'packets', 'health', 'topology']

export type ViewState = {
  tab: Tab | null
  map: { lon: number; lat: number; zoom: number } | null
  conv: string | null
  netSort: { key: SortKey; dir: 'asc' | 'desc' } | null
  nodeSort: NodeSortKey
  cluster: boolean
  waypoints: boolean
  netView: NetView
}

const SORT_KEYS: readonly SortKey[] = [
  'name',
  'last_heard',
  'role',
  'firmware',
  'battery',
  'voltage',
  'snr',
  'hops',
  'channel_util',
  'air_util_tx',
]

function defaults(): ViewState {
  return { tab: null, map: null, conv: null, netSort: null, nodeSort: 'recent', cluster: true, waypoints: true, netView: 'nodes' }
}

const inRange = (x: unknown, lim: number, min = -lim): x is number =>
  typeof x === 'number' && Number.isFinite(x) && x >= min && x <= lim

function parseMap(m: unknown): ViewState['map'] {
  if (!m || typeof m !== 'object') return null
  const { lon, lat, zoom } = m as Record<string, unknown>
  if (!inRange(lon, 180) || !inRange(lat, 85) || !inRange(zoom, 22, 0)) return null
  return { lon, lat, zoom }
}

function parseNetSort(s: unknown): ViewState['netSort'] {
  if (!s || typeof s !== 'object') return null
  const { key, dir } = s as Record<string, unknown>
  if (!SORT_KEYS.includes(key as SortKey) || (dir !== 'asc' && dir !== 'desc')) return null
  return { key: key as SortKey, dir }
}

function readRaw(storage: Pick<Storage, 'getItem'> | null): Record<string, unknown> | null {
  try {
    const raw = storage?.getItem(VIEW_KEY)
    if (raw == null) return null
    const o: unknown = JSON.parse(raw)
    return o && typeof o === 'object' && !Array.isArray(o) ? (o as Record<string, unknown>) : null
  } catch {
    return null
  }
}

/** Legge la vista; ogni campo non valido torna al predefinito, uno per uno. */
export function loadView(storage: Pick<Storage, 'getItem'> | null): ViewState {
  const v = defaults()
  const o = readRaw(storage)
  if (!o || o.v !== 1) return v
  if (isRouteTab(o.tab)) v.tab = o.tab
  v.map = parseMap(o.map)
  if (typeof o.conv === 'string' && o.conv !== '') v.conv = o.conv
  v.netSort = parseNetSort(o.netSort)
  if (NODE_SORTS.some((s) => s.key === o.nodeSort)) v.nodeSort = o.nodeSort as NodeSortKey
  if (typeof o.cluster === 'boolean') v.cluster = o.cluster
  if (typeof o.waypoints === 'boolean') v.waypoints = o.waypoints
  if (NET_VIEWS.includes(o.netView as NetView)) v.netView = o.netView as NetView
  return v
}

/** Unisce `patch` alla vista salvata; gli errori di storage si ignorano. */
export function saveView(storage: Pick<Storage, 'getItem' | 'setItem'> | null, patch: Partial<ViewState>): void {
  try {
    if (!storage) return
    storage.setItem(VIEW_KEY, JSON.stringify({ ...loadView(storage), ...patch, v: 1 }))
  } catch {
    // localStorage pieno o non disponibile: la vista vale solo per questa sessione
  }
}
