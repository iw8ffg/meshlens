import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  COMPARE_COLORS,
  COMPARE_MAX,
  COMPARE_METRICS,
  compareMeta,
  compareSeries,
  extentOf,
  healthBatteries,
  sortHealth,
  splitHealth,
  toggleCompare,
} from './health'
import type { HealthNode, SnrPoint, TelemetryPoint } from './types'

afterEach(() => vi.unstubAllGlobals())

const hn = (over: Partial<HealthNode> = {}): HealthNode => ({
  node_id: '!00000001', name: 'A', is_mine: true, is_favorite: false, battery: 50, samples: 70,
  last_sample: 1, voltage: null, current_ma: null, uptime_s: null, reboots: 0, status: 'stable',
  level: 50, slope_per_day: 0, days_left: null, solar: false, solar_trend: null, solar_peak: null, ...over,
})

describe('toggleCompare', () => {
  it('aggiunge fino a 3, toglie, non muta', () => {
    const a: string[] = []
    const b = toggleCompare(a, 'x')
    expect(b).toEqual(['x'])
    expect(a).toEqual([])
    const c = toggleCompare(toggleCompare(b, 'y'), 'z')
    expect(c).toEqual(['x', 'y', 'z'])
    expect(toggleCompare(c, 'w')).toBe(c)
    expect(toggleCompare(c, 'y')).toEqual(['x', 'z'])
    expect(COMPARE_MAX).toBe(3)
    expect(COMPARE_METRICS).toHaveLength(5)
    expect(COMPARE_COLORS).toHaveLength(3)
  })
})

describe('sortHealth e splitHealth', () => {
  const set = [
    hn({ node_id: '1', name: 'insufficiente', status: 'insufficient', level: null, battery: null }),
    hn({ node_id: '2', name: 'esterna', status: 'external', level: null, battery: 101 }),
    hn({ node_id: '3', name: 'stabile80', status: 'stable', level: 80 }),
    hn({ node_id: '4', name: 'stabile40', status: 'stable', level: 40 }),
    hn({ node_id: '5', name: 'solare in carica', status: 'solar', solar: true, solar_trend: 'charging', level: 55 }),
    hn({ node_id: '6', name: 'solare in calo', status: 'solar', solar: true, solar_trend: 'falling', level: 60 }),
    hn({ node_id: '7', name: 'in calo 6', status: 'falling', days_left: 6, level: 50 }),
    hn({ node_id: '8', name: 'in calo 2', status: 'falling', days_left: 2, level: 20 }),
    hn({ node_id: '9', name: 'solare stabile', status: 'solar', solar: true, solar_trend: 'stable', level: 70 }),
  ]
  it('ordine', () => {
    // in calo (meno giorni prima), solare in calo, solare stabile, resto per livello, esterna/insufficiente in fondo
    expect(sortHealth(set).map((n) => n.node_id)).toEqual(['8', '7', '6', '9', '4', '5', '3', '2', '1'])
  })
  it('non muta e a parità ordina per nome', () => {
    const copy = [...set]
    sortHealth(set)
    expect(set).toEqual(copy)
    const same = [hn({ node_id: 'b', name: 'B' }), hn({ node_id: 'a', name: 'A' })]
    expect(sortHealth(same).map((n) => n.name)).toEqual(['A', 'B'])
  })
  it('splitHealth', () => {
    const { attention, others } = splitHealth(set)
    expect(attention.map((n) => n.node_id)).toEqual(['8', '7', '6'])
    expect(others.map((n) => n.node_id)).toEqual(['9', '4', '5', '3', '2', '1'])
  })
})

describe('compareSeries e compareMeta', () => {
  const tel: TelemetryPoint[] = [
    { time: 1, battery: 80, voltage: 3.9, channel_util: 10, air_util_tx: 1 },
    { time: 2, battery: 101, voltage: null, channel_util: null, air_util_tx: 2 },
  ]
  const snr: SnrPoint[] = [
    { time: 1, source: 'rf', snr_avg: -5, snr_max: -3, packets: 4 },
    { time: 2, source: 'mqtt', snr_avg: 3, snr_max: 4, packets: 1 },
  ]
  it('serie per grandezza', () => {
    expect(compareSeries('battery', tel, snr)).toEqual([{ t: 1, v: 80 }, { t: 2, v: null }])
    expect(compareSeries('voltage', tel, snr)).toEqual([{ t: 1, v: 3.9 }, { t: 2, v: null }])
    expect(compareSeries('channel_util', tel, snr)).toEqual([{ t: 1, v: 10 }, { t: 2, v: null }])
    expect(compareSeries('air_util_tx', tel, snr)).toEqual([{ t: 1, v: 1 }, { t: 2, v: 2 }])
    expect(compareSeries('snr', tel, snr)).toEqual([{ t: 1, v: -5 }])
  })
  it('meta', () => {
    expect(compareMeta('battery').fixedRange).toEqual([0, 100])
    expect(compareMeta('voltage')).toMatchObject({ unit: 'V', digits: 2 })
    expect(compareMeta('snr').fixedRange).toBeUndefined()
  })
})

describe('extentOf e healthBatteries', () => {
  it('estremi', () => {
    expect(extentOf([])).toEqual([0, 1])
    expect(extentOf([[{ t: 5, v: null }]])).toEqual([0, 1])
    expect(extentOf([[{ t: 5, v: 1 }, { t: 9, v: null }], [{ t: 3, v: 2 }, { t: 7, v: 1 }]])).toEqual([3, 7])
  })
  it('healthBatteries chiama la rotta', async () => {
    const fn = vi.fn(async () => new Response('{}', { status: 200 }))
    vi.stubGlobal('fetch', fn)
    await healthBatteries('all')
    expect((fn.mock.calls[0] as unknown as [string])[0]).toBe('/api/health/batteries?scope=all')
  })
})
