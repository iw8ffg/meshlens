import { test, expect } from 'vitest'
import { linksToGeoJSON, snrColor } from './links'
import type { Link, Node } from './types'

const node = (id: string, lat: number | null, lon: number | null) => ({ id, lat, lon, short_name: id, long_name: null }) as Node
const nodes = new Map<string, Node>([
  ['!a', node('!a', 45, 9)],
  ['!b', node('!b', 46, 10)],
  ['!nogps', node('!nogps', null, null)],
])
const link = (from_id: string, to_id: string, snr: number | null, time: number, source: Link['source'] = 'neighborinfo') =>
  ({ from_id, to_id, snr, time, source }) as Link

test('snrColor ai limiti', () => {
  expect(snrColor(0)).toBe('#2e9d4b')
  expect(snrColor(5)).toBe('#2e9d4b')
  expect(snrColor(-0.1)).toBe('#d9a400')
  expect(snrColor(-10)).toBe('#d9a400')
  expect(snrColor(-10.1)).toBe('#c8382e')
  expect(snrColor(null)).toBe('#8a8a8a')
})

test('A->B e B->A in una sola linea con SNR migliore e tempo piu recente', () => {
  const fc = linksToGeoJSON([link('!a', '!b', -12, 1000), link('!b', '!a', 3, 900)], nodes, 1000 + 7200)
  expect(fc.features).toHaveLength(1)
  const p = fc.features[0].properties!
  expect(p.snr).toBe(3)
  expect(p.color).toBe('#2e9d4b')
  expect(p.age_h).toBeCloseTo(2)
  expect(fc.features[0].geometry.coordinates).toEqual([
    [9, 45],
    [10, 46],
  ])
})

test('estremo senza posizione saltato', () => {
  expect(linksToGeoJSON([link('!a', '!nogps', 1, 1)], nodes, 10).features).toHaveLength(0)
})

test('nodo assente saltato', () => {
  expect(linksToGeoJSON([link('!a', '!zz', 1, 1)], nodes, 10).features).toHaveLength(0)
})

test('SNR null non batte uno noto', () => {
  const fc = linksToGeoJSON([link('!a', '!b', null, 5), link('!b', '!a', -8, 4)], nodes, 10)
  expect(fc.features[0].properties!.snr).toBe(-8)
})
