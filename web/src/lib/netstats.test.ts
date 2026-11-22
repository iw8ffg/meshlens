import { describe, expect, it } from 'vitest'
import { barRects, kindLabel, kindTotals, packetsPerHour, snrBinLabel } from './netstats'

const rows = [
  { time: 7200, kind: 'text', packets: 3, receptions: 4 },
  { time: 3600, kind: 'text', packets: 1, receptions: 1 },
  { time: 3600, kind: 'position', packets: 4, receptions: 5 },
  { time: 7200, kind: 'telemetry', packets: 2, receptions: 2 },
]

describe('netstats', () => {
  it('packetsPerHour somma i tipi della stessa ora, in ordine', () => {
    expect(packetsPerHour(rows)).toEqual([
      { time: 3600, packets: 5 },
      { time: 7200, packets: 5 },
    ])
  })
  it('kindTotals ordina in modo decrescente e share somma 1', () => {
    const t = kindTotals(rows)
    expect(t.map((x) => [x.kind, x.packets])).toEqual([
      ['position', 4],
      ['text', 4],
      ['telemetry', 2],
    ])
    expect(t.reduce((a, x) => a + x.share, 0)).toBeCloseTo(1)
    expect(kindTotals([])).toEqual([])
  })
  it('barRects: altezze proporzionali, x crescenti', () => {
    const r = barRects([0, 5, 10], 30, 100)
    expect(r.map((b) => b.h)).toEqual([0, 50, 100])
    expect(r[0].x).toBeLessThan(r[1].x)
    expect(r[1].x).toBeLessThan(r[2].x)
  })
  it('barRects: tutti zero, altezza 0', () => {
    expect(barRects([0, 0], 10, 10).map((b) => b.h)).toEqual([0, 0])
  })
  it('snrBinLabel', () => {
    expect(snrBinLabel(-20)).toBe('−20…−17,5')
    expect(snrBinLabel(15)).toBe('≥ 15')
  })
  it('kindLabel: ripiego sulla chiave', () => {
    expect(kindLabel('xyz')).toBe('xyz')
    expect(kindLabel('text')).toBe('Messaggi')
  })
})
