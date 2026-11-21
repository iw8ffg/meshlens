import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { FALLBACK_TOKENS } from './map/tokens'
import { canSwitch, chooseMode, offlineStyle, SWITCH_MIN_MS } from './mapstyle'

describe('chooseMode', () => {
  it('online forzato', () => {
    for (const online of [true, false])
      for (const has of [true, false]) expect(chooseMode('online', online, has, false)).toBe('online')
  })
  it('offline forzato', () => {
    for (const online of [true, false])
      for (const has of [true, false]) expect(chooseMode('offline', online, has, true)).toBe('offline')
  })
  it('auto: tutte le combinazioni', () => {
    for (const online of [true, false])
      for (const has of [true, false])
        for (const failed of [true, false]) {
          const exp = online && !failed ? 'online' : has ? 'offline' : 'fallback'
          expect(chooseMode('auto', online, has, failed)).toBe(exp)
        }
  })
})

describe('canSwitch', () => {
  it('29 s no, 30 s si', () => {
    expect(canSwitch(0, 29_000)).toBe(false)
    expect(canSwitch(0, 30_000)).toBe(true)
    expect(SWITCH_MIN_MS).toBe(30_000)
  })
})

describe('offlineStyle', () => {
  beforeEach(() => vi.stubGlobal('location', { origin: 'http://localhost:8000' }))
  afterEach(() => vi.unstubAllGlobals())
  it('una sola sorgente con attribuzione e percorsi locali', () => {
    const s = offlineStyle({ maxzoom: 14 })
    expect(Object.keys(s.sources)).toEqual(['protomaps'])
    const src = s.sources.protomaps as { type: string; tiles: string[]; maxzoom: number; attribution: string }
    expect(src.type).toBe('vector')
    expect(src.tiles).toEqual(['http://localhost:8000/tiles/{z}/{x}/{y}.mvt'])
    expect(src.maxzoom).toBe(14)
    expect(src.attribution).toContain('OpenStreetMap')
    expect(s.glyphs).toBe('http://localhost:8000/map-assets/fonts/{fontstack}/{range}.pbf')
    expect(s.sprite).toBe('http://localhost:8000/map-assets/sprites/light')
    expect(s.layers.length).toBeGreaterThan(10)
  })
})

describe('offlineStyle in tema', () => {
  beforeEach(() => vi.stubGlobal('location', { origin: 'http://localhost:8000' }))
  afterEach(() => vi.unstubAllGlobals())
  it('lo sprite segue il tema', () => {
    expect(offlineStyle({ maxzoom: 14 }, 'dark').sprite).toBe('http://localhost:8000/map-assets/sprites/dark')
    expect(offlineStyle({ maxzoom: 14 }, 'light').sprite).toBe('http://localhost:8000/map-assets/sprites/light')
  })
  it('scuro e chiaro hanno fondo diverso; i token ricolorano il fondo', () => {
    const bg = (s: ReturnType<typeof offlineStyle>) => (s.layers[0] as { paint: { 'background-color': string } }).paint['background-color']
    expect(bg(offlineStyle({ maxzoom: 14 }, 'dark'))).not.toBe(bg(offlineStyle({ maxzoom: 14 }, 'light')))
    expect(bg(offlineStyle({ maxzoom: 14 }, 'dark', { ...FALLBACK_TOKENS, land: '#123456' }))).toBe('#123456')
  })
})
