import { describe, expect, it } from 'vitest'
import { addRulerPoint, rulerGeoJSON, rulerText } from './ruler'
import type { RulerPoint } from './ruler'

const P = (lon: number, lat: number, nodeId: string | null = null): RulerPoint => ({ lon, lat, nodeId })
const MI = P(9.19, 45.4642)
const MZ = P(9.2744, 45.5845)

describe('righello', () => {
  it('addRulerPoint: 1, 2, poi ricomincia da 1', () => {
    let pts: RulerPoint[] = []
    pts = addRulerPoint(pts, MI)
    expect(pts).toHaveLength(1)
    pts = addRulerPoint(pts, MZ)
    expect(pts).toHaveLength(2)
    const c = P(1, 2)
    pts = addRulerPoint(pts, c)
    expect(pts).toEqual([c])
  })
  it('rulerGeoJSON: due punti = 3 feature con una LineString', () => {
    const g = rulerGeoJSON([MI, MZ])
    expect(g.features).toHaveLength(3)
    expect(g.features.filter((f) => f.geometry.type === 'LineString')).toHaveLength(1)
    expect(g.features.filter((f) => f.geometry.type === 'Point').map((f) => f.properties?.idx)).toEqual([0, 1])
  })
  it('rulerGeoJSON: un punto = 1 feature, nessun punto = vuoto', () => {
    expect(rulerGeoJSON([MI]).features).toHaveLength(1)
    expect(rulerGeoJSON([]).features).toHaveLength(0)
  })
  it('rulerText con 0, 1 e 2 punti', () => {
    const name = (id: string) => id
    expect(rulerText([], name)).toBe('Tocca il primo punto sulla mappa')
    expect(rulerText([MI], name)).toBe('Tocca il secondo punto')
    const t = rulerText([MI, MZ], name)
    expect(t[0] === '1' || t[0] === '2').toBe(true)
    expect(t).toContain(' km · ')
    expect(t).toContain('N')
  })
  it('con due nodi aggiunge «da A a B»', () => {
    const names: Record<string, string> = { '!a': 'Alfa', '!b': 'Beta' }
    const t = rulerText([P(9.19, 45.4642, '!a'), P(9.2744, 45.5845, '!b')], (id) => names[id])
    expect(t.endsWith(' · da Alfa a Beta')).toBe(true)
  })
})
