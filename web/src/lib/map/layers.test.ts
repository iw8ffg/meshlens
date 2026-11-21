import { describe, expect, it } from 'vitest'
import { ageMinutes, contactColorExpr, isMine, nodeFeatures, precisionData, ringKind, selectionData } from './NodeLayer'
import { snrColorExpr } from './LinkLayer'
import { trackData } from './TrackLayer'
import { FALLBACK_TOKENS as T } from './tokens'
import type { Node } from '../types'

const node = (o: Partial<Node>): Node =>
  ({ id: '!a', num: 1, long_name: null, short_name: null, hw_model: null, role: null, firmware: null, lat: 45, lon: 9, precision_bits: null, position_source: null, position_time: null, country: null, last_heard: 1000, sources: ['rf'], battery: null, voltage: null, channel_util: null, air_util_tx: null, mqtt_gateways: 0, last_snr: null, hops: null, ...o }) as Node

describe('nodi', () => {
  it('fonte: solo RF, solo MQTT, entrambe', () => {
    expect(ringKind({ sources: ['rf'] })).toBe('radio')
    expect(ringKind({ sources: ['mqtt'] })).toBe('mqtt')
    expect(ringKind({ sources: ['rf', 'mqtt'] })).toBe('both')
  })
  it('eta in minuti, mai sentito molto grande', () => {
    expect(ageMinutes(1000, 1000 + 600)).toBe(10)
    expect(ageMinutes(null, 5)).toBeGreaterThan(1e8)
  })
  it('mio nodo: is_mine o radio locale', () => {
    expect(isMine({ is_mine: true })).toBe(true)
    expect(isMine({ is_local_radio: true })).toBe(true)
    expect(isMine({})).toBe(false)
  })
  it('feature solo con posizione', () => {
    const f = nodeFeatures([node({}), node({ id: '!b', lat: null, lon: null }), node({ id: '!c', is_mine: true })], 1600)
    expect(f.map((x) => x.properties!.id)).toEqual(['!a', '!c'])
    expect(f[1].properties).toMatchObject({ mine: true, origin: 'radio', age_min: 10 })
  })
  it('selezione e precisione', () => {
    expect(selectionData(undefined, 0).features).toHaveLength(0)
    expect(selectionData(node({}), 2000).features).toHaveLength(1)
    expect(precisionData(node({ precision_bits: 13 })).features).toHaveLength(1)
    expect(precisionData(node({ precision_bits: 32 })).features).toHaveLength(0)
  })
  it('colore di contatto: step a 120 e 1440 min con i token', () => {
    expect(contactColorExpr(T)).toEqual(['step', ['get', 'age_min'], T.contactFresh, 120, T.contactRecent, 1440, T.contactOld])
  })
})

describe('collegamenti e traccia', () => {
  it('SNR: step a -10 e 0, none se manca', () => {
    expect(snrColorExpr(T)).toEqual([
      'case',
      ['==', ['typeof', ['get', 'snr']], 'number'],
      ['step', ['get', 'snr'], T.snrBad, -10, T.snrMid, 0, T.snrGood],
      T.snrNone,
    ])
  })
  it('traccia vuota con meno di 2 punti', () => {
    expect(trackData(null)).toMatchObject({ type: 'FeatureCollection' })
    expect(trackData([[1, 2]])).toMatchObject({ type: 'FeatureCollection' })
    expect(trackData([[1, 2], [3, 4]])).toMatchObject({ type: 'Feature' })
  })
})
