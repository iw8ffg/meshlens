import { afterEach, describe, expect, it } from 'vitest'
import { daysLabel, levelOf, statusLabel, statusTone, uptimeLabel } from './autonomy'
import { setLang } from './i18n/index.svelte'
import type { HealthNode } from './types'

afterEach(() => setLang('it'))

const hn =(over: Partial<HealthNode> = {}): HealthNode => ({
  node_id: '!00000001', name: 'A', is_mine: true, is_favorite: false, battery: 50, samples: 70,
  last_sample: 1, voltage: null, current_ma: null, uptime_s: null, reboots: 0, status: 'stable',
  level: 50, slope_per_day: 0, days_left: null, solar: false, solar_trend: null, solar_peak: null, ...over,
})

describe('daysLabel', () => {
  it('circa N giorni', () => {
    expect(daysLabel(6.0)).toBe('circa 6 giorni')
    expect(daysLabel(1.4)).toBe('circa 1 giorno')
    expect(daysLabel(0.96)).toBe('meno di 1 giorno')
    expect(daysLabel(0)).toBe('meno di 1 giorno')
    setLang('en')
    expect(daysLabel(6)).toBe('about 6 days')
    expect(daysLabel(1.2)).toBe('about 1 day')
    expect(daysLabel(0.5)).toBe('less than 1 day')
  })
})

describe('statusLabel e statusTone', () => {
  it('per ogni stato', () => {
    expect(statusLabel(hn({ status: 'falling', days_left: 6 }))).toBe('circa 6 giorni')
    expect(statusLabel(hn({ status: 'charging' }))).toBe('in carica')
    expect(statusLabel(hn({ status: 'stable' }))).toBe('stabile')
    expect(statusLabel(hn({ status: 'insufficient' }))).toBe('dati insufficienti')
    expect(statusLabel(hn({ status: 'external' }))).toBe('alimentazione esterna')
    expect(statusLabel(hn({ status: 'solar', solar: true, solar_trend: 'charging' }))).toBe('in carica')
    expect(statusLabel(hn({ status: 'solar', solar: true, solar_trend: 'falling' }))).toBe('in calo')
    expect(statusLabel(hn({ status: 'solar', solar: true, solar_trend: 'stable' }))).toBe('stabile')
    expect(statusLabel(hn({ status: 'solar', solar: true, solar_trend: null }))).toBe('dati insufficienti')
  })
  it('toni', () => {
    expect(statusTone(hn({ status: 'falling', days_left: 2 }))).toBe('warn')
    expect(statusTone(hn({ status: 'falling', days_left: 3 }))).toBe('warn')
    expect(statusTone(hn({ status: 'falling', days_left: 6 }))).toBe('muted')
    expect(statusTone(hn({ status: 'solar', solar_trend: 'falling' }))).toBe('warn')
    expect(statusTone(hn({ status: 'charging' }))).toBe('ok')
    expect(statusTone(hn({ status: 'solar', solar_trend: 'charging' }))).toBe('ok')
    expect(statusTone(hn({ status: 'stable' }))).toBe('muted')
    expect(statusTone(hn({ status: 'external' }))).toBe('muted')
  })
})

describe('uptimeLabel e levelOf', () => {
  it('formati', () => {
    expect(uptimeLabel(null)).toBe('—')
    expect(uptimeLabel(90000)).toBe('1 g 1 h')
    expect(uptimeLabel(3720)).toBe('1 h 2 min')
    expect(uptimeLabel(1800)).toBe('30 min')
    setLang('en')
    expect(uptimeLabel(90000)).toBe('1d 1h')
  })
  it('levelOf', () => {
    expect(levelOf(hn({ level: 42.5 }))).toBe(42.5)
    expect(levelOf(hn({ level: null, battery: 80 }))).toBe(80)
    expect(levelOf(hn({ level: null, battery: 101 }))).toBeNull()
    expect(levelOf(hn({ level: null, battery: null }))).toBeNull()
  })
})
