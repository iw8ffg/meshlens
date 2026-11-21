import { describe, expect, it } from 'vitest'
import { loadView, saveView, VIEW_KEY, type ViewState } from './viewstate'

function mem(init: Record<string, string> = {}) {
  const data = new Map(Object.entries(init))
  return {
    data,
    getItem: (k: string) => data.get(k) ?? null,
    setItem: (k: string, v: string) => void data.set(k, v),
  }
}

const DEFAULTS: ViewState = { tab: null, map: null, conv: null, netSort: null, nodeSort: 'recent', cluster: true, waypoints: true }

describe('loadView', () => {
  it('waypoints: assente true, false salvato false, valore non booleano true', () => {
    expect(loadView(mem({ [VIEW_KEY]: JSON.stringify({ v: 1 }) })).waypoints).toBe(true)
    expect(loadView(mem({ [VIEW_KEY]: JSON.stringify({ v: 1, waypoints: false }) })).waypoints).toBe(false)
    expect(loadView(mem({ [VIEW_KEY]: JSON.stringify({ v: 1, waypoints: 'no' }) })).waypoints).toBe(true)
  })
  it('storage vuoto o assente: predefiniti', () => {
    expect(loadView(mem())).toEqual(DEFAULTS)
    expect(loadView(null)).toEqual(DEFAULTS)
  })
  it('JSON rotto: predefiniti', () => {
    expect(loadView(mem({ [VIEW_KEY]: '{rotto' }))).toEqual(DEFAULTS)
  })
  it('lat fuori intervallo: map null, gli altri campi restano', () => {
    const s = mem({
      [VIEW_KEY]: JSON.stringify({ v: 1, tab: 'chat', map: { lon: 10, lat: 120, zoom: 5 }, conv: 'mqtt', nodeSort: 'snr' }),
    })
    expect(loadView(s)).toEqual({ ...DEFAULTS, tab: 'chat', conv: 'mqtt', nodeSort: 'snr' })
  })
  it('lon e zoom fuori intervallo: map null', () => {
    expect(loadView(mem({ [VIEW_KEY]: JSON.stringify({ v: 1, map: { lon: 181, lat: 0, zoom: 5 } }) })).map).toBeNull()
    expect(loadView(mem({ [VIEW_KEY]: JSON.stringify({ v: 1, map: { lon: 0, lat: 0, zoom: 23 } }) })).map).toBeNull()
  })
  it('scheda sconosciuta: tab null', () => {
    expect(loadView(mem({ [VIEW_KEY]: JSON.stringify({ v: 1, tab: 'boh', conv: 'mqtt' }) }))).toEqual({ ...DEFAULTS, conv: 'mqtt' })
  })
  it('ordinamenti e raggruppamento non validi: predefiniti', () => {
    const s = mem({ [VIEW_KEY]: JSON.stringify({ v: 1, netSort: { key: 'x', dir: 'asc' }, nodeSort: 'x', cluster: 'no' }) })
    expect(loadView(s)).toEqual(DEFAULTS)
  })
  it('versione diversa da 1: predefiniti', () => {
    expect(loadView(mem({ [VIEW_KEY]: JSON.stringify({ v: 2, tab: 'chat' }) }))).toEqual(DEFAULTS)
  })
})

describe('saveView', () => {
  it('giro completo su tutti i campi', () => {
    const s = mem()
    const v: ViewState = {
      tab: 'network',
      map: { lon: 9.18951, lat: 45.46427, zoom: 11.5 },
      conv: 'dm:r1:!0000abcd',
      netSort: { key: 'snr', dir: 'asc' },
      nodeSort: 'distance',
      cluster: false,
      waypoints: false,
    }
    saveView(s, v)
    expect(JSON.parse(s.data.get(VIEW_KEY)!).v).toBe(1)
    expect(loadView(s)).toEqual(v)
  })
  it('le scritture parziali si uniscono', () => {
    const s = mem()
    saveView(s, { tab: 'chat' })
    saveView(s, { conv: 'mqtt' })
    expect(loadView(s)).toEqual({ ...DEFAULTS, tab: 'chat', conv: 'mqtt' })
  })
  it('storage che lancia: nessuna eccezione', () => {
    const s = {
      getItem: () => {
        throw new Error('no')
      },
      setItem: () => {
        throw new Error('pieno')
      },
    }
    expect(() => saveView(s, { tab: 'chat' })).not.toThrow()
    expect(() => saveView(null, { tab: 'chat' })).not.toThrow()
    expect(loadView(s)).toEqual(DEFAULTS)
  })
})
