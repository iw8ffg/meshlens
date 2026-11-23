import { describe, expect, it, vi } from 'vitest'
import type { Map as MLMap } from 'maplibre-gl'
import { createPropertyExpression, latest } from '@maplibre/maplibre-gl-style-spec'
import { addOverlayLayers, applyOverlayVisibility } from './overlays'
import { PRECISION_RADIUS_EXPR, addPrecisionLayer } from './PrecisionLayer'
import { addHeatLayer } from './HeatLayer'
import { addTakLayer, takFeatures } from './TakLayer'
import { addLinkLayers, setLinkLabelZoom } from './LinkLayer'
import { defaultLayers } from './layerstate'
import { ageMinutes } from './NodeLayer'
import { FALLBACK_TOKENS as T } from './tokens'
import type { TakContact } from '../types'

const fakeMap = (existing: string[] = []) => {
  const m = {
    addSource: vi.fn(),
    addLayer: vi.fn(),
    getLayer: vi.fn((id: string) => (existing.includes(id) ? { id } : undefined)),
    setLayoutProperty: vi.fn(),
    setLayerZoomRange: vi.fn(),
  }
  return { m, map: m as unknown as MLMap }
}
const ids = (m: ReturnType<typeof fakeMap>['m']) => m.addLayer.mock.calls.map((c) => c[0].id)
const layer = (m: ReturnType<typeof fakeMap>['m'], id: string) => m.addLayer.mock.calls.find((c) => c[0].id === id)!

describe('strati', () => {
  it('il raggio di precisione e\' un\'espressione composite valida', () => {
    const r = createPropertyExpression(PRECISION_RADIUS_EXPR, 'circle-radius', (latest as any).paint_circle['circle-radius'])
    expect(r.result).toBe('success')
    if (r.result === 'success') expect(r.value.kind).toBe('composite')
  })
  it('precisione: sorgente, id, minzoom e posizione', () => {
    const { m, map } = fakeMap()
    addPrecisionLayer(map, T)
    expect(m.addSource.mock.calls[0][0]).toBe('precision-all')
    const [l, before] = layer(m, 'precision-all-circle')
    expect(l.type).toBe('circle')
    expect(l.minzoom).toBe(8)
    expect(l.paint['circle-pitch-alignment']).toBe('map')
    expect(before).toBe('precision-fill')
  })
  it('calore: valori predefiniti e posizione', () => {
    const a = fakeMap()
    addHeatLayer(a.map, T)
    const [l, before] = layer(a.m, 'heat-layer')
    expect(l.type).toBe('heatmap')
    expect(l.source).toBe('heat')
    expect(l.paint['heatmap-weight']).toBe(1)
    const op = l.paint['heatmap-opacity'] as unknown[]
    expect(op[0]).toBe('interpolate')
    expect(op[2]).toEqual(['zoom'])
    expect(op[4] as number).toBeGreaterThan(op[6] as number)
    const color = l.paint['heatmap-color'] as unknown[]
    expect(color[4]).toBe('rgba(0,0,0,0)')
    expect([color[6], color[8], color[10]]).toEqual([T.srcRadio, T.contactRecent, T.snrBad])
    expect(before).toBe('precision-fill')
    const b = fakeMap(['precision-all-circle'])
    addHeatLayer(b.map, T)
    expect(layer(b.m, 'heat-layer')[1]).toBe('precision-all-circle')
  })
  it('ATAK: con e senza glyph', () => {
    const a = fakeMap()
    addTakLayer(a.map, T, false)
    expect(ids(a.m)).toEqual(['tak-points'])
    const b = fakeMap()
    addTakLayer(b.map, T, true)
    expect(ids(b.m)).toEqual(['tak-points', 'tak-labels'])
    expect(layer(b.m, 'tak-labels')[0].layout['text-optional']).toBe(true)
  })
  it('takFeatures', () => {
    const c = (o: Partial<TakContact>): TakContact => ({ node_id: '!a', callsign: 'ALFA', device_callsign: null, team: 'Cyan', role: null, battery: null, lat: 45, lon: 9, altitude: null, speed: null, course: null, compressed: false, time: 1000, source: 'rf', ...o })
    const f = takFeatures([c({}), c({ node_id: '!b', lat: null }), c({ node_id: '!c', callsign: null, compressed: true })], (id) => `nome ${id}`, 1600)
    expect(f).toHaveLength(2)
    expect(f[0].properties).toMatchObject({ label: 'ALFA', age_min: ageMinutes(1000, 1600) })
    expect(f[1].properties).toMatchObject({ label: 'nome !c', compressed: true })
  })
  it('etichette dei collegamenti solo con i glyph', () => {
    const a = fakeMap()
    addLinkLayers(a.map, T)
    expect(ids(a.m)).toEqual(['links', 'links-trace', 'links-gateway'])
    const b = fakeMap()
    addLinkLayers(b.map, T, true)
    const [l] = layer(b.m, 'links-labels')
    expect(l.layout['symbol-placement']).toBe('line-center')
    expect(l.layout['text-field']).toEqual(['get', 'label'])
    expect(l.filter).toEqual(['!=', ['get', 'label'], ''])
    expect(l.minzoom).toBe(9)
  })
  it('zoom delle etichette', () => {
    const a = fakeMap(['links-labels'])
    setLinkLabelZoom(a.map, true)
    expect(a.m.setLayerZoomRange).toHaveBeenCalledWith('links-labels', 11, 24)
    setLinkLabelZoom(a.map, false)
    expect(a.m.setLayerZoomRange).toHaveBeenLastCalledWith('links-labels', 9, 24)
    const b = fakeMap()
    setLinkLabelZoom(b.map, true)
    expect(b.m.setLayerZoomRange).not.toHaveBeenCalled()
  })
  it('visibilita\'', () => {
    const { m, map } = fakeMap(['precision-all-circle', 'heat-layer', 'tak-points', 'tak-labels', 'links-labels'])
    applyOverlayVisibility(map, { ...defaultLayers(), precision: true, linkLabels: true })
    const calls = m.setLayoutProperty.mock.calls.map((c) => `${c[0]}:${c[2]}`)
    expect(calls).toContain('precision-all-circle:visible')
    expect(calls).toContain('links-labels:visible')
    expect(calls).toContain('heat-layer:none')
    expect(calls).toContain('tak-points:none')
    expect(calls).toContain('tak-labels:none')
    const x = fakeMap()
    applyOverlayVisibility(x.map, defaultLayers())
    expect(x.m.setLayoutProperty).not.toHaveBeenCalled()
  })
  it('addOverlayLayers aggiunge i tre gruppi in ordine', () => {
    const { m, map } = fakeMap()
    addOverlayLayers(map, T, true)
    expect(ids(m)).toEqual(['precision-all-circle', 'heat-layer', 'tak-points', 'tak-labels'])
  })
})
