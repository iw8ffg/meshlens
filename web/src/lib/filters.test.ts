import { test, expect } from 'vitest'
import { matchNode, ageClass, loadFilter, saveFilter, FILTER_KEY } from './filters'
import type { Node } from './types'

const now = 1_000_000
const n = { id: '!a1b2c3d4', long_name: 'Base Milano', short_name: 'BM', country: 'IT', last_heard: now - 3600, sources: ['mqtt'] } as Node

test('country filter', () => {
  expect(matchNode(n, { countries: ['IT'], maxAgeH: null, sources: [], text: '', links: false }, now)).toBe(true)
  expect(matchNode(n, { countries: ['FR'], maxAgeH: null, sources: [], text: '', links: false }, now)).toBe(false)
  expect(matchNode({ ...n, country: null }, { countries: ['none'], maxAgeH: null, sources: [], text: '', links: false }, now)).toBe(true)
})

test('age and text', () => {
  expect(matchNode(n, { countries: [], maxAgeH: 0.5, sources: [], text: '', links: false }, now)).toBe(false)
  expect(matchNode(n, { countries: [], maxAgeH: null, sources: [], text: 'milano', links: false }, now)).toBe(true)
  expect(ageClass(now - 3600, now)).toBe('fresh')
  expect(ageClass(now - 3 * 3600, now)).toBe('recent')
  expect(ageClass(now - 25 * 3600, now)).toBe('old')
})

test('sources and null names', () => {
  expect(matchNode(n, { countries: [], maxAgeH: null, sources: ['rf'], text: '', links: false }, now)).toBe(false)
  expect(matchNode(n, { countries: [], maxAgeH: null, sources: ['rf', 'mqtt'], text: '', links: false }, now)).toBe(true)
  const bare = { ...n, long_name: null, short_name: null } as Node
  expect(matchNode(bare, { countries: [], maxAgeH: null, sources: [], text: 'A1B2', links: false }, now)).toBe(true)
  expect(matchNode(bare, { countries: [], maxAgeH: null, sources: [], text: 'zzz', links: false }, now)).toBe(false)
})

function mem(init?: string) {
  const m = new Map<string, string>()
  if (init !== undefined) m.set(FILTER_KEY, init)
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }
}

test('loadFilter defaults to IT when empty', () => {
  expect(loadFilter(mem())).toEqual({ countries: ['IT'], maxAgeH: null, sources: [], text: '', links: false, favorites: false })
})

test('loadFilter defaults on invalid JSON', () => {
  expect(loadFilter(mem('{nope')).countries).toEqual(['IT'])
})

test('saveFilter/loadFilter round trip', () => {
  const s = mem()
  const f = { countries: ['FR', 'none'], maxAgeH: 24, sources: [], text: 'abc', links: false, favorites: false }
  saveFilter(s, f)
  expect(loadFilter(s)).toEqual(f)
  saveFilter(s, { ...f, countries: [] })
  expect(loadFilter(s).countries).toEqual([])
})

test('storage throwing falls back to default and does not throw on save', () => {
  const bad = {
    getItem: () => {
      throw new Error('denied')
    },
    setItem: () => {
      throw new Error('denied')
    },
  }
  expect(loadFilter(bad).countries).toEqual(['IT'])
  expect(() => saveFilter(bad, loadFilter(bad))).not.toThrow()
})

test('links toggle round trip', () => {
  const s = mem()
  saveFilter(s, { ...loadFilter(s), links: true })
  expect(loadFilter(s).links).toBe(true)
  expect(loadFilter(mem('{"links":"si"}')).links).toBe(false)
})

test('null last_heard', () => {
  expect(ageClass(null, now)).toBe('old')
  const nn = { ...n, last_heard: null } as Node
  expect(matchNode(nn, { countries: [], maxAgeH: 24, sources: [], text: '', links: false }, now)).toBe(false)
  expect(matchNode(nn, { countries: [], maxAgeH: null, sources: [], text: '', links: false }, now)).toBe(true)
})

// ---- filtro del feed MQTT (separato dalla mappa) ----
import { matchFeed, countFeedHidden, loadFeedFilter, saveFeedFilter, FEED_FILTER_KEY } from './filters'

function memFeed(init?: string) {
  const m = new Map<string, string>()
  if (init !== undefined) m.set(FEED_FILTER_KEY, init)
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }
}

test('feed default: tutte le nazioni, senza posizione incluse', () => {
  const f = loadFeedFilter(memFeed())
  expect(f).toEqual({ countries: [], includeUnknown: true })
  expect(matchFeed('IT', f)).toBe(true)
  expect(matchFeed('DE', f)).toBe(true)
  expect(matchFeed(null, f)).toBe(true)
})

test('feed: nazioni scelte e nodi senza posizione', () => {
  const f = { countries: ['IT'], includeUnknown: true }
  expect(matchFeed('IT', f)).toBe(true)
  expect(matchFeed('DE', f)).toBe(false)
  expect(matchFeed(null, f)).toBe(true)
  expect(matchFeed(null, { ...f, includeUnknown: false })).toBe(false)
  expect(matchFeed('DE', { countries: [], includeUnknown: false })).toBe(true)
})

test('feed: conteggio nascosti', () => {
  const msgs = [{ country: 'IT' }, { country: 'DE' }, { country: null }, { country: 'FR' }]
  expect(countFeedHidden(msgs, { countries: ['IT'], includeUnknown: false })).toBe(3)
  expect(countFeedHidden(msgs, { countries: [], includeUnknown: true })).toBe(0)
})

test('feed: salvataggio e dati vecchi o corrotti', () => {
  const s = memFeed()
  saveFeedFilter(s, { countries: ['IT', 'FR'], includeUnknown: false })
  expect(loadFeedFilter(s)).toEqual({ countries: ['IT', 'FR'], includeUnknown: false })
  expect(loadFeedFilter(memFeed('{"countries":"IT","includeUnknown":"x"}'))).toEqual({ countries: [], includeUnknown: true })
  expect(loadFeedFilter(memFeed('{"countries":["IT",3]}'))).toEqual({ countries: ['IT'], includeUnknown: true })
  expect(loadFeedFilter(memFeed('not json'))).toEqual({ countries: [], includeUnknown: true })
  const bad = { getItem: () => { throw new Error('x') }, setItem: () => { throw new Error('x') } }
  expect(loadFeedFilter(bad)).toEqual({ countries: [], includeUnknown: true })
  expect(() => saveFeedFilter(bad, { countries: [], includeUnknown: true })).not.toThrow()
})

test('favorites filter and tolerant load of old saved data', () => {
  const f = { countries: [], maxAgeH: null, sources: [], text: '', links: false, favorites: true }
  expect(matchNode({ ...n, is_favorite: true } as Node, f, now)).toBe(true)
  expect(matchNode(n, f, now)).toBe(false)
  expect(matchNode(n, { ...f, favorites: false }, now)).toBe(true)
  // dati salvati da versioni precedenti: nessun campo `favorites`
  expect(loadFilter(mem('{"countries":["IT"],"links":true}')).favorites).toBe(false)
  expect(loadFilter(mem('{"favorites":"si"}')).favorites).toBe(false)
  const s = mem()
  saveFilter(s, { ...loadFilter(s), favorites: true })
  expect(loadFilter(s).favorites).toBe(true)
})
