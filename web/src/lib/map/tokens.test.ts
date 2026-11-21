import { describe, expect, it } from 'vitest'
import { FALLBACK_TOKENS, mix, readTokens, TOKEN_VARS } from './tokens'

describe('readTokens', () => {
  it('legge ogni variabile e usa la riserva se vuota', () => {
    const t = readTokens((n) => (n === '--map-land' ? ' #e9eef2 ' : n === '--src-mqtt' ? '#a1337a' : ''))
    expect(t.land).toBe('#e9eef2')
    expect(t.srcMqtt).toBe('#a1337a')
    expect(t.water).toBe(FALLBACK_TOKENS.water)
  })
  it('ogni chiave ha una variabile --*', () => {
    for (const v of Object.values(TOKEN_VARS)) expect(v).toMatch(/^--[a-z-]+$/)
  })
})

describe('mix', () => {
  it('estremi e meta', () => {
    expect(mix('#000000', '#ffffff', 0)).toBe('#000000')
    expect(mix('#000000', '#ffffff', 1)).toBe('#ffffff')
    expect(mix('#000000', '#ffffff', 0.5)).toBe('#808080')
    expect(mix('#fff', '#000', 0.5)).toBe('#808080')
  })
  it('colore non esadecimale: resta il primo', () => {
    expect(mix('red', '#000000', 0.5)).toBe('red')
  })
})
