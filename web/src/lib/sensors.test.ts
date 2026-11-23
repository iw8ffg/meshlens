import { afterEach, describe, expect, it, vi } from 'vitest'
import { eventLabel, groupByDay, hasPax, mergeLive, paxSeries, sensorEvents } from './sensors'
import { setLang } from './i18n/index.svelte'
import type { SensorEvent } from './types'

afterEach(() => {
  vi.unstubAllGlobals()
  setLang('it')
})

const ev = (id: number, time: number, over: Partial<SensorEvent> = {}): SensorEvent => ({
  id, node_id: '!00000001', time, kind: 'detection', text: 'Porta detected', value: 1, source: 'rf', ...over,
})

describe('paxSeries', () => {
  it('converte le serie e riconosce l’assenza', () => {
    const s = { 'paxcounter.wifi': [[10, 3], [20, 5]], 'paxcounter.ble': [[10, 1]] } as Record<string, [number, number][]>
    expect(paxSeries(s)).toEqual({ wifi: [{ t: 10, v: 3 }, { t: 20, v: 5 }], ble: [{ t: 10, v: 1 }] })
    expect(hasPax(s)).toBe(true)
    expect(paxSeries({})).toEqual({ wifi: [], ble: [] })
    expect(hasPax({ 'environment.lux': [[1, 2]] })).toBe(false)
  })
})

describe('eventLabel', () => {
  it('testo del sensore, oppure Rilevato/Cessato', () => {
    expect(eventLabel(ev(1, 1))).toBe('Porta detected')
    expect(eventLabel(ev(1, 1, { text: '', value: 1 }))).toBe('Rilevato')
    expect(eventLabel(ev(1, 1, { text: null, value: 0 }))).toBe('Cessato')
    expect(eventLabel(ev(1, 1, { text: null, value: null }))).toBe('Rilevato')
    setLang('en')
    expect(eventLabel(ev(1, 1, { text: null, value: 0 }))).toBe('Cleared')
  })
})

describe('groupByDay', () => {
  it('giorno locale, dal più recente', () => {
    const t = (d: number, h: number) => new Date(2026, 10, d, h).getTime() / 1000
    const groups = groupByDay([ev(1, t(22, 23)), ev(2, t(23, 8)), ev(3, t(23, 15))], t(23, 20))
    expect(groups).toHaveLength(2)
    expect(groups[0].dayStart).toBe(new Date(2026, 10, 23).getTime() / 1000)
    expect(groups[0].events.map((e) => e.id)).toEqual([3, 2])
    expect(groups[1].events.map((e) => e.id)).toEqual([1])
    expect(groupByDay([], 0)).toEqual([])
  })
})

describe('mergeLive', () => {
  it('in testa, senza duplicati, tagliata a max', () => {
    const list = [ev(2, 20), ev(1, 10)]
    expect(mergeLive(list, ev(3, 30)).map((e) => e.id)).toEqual([3, 2, 1])
    expect(mergeLive(list, ev(2, 20))).toBe(list)
    expect(mergeLive(list, ev(3, 30), 2).map((e) => e.id)).toEqual([3, 2])
    expect(list).toHaveLength(2)
  })
})

describe('sensorEvents', () => {
  it('chiama la rotta con l’id codificato', async () => {
    const fn = vi.fn(async () => new Response('[]', { status: 200 }))
    vi.stubGlobal('fetch', fn)
    await sensorEvents('!00000001')
    expect((fn.mock.calls[0] as unknown as [string])[0]).toBe('/api/nodes/!00000001/sensor-events?hours=168&limit=200')
    await sensorEvents('a b')
    expect((fn.mock.calls[1] as unknown as [string])[0]).toBe('/api/nodes/a%20b/sensor-events?hours=168&limit=200')
  })
})
