import { describe, expect, it } from 'vitest'
import { generatePsk, isWeak, keyKind } from './psk'

const bytesOf = (b64: string) => atob(b64).length
const rnd32 = () => btoa(String.fromCharCode(...Array.from({ length: 32 }, (_, i) => (i * 37 + 11) % 256)))

describe('psk', () => {
  it('generatePsk: 32 o 16 byte, sempre diversa', () => {
    expect(bytesOf(generatePsk())).toBe(32)
    expect(bytesOf(generatePsk(16))).toBe(16)
    expect(generatePsk()).not.toBe(generatePsk())
  })

  it('keyKind come config_model.psk_kind', () => {
    expect(keyKind('')).toBe('none')
    expect(keyKind('AA==')).toBe('none')
    expect(keyKind('AQ==')).toBe('default')
    expect(keyKind('BQ==')).toBe('default')
    expect(keyKind('1PG7OiApB1nwvP+rz05pAQ==')).toBe('default')
    expect(keyKind(rnd32())).toBe('custom')
    expect(keyKind(btoa('0123456789abcdef'))).toBe('custom')
    expect(keyKind('%%')).toBe('invalid')
    expect(keyKind(btoa('12345'))).toBe('invalid')
  })

  it('isWeak', () => {
    expect(isWeak('default')).toBe(true)
    expect(isWeak('none')).toBe(true)
    expect(isWeak('custom')).toBe(false)
    expect(isWeak('invalid')).toBe(false)
    expect(isWeak(undefined)).toBe(false)
  })
})
