import { describe, expect, it, test } from 'vitest'
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

import { channelOptions, STANDARD_CHANNELS } from './settings'

test('channelOptions: preset standard piu canali visti, ordinati per conteggio', () => {
  expect(STANDARD_CHANNELS[0]).toBe('LongFast')
  const o = channelOptions([{ name: 'Custom', count_1h: 7, enabled: true }, { name: 'LongFast', count_1h: 3, enabled: true }], ['Old'])
  expect(o.find((x) => x.name === 'Custom')).toEqual({ name: 'Custom', count: 7 })
  expect(o.find((x) => x.name === 'LongFast')).toEqual({ name: 'LongFast', count: 3 })
  expect(o.find((x) => x.name === 'MediumSlow')).toEqual({ name: 'MediumSlow', count: 0 })
  expect(o.find((x) => x.name === 'Old')).toEqual({ name: 'Old', count: 0 })
  expect(o.map((x) => x.name).filter((n) => n === 'LongFast')).toHaveLength(1)
  expect(o[0].name).toBe('Custom')
})
