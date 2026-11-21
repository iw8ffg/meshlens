import { describe, expect, it } from 'vitest'
import { defaultChannel, isLikelyPublic, jobText, WINDOW_OPTIONS, type SfJob } from './storeforward'

const job = (o: Partial<SfJob>): SfJob => ({
  id: 'j', radio_id: 'r1', router_id: '!a1b2c3d4', window_min: 240, channel_index: 1,
  status: 'receiving', expected: null, received: 0, duplicates: 0, error: null, started: 1, ended: null, ...o,
})

describe('defaultChannel', () => {
  it('sceglie il primo secondario, altrimenti 0', () => {
    expect(defaultChannel([{ index: 0, role: 'PRIMARY' }, { index: 2, role: 'SECONDARY' }])).toBe(2)
    expect(defaultChannel([{ index: 0, role: 'PRIMARY' }])).toBe(0)
    expect(defaultChannel([])).toBe(0)
  })
})

describe('isLikelyPublic', () => {
  it('primario con nome preset o vuoto', () => {
    expect(isLikelyPublic({ index: 0, name: 'LongFast', role: 'PRIMARY' })).toBe(true)
    expect(isLikelyPublic({ index: 0, name: '', role: 'PRIMARY' })).toBe(true)
    expect(isLikelyPublic({ index: 0, name: 'Casa', role: 'PRIMARY' })).toBe(false)
    expect(isLikelyPublic({ index: 1, name: 'Club', role: 'SECONDARY' })).toBe(false)
    expect(isLikelyPublic({ index: 1, name: 'LongFast', role: 'SECONDARY' })).toBe(false)
  })
})

describe('jobText', () => {
  it('waiting', () => expect(jobText(job({ status: 'waiting' }))).toBe('In attesa del router…'))
  it('receiving', () => {
    expect(jobText(job({ received: 3, expected: 12 }))).toBe('Ricevuti 3 di 12')
    expect(jobText(job({ received: 3, expected: 12, duplicates: 2 }))).toBe('Ricevuti 3 di 12, 2 già presenti')
    expect(jobText(job({ received: 3 }))).toBe('Ricevuti 3')
    expect(jobText(job({ received: 3, duplicates: 1 }))).toBe('Ricevuti 3, 1 già presenti')
  })
  it('done', () => {
    expect(jobText(job({ status: 'done', received: 5 }))).toBe('Completato: 5 messaggi recuperati')
    expect(jobText(job({ status: 'done', received: 5, duplicates: 2 }))).toBe('Completato: 5 messaggi recuperati, 2 già presenti')
    expect(jobText(job({ status: 'done' }))).toBe('Nessun messaggio da recuperare')
    expect(jobText(job({ status: 'done', duplicates: 2 }))).toBe('Completato: 0 messaggi recuperati, 2 già presenti')
  })
  it('failed', () => expect(jobText(job({ status: 'failed', error: 'Nessuna risposta dal router' }))).toBe('Nessuna risposta dal router'))
})

describe('WINDOW_OPTIONS', () => {
  it('quattro finestre', () => expect(WINDOW_OPTIONS.map((o) => o.min)).toEqual([60, 240, 720, 1440]))
})
