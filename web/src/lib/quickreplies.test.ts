import { describe, expect, it } from 'vitest'
import { expandVariables, hasUnresolvedVariables, insertReply, ownNodeId, validateQuickReply, variablesIn } from './quickreplies'
import type { Radio } from './types'

const radio = (over: Partial<Radio>): Radio =>
  ({ id: 'r1', name: 'R', kind: 'usb', address: '', auto_connect: true, state: 'connected', error: null, my_node_id: '!00000001', my_node_name: null, channels: [], ...over }) as Radio

describe('validateQuickReply', () => {
  it('applica le regole del server', () => {
    expect(validateQuickReply('', [])).toBe('empty')
    expect(validateQuickReply(' x', [])).toBe('edges')
    expect(validateQuickReply('x ', [])).toBe('edges')
    expect(validateQuickReply('è'.repeat(101), [])).toBe('tooLong')
    expect(validateQuickReply('è'.repeat(100), [])).toBeNull()
    expect(validateQuickReply('a\nb', [])).toBe('control')
    expect(validateQuickReply('ok', ['ok'])).toBe('duplicate')
    expect(validateQuickReply('Arrivo {ora}', [])).toBeNull()
  })
})

describe('expandVariables', () => {
  const now = new Date(2026, 10, 23, 9, 5)
  it('sostituisce batteria e ora', () => {
    const r = expandVariables('Batteria {batteria}, ore {ora}', { node: { battery: 87, lat: null, lon: null }, now })
    expect(r).toEqual({ text: 'Batteria 87%, ore 09:05', missing: [] })
  })
  it('posizione a 5 decimali con il punto', () => {
    expect(expandVariables('{posizione}', { node: { battery: null, lat: 45.123456, lon: 9.1 }, now }).text).toBe('45.12346, 9.10000')
  })
  it('lascia intatta una variabile non risolvibile', () => {
    const r = expandVariables('B {batteria}', { node: { battery: null, lat: null, lon: null }, now })
    expect(r.text).toBe('B {batteria}')
    expect(r.missing).toEqual(['batteria'])
    expect(expandVariables('B {batteria}', { node: { battery: 101, lat: null, lon: null }, now }).missing).toEqual(['batteria'])
  })
  it('sostituisce tutte le occorrenze', () => {
    expect(expandVariables('{ora} e {ora}', { node: null, now }).text).toBe('09:05 e 09:05')
  })
  it('senza nodo mancano batteria e posizione, non l\'ora', () => {
    const r = expandVariables('{batteria} {posizione} {ora}', { node: null, now })
    expect(r.missing).toEqual(['batteria', 'posizione'])
    expect(r.text).toBe('{batteria} {posizione} 09:05')
  })
  it('una variabile sconosciuta resta com\'e\'', () => {
    const r = expandVariables('{altro}', { node: null, now })
    expect(r).toEqual({ text: '{altro}', missing: [] })
    expect(variablesIn('{altro}')).toEqual([])
    expect(variablesIn('{ora} {batteria}')).toEqual(['batteria', 'ora'])
  })
})

describe('hasUnresolvedVariables', () => {
  it('rileva solo le variabili note', () => {
    expect(hasUnresolvedVariables('ok {batteria}')).toBe(true)
    expect(hasUnresolvedVariables('ok')).toBe(false)
    expect(hasUnresolvedVariables('{altro}')).toBe(false)
  })
})

describe('ownNodeId', () => {
  const radios = [radio({ id: 'r1', my_node_id: '!00000001' }), radio({ id: 'r2', my_node_id: '!00000002', state: 'disconnected' })]
  it('radio scelta', () => {
    expect(ownNodeId('radio:r2', radios, '')).toBe('!00000002')
    expect(ownNodeId('radio:zz', radios, '')).toBeNull()
  })
  it('mqtt con id proprio o ripiego sulla prima radio collegata', () => {
    expect(ownNodeId('mqtt', radios, '!0000abcd')).toBe('!0000abcd')
    expect(ownNodeId('mqtt', radios, '')).toBe('!00000001')
    expect(ownNodeId('mqtt', [], '')).toBeNull()
    expect(ownNodeId('boh', radios, '')).toBeNull()
  })
})

describe('inserimento nel campo', () => {
  it('campo vuoto: sostituisce; altrimenti accoda con uno spazio', () => {
    expect(insertReply('', 'Sto bene')).toBe('Sto bene')
    expect(insertReply('   ', 'Sto bene')).toBe('Sto bene')
    expect(insertReply('Ciao', 'Sto bene')).toBe('Ciao Sto bene')
    expect(insertReply('Ciao ', 'Sto bene')).toBe('Ciao Sto bene')
  })
})
