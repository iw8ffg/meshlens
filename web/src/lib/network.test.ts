import { describe, expect, it } from 'vitest'
import { batteryLabel, sortNodes } from './network'
import type { Node } from './types'

const n = (id: string, over: Partial<Node> = {}): Node =>
  ({ id, long_name: id, short_name: null, role: null, firmware: null, battery: null, ...over }) as Node

describe('sortNodes', () => {
  const list = [n('a', { battery: 50 }), n('b', { battery: null }), n('c', { battery: 90 })]
  it('mette i null in fondo in entrambe le direzioni', () => {
    expect(sortNodes(list, 'battery', 'asc').map((x) => x.id)).toEqual(['a', 'c', 'b'])
    expect(sortNodes(list, 'battery', 'desc').map((x) => x.id)).toEqual(['c', 'a', 'b'])
  })
  it('ordina per batteria decrescente', () => {
    expect(sortNodes(list, 'battery', 'desc')[0].id).toBe('c')
  })
  it('confronta il nome con localeCompare', () => {
    const l = [n('x', { long_name: 'Zeta' }), n('y', { long_name: 'alfa' })]
    expect(sortNodes(l, 'name', 'asc').map((x) => x.id)).toEqual(['y', 'x'])
  })
  it('non modifica l\'input', () => {
    const copy = [...list]
    sortNodes(list, 'battery', 'asc')
    expect(list).toEqual(copy)
  })
})

describe('batteryLabel', () => {
  it('101 e USB, null e trattino', () => {
    expect(batteryLabel(101)).toBe('USB')
    expect(batteryLabel(null)).toBe('—')
    expect(batteryLabel(55)).toBe('55%')
  })
})
