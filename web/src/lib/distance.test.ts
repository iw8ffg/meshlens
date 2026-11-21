import { expect, test } from 'vitest'
import { bearingDeg, cardinal, haversineM, myOrigin } from './distance'
import type { Node, Radio } from './types'

const node = (id: string, lat: number | null, lon: number | null, extra: Partial<Node> = {}) => ({ id, lat, lon, ...extra }) as Node
const radio = (id: string, state: string, my: string | null) => ({ id, name: `R-${id}`, state, my_node_id: my }) as Radio

test('haversine Milano-Roma', () => {
  const d = haversineM({ lat: 45.4642, lon: 9.19 }, { lat: 41.9028, lon: 12.4964 })
  expect(d).toBeGreaterThan(476_000)
  expect(d).toBeLessThan(478_000)
})

test('haversine di un punto con se stesso è 0', () => {
  const p = { lat: 44, lon: 11 }
  expect(haversineM(p, p)).toBe(0)
})

test('bearing', () => {
  expect(bearingDeg({ lat: 0, lon: 0 }, { lat: 1, lon: 0 })).toBeCloseTo(0, 3)
  expect(bearingDeg({ lat: 0, lon: 0 }, { lat: 0, lon: 1 })).toBeCloseTo(90, 3)
})

test('cardinal', () => {
  expect(cardinal(350)).toBe('N')
  expect(cardinal(225)).toBe('SO')
})

test('myOrigin: la radio connessa vince sul browser', () => {
  const nodes = new Map([['!a', node('!a', 45, 9)]])
  const o = myOrigin(nodes, [radio('r1', 'connected', '!a')], { lat: 1, lon: 1 })
  expect(o).toEqual({ lat: 45, lon: 9, label: 'dalla radio R-r1' })
})

test('myOrigin: radio senza posizione, ricade sul browser', () => {
  const nodes = new Map([['!a', node('!a', null, null)]])
  const o = myOrigin(nodes, [radio('r1', 'connected', '!a')], { lat: 1, lon: 2 })
  expect(o).toEqual({ lat: 1, lon: 2, label: 'dalla tua posizione' })
})

test('myOrigin: nodo is_local_radio con posizione', () => {
  const nodes = new Map([['!b', node('!b', 40, 10, { is_local_radio: true })]])
  expect(myOrigin(nodes, [], null)?.label).toBe('dalla tua radio')
})

test('myOrigin: niente -> null', () => {
  expect(myOrigin(new Map(), [radio('r1', 'disconnected', '!a')], null)).toBeNull()
})
