import { describe, expect, it } from 'vitest'
import type { StyleSpecification } from 'maplibre-gl'
import { recolorLiberty, themedFlavor } from './basemap'
import { FALLBACK_TOKENS as T } from './tokens'

const raw = {
  version: 8,
  sources: { openmaptiles: { type: 'vector', url: 'https://tiles.openfreemap.org/planet' } },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#fff' } },
    { id: 'park', type: 'fill', source: 'openmaptiles', paint: { 'fill-color': '#0f0' } },
    { id: 'water', type: 'fill', source: 'openmaptiles', paint: { 'fill-color': '#00f' } },
    { id: 'building', type: 'fill', source: 'openmaptiles' },
    { id: 'highway_major', type: 'line', source: 'openmaptiles', paint: { 'line-color': '#f00' } },
    { id: 'road_minor_casing', type: 'line', source: 'openmaptiles' },
    { id: 'waterway', type: 'line', source: 'openmaptiles' },
    { id: 'label_city', type: 'symbol', source: 'openmaptiles', layout: { 'text-field': '{name}' }, paint: { 'text-color': '#000' } },
    { id: 'poi', type: 'symbol', source: 'openmaptiles', layout: { 'icon-image': 'x' } },
    { id: 'natural_earth', type: 'raster', source: 'ne' },
  ],
} as unknown as StyleSpecification

const paintOf = (s: StyleSpecification, id: string) => (s.layers.find((l) => l.id === id) as { paint: Record<string, unknown> }).paint

describe('recolorLiberty', () => {
  const out = recolorLiberty(raw, T)
  it('terra, acqua, strade ed etichette dai token', () => {
    expect(paintOf(out, 'background')['background-color']).toBe(T.land)
    expect(paintOf(out, 'water')['fill-color']).toBe(T.water)
    expect(paintOf(out, 'waterway')['line-color']).toBe(T.water)
    expect(paintOf(out, 'highway_major')['line-color']).toBe(T.road)
    const lbl = paintOf(out, 'label_city')
    expect(lbl['text-color']).toBe(T.label)
    expect(lbl['text-halo-color']).toBe(T.land)
  })
  it('parchi ed edifici sono miscele, i simboli senza testo restano', () => {
    expect(paintOf(out, 'park')['fill-color']).not.toBe(T.land)
    expect(paintOf(out, 'building')['fill-color']).not.toBe(T.water)
    expect(paintOf(out, 'poi')['text-color']).toBeUndefined()
    expect(paintOf(out, 'natural_earth')['raster-opacity']).toBe(0)
  })
  it('non modifica lo stile originale e conserva sorgenti e id', () => {
    expect(paintOf(raw, 'water')['fill-color']).toBe('#00f')
    expect(out.sources).toEqual(raw.sources)
    expect(out.layers.map((l) => l.id)).toEqual(raw.layers.map((l) => l.id))
  })
  it('chiaro e scuro danno colori diversi', () => {
    const light = recolorLiberty(raw, { ...T, land: '#e9eef2' })
    expect(paintOf(light, 'background')['background-color']).toBe('#e9eef2')
    expect(paintOf(out, 'background')['background-color']).toBe(T.land)
  })
})

describe('themedFlavor', () => {
  it('senza token e il flavor Protomaps del tema', () => {
    expect(themedFlavor('dark').background).not.toBe(themedFlavor('light').background)
  })
  it('con token usa terra, acqua, strade ed etichette', () => {
    const f = themedFlavor('dark', T)
    expect(f.background).toBe(T.land)
    expect(f.earth).toBe(T.land)
    expect(f.water).toBe(T.water)
    expect(f.highway).toBe(T.road)
    expect(f.city_label).toBe(T.label)
    expect(f.city_label_halo).toBe(T.land)
  })
})
