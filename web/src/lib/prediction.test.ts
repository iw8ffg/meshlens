import { describe, expect, it } from 'vitest'
import { FALLBACK_TOKENS } from './map/tokens'
import {
  decodeValues, defaultParams, eirpDbm, gridToRgba, hexToRgb, imageCoordinates, marginBand, overLegalLimit, validateParams,
} from './prediction'

describe('marginBand', () => {
  it('fasce ai bordi', () => {
    expect(marginBand(10)).toBe('good')
    expect(marginBand(9)).toBe('mid')
    expect(marginBand(0)).toBe('mid')
    expect(marginBand(-1)).toBe('weak')
    expect(marginBand(-10)).toBe('weak')
    expect(marginBand(-11)).toBeNull()
    expect(marginBand(-128)).toBeNull()
  })
})

describe('gridToRgba', () => {
  it('colori dei token e alpha per fascia', () => {
    const px = gridToRgba(Int8Array.from([20, 5, -5, -128]), FALLBACK_TOKENS)
    const t = FALLBACK_TOKENS
    expect([...px.slice(0, 4)]).toEqual([...hexToRgb(t.snrGood), 140])
    expect([...px.slice(4, 8)]).toEqual([...hexToRgb(t.snrMid), 115])
    expect([...px.slice(8, 12)]).toEqual([...hexToRgb(t.snrBad), 80])
    expect(px[15]).toBe(0)
  })
})

describe('validateParams', () => {
  it('raggio fuori limite', () => {
    expect(validateParams({ ...defaultParams(), radius_km: 0 })).toBe('Raggio: tra 1 e 50 km')
  })
  it('parametri predefiniti validi', () => {
    expect(validateParams(defaultParams())).toBeNull()
  })
})

describe('limite di legge', () => {
  it('EIRP oltre 29,15 dBm', () => {
    expect(overLegalLimit({ ...defaultParams(), tx_power_dbm: 27, antenna_gain_dbi: 3 })).toBe(true)
    expect(overLegalLimit({ ...defaultParams(), tx_power_dbm: 22, antenna_gain_dbi: 2 })).toBe(false)
    expect(eirpDbm({ ...defaultParams(), cable_loss_db: 1 })).toBe(23)
  })
})

describe('geometria e decodifica', () => {
  it('imageCoordinates', () => {
    expect(imageCoordinates([1, 2, 3, 4])).toEqual([[1, 4], [3, 4], [3, 2], [1, 2]])
  })
  it('decodeValues con segno', () => {
    expect([...decodeValues(btoa(String.fromCharCode(255, 1)))]).toEqual([-1, 1])
  })
})
