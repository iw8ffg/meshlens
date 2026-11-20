import { describe, expect, it } from 'vitest'
import { circlePolygon, formatPrecision, precisionRadiusM } from './geo'

describe('precisionRadiusM', () => {
  it('13 bit -> 2844 m', () => expect(precisionRadiusM(13)).toBe(2844))
  it('16 bit o piu e null (posizione esatta)', () => {
    expect(precisionRadiusM(16)).toBeNull()
    expect(precisionRadiusM(32)).toBeNull()
  })
  it('null/0 -> null', () => {
    expect(precisionRadiusM(null)).toBeNull()
    expect(precisionRadiusM(0)).toBeNull()
  })
})

describe('formatPrecision', () => {
  it('km con virgola', () => expect(formatPrecision(14)).toBe('± 1,4 km'))
  it('metri sotto 1 km', () => expect(formatPrecision(15)).toBe('± 710 m'))
  it('esatta -> null', () => expect(formatPrecision(16)).toBeNull())
})

describe('circlePolygon', () => {
  it('anello chiuso con steps+1 punti', () => {
    const r = circlePolygon(42, 12, 1000, 16)
    expect(r).toHaveLength(17)
    expect(r[0]).toEqual(r[16])
  })
})
