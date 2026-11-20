import { describe, expect, it } from 'vitest'
import { joinLines, parseLines } from './settings'

describe('parseLines', () => {
  it('toglie spazi e righe vuote', () => {
    expect(parseLines(' a \r\n\n  \nb\n')).toEqual(['a', 'b'])
  })
  it('testo vuoto -> lista vuota', () => {
    expect(parseLines('')).toEqual([])
  })
  it('round trip con joinLines', () => {
    expect(parseLines(joinLines(['msh/EU_868/#', 'x']))).toEqual(['msh/EU_868/#', 'x'])
  })
})
