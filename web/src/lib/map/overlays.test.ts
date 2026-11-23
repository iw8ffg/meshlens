import { describe, expect, it } from 'vitest'
import { HEAT_MAX, M_PER_PX_Z22, PRECISION_MAX, denseLabels, heatPoints, precisionCircles } from './overlays'
import { precisionRadiusM } from '../geo'
import type { Node } from '../types'

const node = (o: Partial<Node>): Node => ({ id: '!a', num: 1, lat: 45, lon: 9, precision_bits: null, last_heard: 1000, is_ignored: false, ...o }) as unknown as Node

describe('precisionCircles', () => {
  it('raggio e px22 coerenti', () => {
    const [f] = precisionCircles([node({ precision_bits: 13 })])
    const r = precisionRadiusM(13)!
    expect(f.properties!.r_m).toBe(r)
    expect(f.properties!.px22).toBeCloseTo(r / (M_PER_PX_Z22 * Math.cos(Math.PI / 4)), 2)
  })
  it('esclude bits non validi, senza posizione e ignorati', () => {
    const list = [null, 0, 16, 32].map((b, i) => node({ num: i, precision_bits: b }))
    list.push(node({ precision_bits: 10, lat: null, lon: null }), node({ precision_bits: 10, is_ignored: true }))
    expect(precisionCircles(list)).toHaveLength(0)
  })
  it('tetto: tiene i raggi maggiori', () => {
    const list = Array.from({ length: 4000 }, (_, i) => node({ num: i, precision_bits: 1 + (i % 15) }))
    const out = precisionCircles(list)
    expect(out).toHaveLength(PRECISION_MAX)
    expect(Math.min(...out.map((f) => f.properties!.r_m as number))).toBeGreaterThanOrEqual(precisionRadiusM(12)!)
  })
  it('coerenza fisica a zoom 12, lat 45', () => {
    const [f] = precisionCircles([node({ precision_bits: 12 })])
    const mPerPx12 = (156543.03392 * Math.cos(Math.PI / 4)) / 2 ** 12
    const px = (f.properties!.px22 as number) * 2 ** (12 - 22)
    expect(px * mPerPx12).toBeCloseTo(f.properties!.r_m as number, -1)
    expect(Math.abs((px * mPerPx12) / (f.properties!.r_m as number) - 1)).toBeLessThan(0.005)
  })
  it('20000 nodi in meno di 500 ms', () => {
    const list = Array.from({ length: 20000 }, (_, i) => node({ num: i, precision_bits: 1 + (i % 15), lat: 40 + (i % 100) / 10 }))
    const t0 = performance.now()
    precisionCircles(list)
    expect(performance.now() - t0).toBeLessThan(500)
  })
})

describe('heatPoints', () => {
  it('solo con posizione, vuoto ok', () => {
    expect(heatPoints([])).toEqual([])
    expect(heatPoints([node({}), node({ lat: null, lon: null })])).toHaveLength(1)
  })
  it('oltre il tetto tiene i piu\' recenti', () => {
    const list = Array.from({ length: 25000 }, (_, i) => node({ num: i, last_heard: i }))
    const out = heatPoints(list)
    expect(out).toHaveLength(HEAT_MAX)
  })
  it('20000 nodi in meno di 500 ms', () => {
    const list = Array.from({ length: 20000 }, (_, i) => node({ num: i }))
    const t0 = performance.now()
    heatPoints(list)
    expect(performance.now() - t0).toBeLessThan(500)
  })
})

describe('denseLabels', () => {
  it('soglia a 800', () => {
    expect(denseLabels(800)).toBe(false)
    expect(denseLabels(801)).toBe(true)
  })
})
