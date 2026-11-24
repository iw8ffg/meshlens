import { describe, expect, it, vi } from 'vitest'

const calls = vi.hoisted(() => [] as unknown[][])
vi.mock('./api', () => ({
  send: vi.fn(async (...args: unknown[]) => {
    calls.push(args)
    return { kind: 'usb', address: 'COM5', checks: [], advice: null, radio_state: null }
  }),
  getJSON: vi.fn(),
}))

import { it as itCat } from './i18n/it'
import { en as enCat } from './i18n/en'
import {
  ADVICE_CODES, adviceSteps, adviceTitleKey, CHECKS, checkLabelKey, diagnoseAddress, diagnoseSaved,
  needsSave, statusKind, statusLabelKey, type Diagnosis,
} from './radiodiag'

const has = (k: string) => Object.hasOwn(itCat, k) && !!(enCat as Record<string, string>)[k]

describe('adviceSteps', () => {
  it('almeno due passi per ogni consiglio, tutti tradotti', () => {
    for (const code of ADVICE_CODES) {
      const steps = adviceSteps(code, { chip: 'CP210x' })
      expect(steps.length, code).toBeGreaterThanOrEqual(2)
      expect(steps.length, code).toBeLessThanOrEqual(4)
      for (const s of steps) expect(has(s), s).toBe(true)
      expect(has(adviceTitleKey(code)), code).toBe(true)
    }
  })

  it('il driver dipende dal chip', () => {
    expect(adviceSteps('usb_driver_missing', { chip: 'CP210x' })).toContain('radiodiag.step.driverCp210x')
    expect(adviceSteps('usb_driver_missing', { chip: 'CH340' })).toContain('radiodiag.step.driverCh340')
    expect(adviceSteps('usb_driver_missing', { chip: 'ESP32/native' })).toContain('radiodiag.step.driverEsp32')
    expect(adviceSteps('usb_driver_missing', {})).toContain('radiodiag.step.driverGeneric')
  })

  it('codice ignoto: passo generico', () => {
    expect(adviceSteps('boh')).toEqual(['radiodiag.step.replug', 'radiodiag.step.restart'])
    expect(adviceSteps(null).length).toBe(2)
    expect(adviceTitleKey('boh')).toBe('radiodiag.advice.generic')
  })
})

describe('stati e controlli', () => {
  it('statusKind e etichette', () => {
    expect(statusKind('ok')).toBe('ok')
    expect(statusKind('warn')).toBe('warn')
    expect(statusKind('fail')).toBe('danger')
    expect(statusKind('skip')).toBe('neutral')
    for (const s of ['ok', 'warn', 'fail', 'skip']) expect(has(statusLabelKey(s))).toBe(true)
  })

  it('ogni controllo noto ha un etichetta', () => {
    for (const c of CHECKS) expect(has(checkLabelKey(c)), c).toBe(true)
    expect(checkLabelKey('nuovo')).toBe('radiodiag.check.unknown')
  })
})

describe('chiamate', () => {
  it('radio salvata e indirizzo', async () => {
    await diagnoseSaved('r 1')
    await diagnoseAddress('tcp', '192.0.2.1')
    expect(calls).toEqual([
      ['POST', '/radios/r%201/diagnose', {}],
      ['POST', '/radios/diagnose', { kind: 'tcp', address: '192.0.2.1' }],
    ])
  })
})

describe('needsSave', () => {
  const diag = (checks: Diagnosis['checks']): Diagnosis =>
    ({ kind: 'tcp', address: '10.0.0.5', checks, advice: null, radio_state: null })
  it('vero se il server ha saltato i controlli TCP perché la radio non è salvata', () => {
    expect(needsSave(diag([
      { check: 'address_valid', status: 'ok', advice: null, params: {} },
      { check: 'tcp_connect', status: 'skip', advice: null, params: { reason: 'not_saved' } },
    ]))).toBe(true)
    expect(needsSave(diag([{ check: 'tcp_connect', status: 'skip', advice: null, params: {} }]))).toBe(false)
    expect(needsSave(null)).toBe(false)
    expect(has('radiodiag.notSaved')).toBe(true)
    expect((itCat as Record<string, string>)['radiodiag.notSaved']).toBe('Salva la radio e ripeti la diagnosi')
  })
})