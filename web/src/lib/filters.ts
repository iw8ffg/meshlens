import type { Node } from './types'

export type NodeFilter = {
  countries: string[]
  maxAgeH: number | null
  sources: string[]
  text: string
}

export function matchNode(n: Node, f: NodeFilter, now: number): boolean {
  if (f.countries.length > 0) {
    const key = n.country ?? 'none'
    if (!f.countries.includes(key)) return false
  }
  if (f.maxAgeH !== null && now - n.last_heard > f.maxAgeH * 3600) return false
  if (f.sources.length > 0 && !n.sources.some((s) => f.sources.includes(s))) return false
  const t = f.text.trim().toLowerCase()
  if (t) {
    const hay = [n.long_name, n.short_name, n.id].map((s) => (s ?? '').toLowerCase())
    if (!hay.some((s) => s.includes(t))) return false
  }
  return true
}

export function ageClass(lastHeard: number, now: number): 'fresh' | 'recent' | 'old' {
  const age = now - lastHeard
  if (age < 2 * 3600) return 'fresh'
  if (age < 24 * 3600) return 'recent'
  return 'old'
}

export const FILTER_KEY = 'meshlens.filter'

type FilterStorage = Pick<Storage, 'getItem' | 'setItem'>

const defaultFilter = (): NodeFilter => ({ countries: ['IT'], maxAgeH: null, sources: [], text: '' })

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
    }
  } catch {
    return defaultFilter()
  }
}

export function saveFilter(storage: FilterStorage, f: NodeFilter): void {
  try {
    storage.setItem(FILTER_KEY, JSON.stringify({ countries: [...f.countries], maxAgeH: f.maxAgeH, text: f.text }))
  } catch {
    // storage non disponibile: ignora
  }
}
