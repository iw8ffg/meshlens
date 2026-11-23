import { afterEach, describe, expect, it } from 'vitest'
import { i18n } from './i18n/index.svelte'
import { it as itCat } from './i18n/it'
import { en as enCat } from './i18n/en'
import {
  clampInterval, diffRoute, failureMultiplier, intervalLabel, INTERVAL_OPTIONS, nextRunAt,
  routeLabel, statusKey,
} from './tracesched'

afterEach(() => {
  i18n.lang = 'it'
})

describe('clampInterval', () => {
  it('limita a 60..10080 minuti interi', () => {
    expect(clampInterval(10)).toBe(60)
    expect(clampInterval(99999)).toBe(10080)
    expect(clampInterval(90.7)).toBe(90)
    expect(clampInterval(Number.NaN)).toBe(60)
    expect(INTERVAL_OPTIONS.every((n) => clampInterval(n) === n)).toBe(true)
  })
})

describe('nextRunAt', () => {
  it('ultimo tentativo + intervallo (con il moltiplicatore dopo gli errori)', () => {
    expect(nextRunAt({ last_run: null, interval_min: 60, fail_count: 0 })).toBeNull()
    expect(nextRunAt({ last_run: 1000, interval_min: 60, fail_count: 0 })).toBe(4600)
    expect(nextRunAt({ last_run: 1000, interval_min: 60, fail_count: 3 })).toBe(1000 + 7200)
    expect([0, 2, 3, 5, 6].map(failureMultiplier)).toEqual([1, 1, 2, 2, 4])
  })
})

describe('diffRoute', () => {
  it('salti aggiunti e tolti', () => {
    expect(diffRoute('!aa>!bb', '!aa>!cc')).toEqual({ added: ['!cc'], removed: ['!bb'] })
    expect(diffRoute('', '!aa')).toEqual({ added: ['!aa'], removed: [] })
    expect(diffRoute('!aa', '')).toEqual({ added: [], removed: ['!aa'] })
  })
})

describe('routeLabel', () => {
  it('diretto oppure nomi dei salti', () => {
    expect(routeLabel('', (id) => id)).toBe('diretto')
    expect(routeLabel(null, (id) => id)).toBe('diretto')
    expect(routeLabel('!aa>!bb', (id) => id.toUpperCase())).toBe('!AA → !BB')
    i18n.lang = 'en'
    expect(routeLabel('', (id) => id)).toBe('direct')
  })
})

describe('statusKey', () => {
  it('tutti gli stati noti, null e uno ignoto', () => {
    for (const s of ['pending', 'ok', 'failed', 'timeout', 'throttled', 'busy', 'no_radio'])
      expect(statusKey(s)).toBe(`tracesched.status.${s}`)
    expect(statusKey(null)).toBe('tracesched.status.never')
    expect(statusKey('boh')).toBe('tracesched.status.unknown')
  })
})

describe('intervalLabel', () => {
  it('ore e giorni', () => {
    expect(intervalLabel(180)).toBe('ogni 3 h')
    expect(intervalLabel(1440)).toBe('ogni 1 g')
    expect(intervalLabel(90)).toBe('ogni 90 min')
  })
})

describe('i18n tracesched e bot', () => {
  it('ogni chiave esiste in italiano e in inglese', () => {
    const itKeys = Object.keys(itCat).filter((k) => k.startsWith('tracesched.') || k.startsWith('bot.'))
    expect(itKeys.length).toBeGreaterThan(50)
    for (const k of itKeys) expect((enCat as Record<string, string>)[k], k).toBeTruthy()
  })
})
