import { describe, expect, it } from 'vitest'
import { bytes } from './maintenance'

describe('bytes', () => {
  it('formatta con la virgola italiana', () => {
    expect(bytes(1_536_000)).toBe('1,5 MB')
  })
  it('zero', () => {
    expect(bytes(0)).toBe('0 B')
  })
})
