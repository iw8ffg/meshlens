import { describe, expect, it } from 'vitest'
import { LAYERS_KEY, defaultLayers, loadLayers, saveLayers } from './layerstate'

const mem = () => {
  const d = new Map<string, string>()
  return { getItem: (k: string) => d.get(k) ?? null, setItem: (k: string, v: string) => void d.set(k, v), d }
}

describe('layerstate', () => {
  it('predefiniti: tutto spento', () => {
    expect(loadLayers(null)).toEqual(defaultLayers())
    expect(Object.values(defaultLayers()).every((v) => v === false)).toBe(true)
    const s = mem()
    expect(loadLayers(s)).toEqual(defaultLayers())
    s.d.set(LAYERS_KEY, '{rotto')
    expect(loadLayers(s)).toEqual(defaultLayers())
    s.d.set(LAYERS_KEY, JSON.stringify({ v: 2, heat: true }))
    expect(loadLayers(s)).toEqual(defaultLayers())
  })
  it('salva e unisce', () => {
    const s = mem()
    saveLayers(s, { heat: true })
    expect(loadLayers(s)).toEqual({ ...defaultLayers(), heat: true })
    saveLayers(s, { infra: true })
    expect(loadLayers(s)).toEqual({ ...defaultLayers(), heat: true, infra: true })
  })
  it('un campo non booleano torna spento solo lui', () => {
    const s = mem()
    s.d.set(LAYERS_KEY, JSON.stringify({ v: 1, heat: 'si', tak: true }))
    expect(loadLayers(s)).toEqual({ ...defaultLayers(), tak: true })
  })
  it('setItem che lancia: nessuna eccezione; scrive solo la propria chiave', () => {
    const bad = { getItem: () => null, setItem: () => { throw new Error('quota') } }
    expect(() => saveLayers(bad, { heat: true })).not.toThrow()
    const s = mem()
    saveLayers(s, { tak: true })
    expect([...s.d.keys()]).toEqual(['meshlens.layers'])
  })
})
