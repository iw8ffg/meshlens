import { describe, expect, it } from 'vitest'
import { ZONE_MAX, addVertex, moveVertex, removeVertex, zoneBounds, zoneError, zoneGeoJSON } from './zone'
import type { ZonePoint } from './zone'

const square: ZonePoint[] = [[0, 0], [10, 0], [10, 10], [0, 10]]

describe('addVertex', () => {
  it('aggiunge e rifiuta', () => {
    expect(addVertex([], [1, 2])).toEqual([[1, 2]])
    const full = Array.from({ length: ZONE_MAX }, (_, i) => [i / 10, i / 10] as ZonePoint)
    expect(addVertex(full, [50, 50])).toBe(full)
    expect(addVertex([[1, 2]], [1, 2])).toEqual([[1, 2]])
    expect(addVertex([[1, 2]], [5, 91])).toEqual([[1, 2]])
    expect(addVertex([[1, 2]], [181, 5])).toEqual([[1, 2]])
  })
})

describe('moveVertex / removeVertex', () => {
  it('non mutano e ignorano indici non validi', () => {
    const z = [...square]
    const m = moveVertex(z, 1, [5, 5])
    expect(m[1]).toEqual([5, 5])
    expect(z[1]).toEqual([10, 0])
    expect(moveVertex(z, 9, [1, 1])).toBe(z)
    expect(moveVertex(z, -1, [1, 1])).toBe(z)
    expect(removeVertex(z, 0)).toHaveLength(3)
    expect(z).toHaveLength(4)
    expect(removeVertex(z, 7)).toBe(z)
  })
})

describe('zoneError', () => {
  it('casi', () => {
    expect(zoneError([[0, 0], [1, 1]])).toBe('tooFew')
    expect(zoneError(Array.from({ length: 65 }, (_, i) => [i, 0] as ZonePoint))).toBe('tooMany')
    expect(zoneError(square)).toBeNull()
    expect(zoneError([[0, 0], [10, 10], [10, 0], [0, 10]])).toBe('selfIntersect')
    expect(zoneError([[0, 0], [10, 0], [5, 100]])).toBe('range')
  })
  it('un triangolo e un poligono concavo sono validi', () => {
    expect(zoneError([[0, 0], [10, 0], [5, 8]])).toBeNull()
    expect(zoneError([[0, 0], [10, 0], [10, 10], [5, 3], [0, 10]])).toBeNull()
  })
})

describe('ZoneEditor: props del contratto', () => {
  const files = import.meta.glob('/src/lib/map/ZoneEditor.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
  const text = Object.values(files)[0]
  it('solo value (bindable) e onchange; nodi ignorati esclusi', () => {
    expect(text).toContain('value = $bindable<[number, number][] | null>(null)')
    expect(text).toContain('onchange?: (polygon: [number, number][] | null) => void')
    expect(text).toContain('visibleNodes(')
    expect(text).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })
})

describe('zoneGeoJSON / zoneBounds', () => {
  it('chiude l\'anello; due punti = linea; vuoto', () => {
    const g = zoneGeoJSON(square)
    const poly = g.features.find((f) => f.geometry.type === 'Polygon')!
    const ring = (poly.geometry as { coordinates: number[][][] }).coordinates[0]
    expect(ring[0]).toEqual(ring[ring.length - 1])
    expect(ring).toHaveLength(5)
    expect(zoneGeoJSON([[0, 0], [1, 1]]).features.some((f) => f.geometry.type === 'LineString')).toBe(true)
    expect(zoneGeoJSON([]).features).toHaveLength(0)
  })
  it('bounds', () => {
    expect(zoneBounds(square)).toEqual([[0, 0], [10, 10]])
    expect(zoneBounds([])).toBeNull()
  })
})
