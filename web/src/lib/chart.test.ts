import { describe, expect, it } from 'vitest'
import { batterySeries, chartTime, isolatedPoints, linePath, nearestIndex, niceRange, pctRange } from './chart'

describe('linePath', () => {
  it('genera M…L…L… per 3 punti', () => {
    const p = linePath(
      [
        { t: 0, v: 0 },
        { t: 5, v: 50 },
        { t: 10, v: 100 },
      ],
      0, 10, 0, 100, 100, 50,
    )
    expect(p.match(/M/g)?.length).toBe(1)
    expect(p.match(/L/g)?.length).toBe(2)
    expect(p.startsWith('M0,50')).toBe(true)
    expect(p.endsWith('L100,0')).toBe(true)
  })
  it('un null interrompe la linea con un nuovo M', () => {
    const p = linePath(
      [
        { t: 0, v: 1 },
        { t: 1, v: null },
        { t: 2, v: 3 },
      ],
      0, 2, 0, 4, 100, 100,
    )
    expect(p.match(/M/g)?.length).toBe(2)
    expect(p.match(/L/g)).toBeNull()
  })
  it('vuoto se non ci sono punti', () => {
    expect(linePath([], 0, 1, 0, 1, 10, 10)).toBe('')
  })
})

describe('batterySeries', () => {
  it('scarta il 101 (alimentazione esterna)', () => {
    const s = batterySeries([
      { time: 1, battery: 80 },
      { time: 2, battery: 101 },
      { time: 3, battery: null },
    ])
    expect(s).toEqual([
      { t: 1, v: 80 },
      { t: 2, v: null },
      { t: 3, v: null },
    ])
  })
})

describe('niceRange', () => {
  it('copre i valori', () => {
    const [lo, hi] = niceRange([3.7, 4.1], 0.1)
    expect(lo).toBeLessThanOrEqual(3.7)
    expect(hi).toBeGreaterThanOrEqual(4.1)
  })
  it('intervallo non nullo con valore unico', () => {
    const [lo, hi] = niceRange([4], 0.1)
    expect(hi).toBeGreaterThan(lo)
  })
})

it('isolatedPoints: solo i punti senza vicini validi', () => {
  const pts = [
    { t: 0, v: 50 },
    { t: 1, v: null },
    { t: 2, v: 20 },
    { t: 3, v: 30 },
    { t: 4, v: null },
    { t: 5, v: 100 },
  ]
  expect(isolatedPoints(pts, 0, 5, 0, 100, 100, 100)).toEqual([
    { x: 0, y: 50 },
    { x: 100, y: 0 },
  ])
  expect(isolatedPoints([{ t: 7, v: 40 }], 7, 7, 0, 100, 100, 100)).toEqual([{ x: 0, y: 60 }])
})

describe('nearestIndex', () => {
  it('trova il piu vicino', () => {
    expect(nearestIndex([10, 20, 30], 24)).toBe(1)
    expect(nearestIndex([10, 20, 30], 26)).toBe(2)
    expect(nearestIndex([10, 20, 30], -5)).toBe(0)
    expect(nearestIndex([10, 20, 30], 99)).toBe(2)
    expect(nearestIndex([], 5)).toBe(-1)
  })
})

describe('chartTime', () => {
  const t = Date.UTC(2026, 10, 21, 14, 5) / 1000
  it('fino a 48 h solo ora', () => {
    expect(chartTime(t, 24)).toMatch(/^\d\d:\d\d$/)
  })
  it('oltre: giorno, mese e ora', () => {
    expect(chartTime(t, 200)).toMatch(/nov.*\d\d:\d\d$/)
  })
})

describe('pctRange', () => {
  it('arrotonda a 10', () => {
    expect(pctRange([3, 7])).toEqual([0, 10])
    expect(pctRange([42])).toEqual([0, 50])
    expect(pctRange([])).toEqual([0, 10])
  })
})
