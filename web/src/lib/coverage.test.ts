import { describe, expect, it } from 'vitest'
import { checklist, formatLoss } from './coverage'
import type { CoverageCheck } from './types'

const good: CoverageCheck = {
  radio_connected: true,
  radio_channels: [],
  mobile_known: true,
  position_age_s: 20,
  precision_bits: 32,
  precision_m: null,
  gps_ok: true,
  rangetest_age_s: 15,
  base_position: null,
}

describe('checklist', () => {
  it('senza controlli tutti i passi hanno ok null', () => {
    const l = checklist(null, 'rangetest')
    expect(l.length).toBe(5)
    expect(l.every((s) => s.ok === null)).toBe(true)
  })
  it('gps_ok false segna il passo GPS', () => {
    const l = checklist({ ...good, gps_ok: false, position_age_s: 900 }, 'rangetest')
    expect(l.find((s) => s.key === 'gps')?.ok).toBe(false)
  })
  it('precisione approssimata: ok false e raggio in km', () => {
    const l = checklist({ ...good, precision_bits: 13, precision_m: 2900 }, 'rangetest')
    const p = l.find((s) => s.key === 'precision')!
    expect(p.ok).toBe(false)
    expect(p.label + p.hint).toContain('2,9 km')
  })
  it('posizione esatta: tutto ok', () => {
    expect(checklist(good, 'rangetest').every((s) => s.ok === true)).toBe(true)
  })
  it('in modalita position non c\'e il passo Range Test', () => {
    const l = checklist(good, 'position')
    expect(l.some((s) => s.key === 'rangetest')).toBe(false)
  })
  it('range test mai ricevuto: ok false', () => {
    const l = checklist({ ...good, rangetest_age_s: null }, 'rangetest')
    expect(l.find((s) => s.key === 'rangetest')?.ok).toBe(false)
  })
})

describe('formatLoss', () => {
  it('null -> trattino', () => {
    expect(formatLoss(null)).toBe('—')
  })
  it('valore con virgola', () => {
    expect(formatLoss(6.67)).toBe('6,7%')
  })
})
