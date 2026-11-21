import { expect, test } from 'vitest'
import { sortNodeList } from './nodesort'
import type { Origin } from './distance'
import type { Node } from './types'

const node = (id: string, extra: Partial<Node> = {}) => ({ id, long_name: null, short_name: null, last_heard: null, lat: null, lon: null, hops: null, hops_min: null, last_snr: null, ...extra }) as Node
const ids = (ns: Node[]) => ns.map((n) => n.id)
const MILANO: Origin = { lat: 45.4642, lon: 9.19, label: 'test' }

test('per nome con collazione italiana', () => {
  const nodes = [node('b', { long_name: 'b' }), node('acc', { long_name: 'À' }), node('a', { long_name: 'a' })]
  expect(ids(sortNodeList(nodes, 'name', null))).toEqual(['a', 'acc', 'b'])
})

test('per SNR decrescente, mancanti in fondo', () => {
  const nodes = [node('x', { last_snr: -5 }), node('n', { last_snr: null }), node('y', { last_snr: 3 })]
  expect(ids(sortNodeList(nodes, 'snr', null))).toEqual(['y', 'x', 'n'])
})

test('per salti crescenti, usa hops_min se hops manca', () => {
  const nodes = [node('two', { hops: 2 }), node('min', { hops: null, hops_min: 1 }), node('zero', { hops: 0 })]
  expect(ids(sortNodeList(nodes, 'hops', null))).toEqual(['zero', 'min', 'two'])
})

test('per distanza da origine: Monza prima di Roma, senza posizione in fondo', () => {
  const nodes = [
    node('roma', { lat: 41.9028, lon: 12.4964 }),
    node('nopos'),
    node('monza', { lat: 45.5845, lon: 9.2744 }),
  ]
  expect(ids(sortNodeList(nodes, 'distance', MILANO))).toEqual(['monza', 'roma', 'nopos'])
})

test('per distanza senza origine equivale a recente', () => {
  const nodes = [
    node('old', { last_heard: 100, lat: 45.5845, lon: 9.2744 }),
    node('never'),
    node('new', { last_heard: 300, lat: 41.9028, lon: 12.4964 }),
  ]
  expect(ids(sortNodeList(nodes, 'distance', null))).toEqual(ids(sortNodeList(nodes, 'recent', null)))
  expect(ids(sortNodeList(nodes, 'distance', null))).toEqual(['new', 'old', 'never'])
})

test('recente: più recenti prima, a parità criterio di ultimo contatto', () => {
  const nodes = [node('never'), node('old', { last_heard: 100 }), node('new', { last_heard: 300 })]
  expect(ids(sortNodeList(nodes, 'recent', null))).toEqual(['new', 'old', 'never'])
})

test('l\'input non viene modificato', () => {
  const nodes = [node('b', { long_name: 'b' }), node('a', { long_name: 'a' })]
  const copy = nodes.map((n) => ({ ...n }))
  sortNodeList(nodes, 'name', null)
  expect(nodes).toEqual(copy)
  expect(ids(nodes)).toEqual(['b', 'a'])
})
