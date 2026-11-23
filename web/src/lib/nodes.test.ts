import { describe, expect, it } from 'vitest'
import { hopsLabel, networkNodes, alertText, alertsByNode, batteryView, contactMinutes, fmtOpt, nodeName, sourceKind, toggleIn } from './nodes'
import type { Alert } from './types'

describe('nodes', () => {
  it('nodeName ripiega su nome breve e id', () => {
    expect(nodeName({ long_name: 'Base', short_name: 'B', id: '!1' })).toBe('Base')
    expect(nodeName({ long_name: null, short_name: 'B', id: '!1' })).toBe('B')
    expect(nodeName({ long_name: '', short_name: null, id: '!1' })).toBe('!1')
  })
  it('sourceKind: radio, mqtt, entrambe, nessuna', () => {
    expect(sourceKind({ sources: ['rf'], mqtt_gateways: 0 })).toBe('radio')
    expect(sourceKind({ sources: ['mqtt'], mqtt_gateways: 1 })).toBe('mqtt')
    expect(sourceKind({ sources: ['rf', 'mqtt'], mqtt_gateways: 1 })).toBe('both')
    expect(sourceKind({ sources: [], mqtt_gateways: 2 })).toBe('mqtt')
    expect(sourceKind({ sources: [], mqtt_gateways: 0 })).toBeNull()
  })
  it('batteryView: 101 e USB', () => {
    expect(batteryView(null)).toBeNull()
    expect(batteryView(101)).toEqual({ pct: 100, usb: true })
    expect(batteryView(55)).toEqual({ pct: 55, usb: false })
  })
  it('contactMinutes', () => {
    expect(contactMinutes(null, 100)).toBeNull()
    expect(contactMinutes(40, 100)).toBe(1)
    expect(contactMinutes(200, 100)).toBe(0)
  })
  it('toggleIn non modifica l\'originale', () => {
    const a = ['rf']
    expect(toggleIn(a, 'mqtt')).toEqual(['rf', 'mqtt'])
    expect(toggleIn(a, 'rf')).toEqual([])
    expect(a).toEqual(['rf'])
  })
  it('alertText e alertsByNode', () => {
    const l: Alert = { key: 'a', kind: 'battery_low', node_id: '!1', node_name: 'X', value: 12, since: 1 }
    const s: Alert = { key: 'b', kind: 'silent', node_id: '!1', node_name: 'X', value: 30, since: 1 }
    expect(alertText(l)).toBe('Batteria al 12%')
    expect(alertText(s)).toBe('Silenzioso da 30 h')
    expect(alertsByNode([l, s]).get('!1')).toHaveLength(2)
  })
  it('fmtOpt: formato it-IT', () => {
    expect(fmtOpt(null)).toBe('–')
    expect(fmtOpt(3.59, 2, ' V')).toBe('3,59 V')
  })
})

describe('hopsLabel', () => {
  it('diretto, numero, almeno 1, ignoto', () => {
    expect(hopsLabel(0, null)).toBe('0 (diretto)')
    expect(hopsLabel(3)).toBe('3')
    expect(hopsLabel(null, 1)).toBe('≥ 1')
    expect(hopsLabel(null, null)).toBe('—')
    expect(hopsLabel(null)).toBe('—')
    expect(hopsLabel(2, 1)).toBe('2')
  })
})

describe('networkNodes', () => {
  const list = [{ is_mine: true, is_favorite: true }, { is_mine: true }, { is_favorite: true }, {}]
  it('filtri miei / preferiti in AND', () => {
    expect(networkNodes(list, false, false)).toHaveLength(4)
    expect(networkNodes(list, true, false)).toHaveLength(2)
    expect(networkNodes(list, false, true)).toHaveLength(2)
    expect(networkNodes(list, true, true)).toHaveLength(1)
  })
})

describe('networkNodes e nodi ignorati', () => {
  it('esclude sempre i nodi ignorati', () => {
    const list = [{ is_mine: true }, { is_mine: true, is_ignored: true }, {}]
    expect(networkNodes(list, false, false)).toHaveLength(2)
    expect(networkNodes(list, true, false)).toHaveLength(1)
  })
})
