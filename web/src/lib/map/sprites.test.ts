import { describe, expect, it } from 'vitest'
import { ringColor, ringShapes, starPoints } from './sprites'
import { FALLBACK_TOKENS as T } from './tokens'

describe('anelli della fonte', () => {
  it('colori dai token src-*', () => {
    expect(ringColor('radio', T)).toBe(T.srcRadio)
    expect(ringColor('mqtt', T)).toBe(T.srcMqtt)
    expect(ringColor('both', T)).toBe(T.srcBoth)
    expect(ringColor('radio', { ...T, srcRadio: '#0369a1' })).toBe('#0369a1')
  })
  it('pieno, tratteggiato, doppio', () => {
    expect(ringShapes('radio')).toHaveLength(1)
    expect(ringShapes('radio')[0].dash).toBeUndefined()
    expect(ringShapes('mqtt')[0].dash).toBeDefined()
    const both = ringShapes('both')
    expect(both).toHaveLength(2)
    expect(both[0].r).not.toBe(both[1].r)
  })
})

describe('starPoints', () => {
  it('10 vertici alternati esterno/interno, il primo in alto', () => {
    const p = starPoints(10, 10, 8, 3)
    expect(p).toHaveLength(10)
    expect(p[0][0]).toBeCloseTo(10)
    expect(p[0][1]).toBeCloseTo(2)
    expect(Math.hypot(p[1][0] - 10, p[1][1] - 10)).toBeCloseTo(3)
  })
})
