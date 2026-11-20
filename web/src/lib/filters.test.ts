import { test, expect } from 'vitest'
import { matchNode, ageClass, loadFilter, saveFilter, FILTER_KEY } from './filters'
import type { Node } from './types'

const now = 1_000_000
const n = { id: '!a1b2c3d4', long_name: 'Base Milano', short_name: 'BM', country: 'IT', last_heard: now - 3600, sources: ['mqtt'] } as Node

test('country filter', () => {
  expect(matchNode(n, { countries: ['IT'], maxAgeH: null, sources: [], text: '' }, now)).toBe(true)
  expect(matchNode(n, { countries: ['FR'], maxAgeH: null, sources: [], text: '' }, now)).toBe(false)
  expect(matchNode({ ...n, country: null }, { countries: ['none'], maxAgeH: null, sources: [], text: '' }, now)).toBe(true)
})

test('age and text', () => {
  expect(matchNode(n, { countries: [], maxAgeH: 0.5, sources: [], text: '' }, now)).toBe(false)
  expect(matchNode(n, { countries: [], maxAgeH: null, sources: [], text: 'milano' }, now)).toBe(true)
  expect(ageClass(now - 3600, now)).toBe('fresh')
  expect(ageClass(now - 3 * 3600, now)).toBe('recent')
  expect(ageClass(now - 25 * 3600, now)).toBe('old')
})

test('sources and null names', () => {
  expect(matchNode(n, { countries: [], maxAgeH: null, sources: ['rf'], text: '' }, now)).toBe(false)
  expect(matchNode(n, { countries: [], maxAgeH: null, sources: ['rf', 'mqtt'], text: '' }, now)).toBe(true)
  const bare = { ...n, long_name: null, short_name: null } as Node
  expect(matchNode(bare, { countries: [], maxAgeH: null, sources: [], text: 'A1B2' }, now)).toBe(true)
  expect(matchNode(bare, { countries: [], maxAgeH: null, sources: [], text: 'zzz' }, now)).toBe(false)
})

function mem(init?: string) {
  const m = new Map<string, string>()
  if (init !== undefined) m.set(FILTER_KEY, init)
  return { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }
}

test('loadFilter defaults to IT when empty', () => {
  expect(loadFilter(mem())).toEqual({ countries: ['IT'], maxAgeH: null, sources: [], text: '' })
})

test('loadFilter defaults on invalid JSON', () => {
  expect(loadFilter(mem('{nope')).countries).toEqual(['IT'])
})

test('saveFilter/loadFilter round trip', () => {
  const s = mem()
  const f = { countries: ['FR', 'none'], maxAgeH: 24, sources: [], text: 'abc' }
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
