import { test, expect } from 'vitest'
import { matchNode, ageClass } from './filters'
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
