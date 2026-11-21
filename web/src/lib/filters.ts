import type { Node } from './types'

export type NodeFilter = {
  countries: string[]
  maxAgeH: number | null
  sources: string[]
  text: string
  links: boolean
  /** Solo nodi preferiti. */
  favorites?: boolean
}

export function matchNode(n: Node, f: NodeFilter, now: number): boolean {
  if (f.countries.length > 0) {
    const key = n.country ?? 'none'
    if (!f.countries.includes(key)) return false
  }
  if (f.maxAgeH !== null && (n.last_heard === null || now - n.last_heard > f.maxAgeH * 3600)) return false
  if (f.favorites && !n.is_favorite) return false
  if (f.sources.length > 0 && !n.sources.some((s) => f.sources.includes(s))) return false
  const t = f.text.trim().toLowerCase()
  if (t) {
    const hay = [n.long_name, n.short_name, n.id].map((s) => (s ?? '').toLowerCase())
    if (!hay.some((s) => s.includes(t))) return false
  }
  return true
}

export function ageClass(lastHeard: number | null, now: number): 'fresh' | 'recent' | 'old' {
  if (lastHeard === null) return 'old'
  const age = now - lastHeard
  if (age < 2 * 3600) return 'fresh'
  if (age < 24 * 3600) return 'recent'
  return 'old'
}

export const FILTER_KEY = 'meshlens.filter'

type FilterStorage = Pick<Storage, 'getItem' | 'setItem'>

const defaultFilter = (): NodeFilter => ({ countries: ['IT'], maxAgeH: null, sources: [], text: '', links: false, favorites: false })

// Ripristina il filtro salvato (default: solo Italia)
export function loadFilter(storage: FilterStorage): NodeFilter {
  try {
    const saved = JSON.parse(storage.getItem(FILTER_KEY) ?? 'null')
    const d = defaultFilter()
    return {
      countries: Array.isArray(saved?.countries) ? saved.countries.filter((c: unknown) => typeof c === 'string') : d.countries,
      maxAgeH: typeof saved?.maxAgeH === 'number' ? saved.maxAgeH : null,
      sources: [],
      text: typeof saved?.text === 'string' ? saved.text : '',
      links: saved?.links === true,
      favorites: saved?.favorites === true,
    }
  } catch {
    return defaultFilter()
  }
}

export function saveFilter(storage: FilterStorage, f: NodeFilter): void {
  try {
    storage.setItem(FILTER_KEY, JSON.stringify({ countries: [...f.countries], maxAgeH: f.maxAgeH, text: f.text, links: f.links, favorites: !!f.favorites }))
  } catch {
    // storage non disponibile: ignora
  }
}

// ---- filtro del feed dei messaggi MQTT (indipendente da quello della mappa) ----
export type FeedFilter = {
  /** Vuoto = tutte le nazioni. */
  countries: string[]
  /** Mostra anche i mittenti senza nazione (mai inviata una posizione). */
  includeUnknown: boolean
}

export const FEED_FILTER_KEY = 'meshlens.feedfilter'

const defaultFeedFilter = (): FeedFilter => ({ countries: [], includeUnknown: true })

export function matchFeed(country: string | null, f: FeedFilter): boolean {
  if (country === null) return f.includeUnknown
  return f.countries.length === 0 || f.countries.includes(country)
}

export function countFeedHidden(messages: { country: string | null }[], f: FeedFilter): number {
  return messages.filter((m) => !matchFeed(m.country, f)).length
}

// Ripristina il filtro del feed (default: tutto); tollera dati assenti o malformati
export function loadFeedFilter(storage: FilterStorage): FeedFilter {
  try {
    const saved = JSON.parse(storage.getItem(FEED_FILTER_KEY) ?? 'null')
    return {
      countries: Array.isArray(saved?.countries) ? saved.countries.filter((c: unknown) => typeof c === 'string') : [],
      includeUnknown: typeof saved?.includeUnknown === 'boolean' ? saved.includeUnknown : true,
    }
  } catch {
    return defaultFeedFilter()
  }
}

export function saveFeedFilter(storage: FilterStorage, f: FeedFilter): void {
  try {
    storage.setItem(FEED_FILTER_KEY, JSON.stringify({ countries: [...f.countries], includeUnknown: f.includeUnknown }))
  } catch {
    // storage non disponibile: ignora
  }
}
