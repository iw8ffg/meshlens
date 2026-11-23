import { describe, expect, it } from 'vitest'
import { searchNodes } from './search'
import type { Node } from '../types'

const node = (o: Partial<Node>): Node =>
  ({ id: '!00000001', num: 1, long_name: null, short_name: null, hw_model: null, role: null, lat: 45, lon: 9, last_heard: 1000, ...o }) as Node

describe('searchNodes', () => {
  it('id con o senza punto esclamativo', () => {
    const nodes = [node({ id: '!11111111', long_name: 'Altro' }), node({ id: '!a1b2c3d4', long_name: 'Zeta' })]
    expect(searchNodes(nodes, '!a1b2c3d4')[0].id).toBe('!a1b2c3d4')
    expect(searchNodes(nodes, 'a1b2c3d4')[0].id).toBe('!a1b2c3d4')
  })
  it('nome breve prima del nome lungo', () => {
    const nodes = [node({ id: '!1', long_name: 'Abmonte', short_name: 'XX' }), node({ id: '!2', short_name: 'BM', long_name: 'Altro' })]
    expect(searchNodes(nodes, 'bm').map((n) => n.id)).toEqual(['!2', '!1'])
  })
  it('senza maiuscole né accenti', () => {
    expect(searchNodes([node({ long_name: 'Città Alta' })], 'citta')).toHaveLength(1)
  })
  it('trova per modello hardware', () => {
    expect(searchNodes([node({ hw_model: 'HELTEC_V3' })], 'heltec')).toHaveLength(1)
  })
  it('esclude i nodi senza posizione', () => {
    expect(searchNodes([node({ long_name: 'Base', lat: null, lon: null })], 'base')).toEqual([])
  })
  it('ricerca vuota', () => {
    expect(searchNodes([node({ long_name: 'Base' })], '  ')).toEqual([])
  })
  it('a parità vince il contatto più recente', () => {
    const nodes = [node({ id: '!1', long_name: 'Base A', last_heard: 10 }), node({ id: '!2', long_name: 'Base B', last_heard: 20 })]
    expect(searchNodes(nodes, 'base').map((n) => n.id)).toEqual(['!2', '!1'])
  })
  it('rispetta il limite', () => {
    const nodes = Array.from({ length: 10 }, (_, i) => node({ id: `!${i}`, long_name: `Base ${i}` }))
    expect(searchNodes(nodes, 'base', 3)).toHaveLength(3)
  })
})

describe('nodi ignorati', () => {
  it('non compaiono nella ricerca sulla mappa', () => {
    const list = [node({ id: '!00000001', short_name: 'AB' }), node({ id: '!00000002', short_name: 'AC', is_ignored: true })]
    expect(searchNodes(list, 'a').map((n) => n.id)).toEqual(['!00000001'])
  })
})
