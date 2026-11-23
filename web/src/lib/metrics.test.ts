import { afterEach, describe, expect, it } from 'vitest'
import { setLang } from './i18n/index.svelte'
import { dupeRatio, formatMetric, metricInfo, orderMetrics } from './metrics'

describe('metricInfo', () => {
  it('catalogo e ripiego', () => {
    expect(metricInfo('environment.temperature').label).toBe('Temperatura')
    const u = metricInfo('foo.bar')
    expect(u.label).toBe('foo.bar')
    expect(u.digits).toBe(2)
    expect(u.chart).toBe(true)
  })
})

describe('orderMetrics', () => {
  it('per variante, poi catalogo, poi alfabetico', () => {
    expect(orderMetrics(['local_stats.num_rx_dupe', 'air_quality.co2', 'environment.temperature'])).toEqual([
      'environment.temperature',
      'air_quality.co2',
      'local_stats.num_rx_dupe',
    ])
    expect(orderMetrics(['x.b', 'environment.lux', 'x.a', 'environment.temperature'])).toEqual([
      'environment.temperature',
      'environment.lux',
      'x.a',
      'x.b',
    ])
  })
})

describe('formatMetric', () => {
  it('numero italiano con meno tipografico e unita', () => {
    expect(formatMetric('environment.temperature', -3.25)).toBe('−3,3 °C')
    expect(formatMetric('environment.iaq', 42)).toBe('42')
  })
})

describe('Paxcounter (1.6)', () => {
  afterEach(() => setLang('it'))
  it('etichette in area sensors, in italiano e in inglese', () => {
    expect(metricInfo('paxcounter.wifi')).toMatchObject({ unit: '', digits: 0, label: 'Dispositivi Wi-Fi' })
    expect(metricInfo('paxcounter.uptime').chart).toBe(false)
    setLang('en')
    expect(metricInfo('paxcounter.wifi').label).toBe('Wi-Fi devices')
  })
  it('ordine: ambiente, potenza, paxcounter', () => {
    expect(orderMetrics(['paxcounter.wifi', 'power.ch1_voltage', 'environment.lux'])).toEqual([
      'environment.lux',
      'power.ch1_voltage',
      'paxcounter.wifi',
    ])
  })
  it('formatMetric', () => {
    expect(formatMetric('paxcounter.wifi', 12)).toBe('12')
    expect(formatMetric('paxcounter.uptime', 60)).toBe('60 s')
  })
})

describe('dupeRatio', () => {
  it('rapporto o null', () => {
    expect(dupeRatio({ 'local_stats.num_rx_dupe': { value: 12, time: 0 }, 'local_stats.num_packets_rx': { value: 100, time: 0 } })).toBe(0.12)
    expect(dupeRatio({ 'local_stats.num_rx_dupe': { value: 12, time: 0 } })).toBeNull()
    expect(dupeRatio({ 'local_stats.num_rx_dupe': { value: 12, time: 0 }, 'local_stats.num_packets_rx': { value: 0, time: 0 } })).toBeNull()
  })
})
