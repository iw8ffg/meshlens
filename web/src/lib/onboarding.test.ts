import { describe, expect, it } from 'vitest'
import { en } from './i18n/en'
import { it as itCat } from './i18n/it'
import { emptyActions, onboardingSteps, shouldAutoOpen } from './onboarding'

describe('etichette', () => {
  it('ogni labelKey di emptyActions esiste in italiano e in inglese', () => {
    const counts = { nodeCount: 0, radioCount: 0, brokerCount: 0, connectedRadios: 0, convCount: 0 }
    const keys = (['nodes', 'network', 'radios', 'chat'] as const).flatMap((k) => emptyActions(k, counts).map((a) => a.labelKey))
    expect(keys.length).toBeGreaterThan(0)
    for (const k of keys) {
      expect(Object.hasOwn(itCat, k), k).toBe(true)
      expect(Object.hasOwn(en, k), k).toBe(true)
    }
  })
})

const base = { brokers: [], radios: [], nodes: [], mapCount: null as number | null }
const done = (s: ReturnType<typeof onboardingSteps>) => Object.fromEntries(s.map((x) => [x.id, x.done]))

describe('onboardingSteps', () => {
  it('database vuoto: tre passi da fare', () => {
    expect(onboardingSteps(base).map((s) => s.id)).toEqual(['source', 'nodes', 'maps'])
    expect(done(onboardingSteps(base))).toEqual({ source: false, nodes: false, maps: false })
  })
  it('broker: solo se abilitato', () => {
    expect(done(onboardingSteps({ ...base, brokers: [{ enabled: false }] })).source).toBe(false)
    expect(done(onboardingSteps({ ...base, brokers: [{ enabled: false }, { enabled: true }] })).source).toBe(true)
  })
  it('una radio qualunque conta, anche non collegata', () => {
    expect(done(onboardingSteps({ ...base, radios: [{ state: 'disconnected' }] })).source).toBe(true)
  })
  it('nodo mio e mappe offline', () => {
    expect(done(onboardingSteps({ ...base, nodes: [{ is_mine: false }] })).nodes).toBe(false)
    expect(done(onboardingSteps({ ...base, nodes: [{ is_mine: true }] })).nodes).toBe(true)
    expect(done(onboardingSteps({ ...base, mapCount: 0 })).maps).toBe(false)
    expect(done(onboardingSteps({ ...base, mapCount: null })).maps).toBe(false)
    expect(done(onboardingSteps({ ...base, mapCount: 2 })).maps).toBe(true)
  })
})

describe('shouldAutoOpen', () => {
  it('solo con onboarding_done === false e non chiusa', () => {
    expect(shouldAutoOpen(false, false)).toBe(true)
    expect(shouldAutoOpen(true, false)).toBe(false)
    expect(shouldAutoOpen(undefined, false)).toBe(false)
    expect(shouldAutoOpen(false, true)).toBe(false)
  })
})

describe('emptyActions', () => {
  const counts = { nodeCount: 0, radioCount: 0, brokerCount: 0, connectedRadios: 0, convCount: 0 }
  it('nodi e rete senza nodi: radio, MQTT, guida; con nodi nessuna azione', () => {
    for (const k of ['nodes', 'network'] as const) {
      expect(emptyActions(k, counts).map((a) => a.labelKey)).toEqual(['onboarding.goRadio', 'onboarding.goMqtt', 'onboarding.openGuide'])
      expect(emptyActions(k, { ...counts, nodeCount: 5 })).toEqual([])
    }
    expect(emptyActions('nodes', counts).map((a) => a.tab)).toEqual(['radio', 'settings', null])
  })
  it('chat: radio + MQTT solo se non c\'e\' niente', () => {
    expect(emptyActions('chat', counts).map((a) => a.labelKey)).toEqual(['onboarding.goRadio', 'onboarding.goMqtt'])
    expect(emptyActions('chat', { ...counts, connectedRadios: 1 })).toEqual([])
    expect(emptyActions('chat', { ...counts, brokerCount: 1 })).toEqual([])
    expect(emptyActions('chat', { ...counts, convCount: 2 })).toEqual([])
  })
  it('radios: guida + MQTT', () => {
    expect(emptyActions('radios', counts).map((a) => a.labelKey)).toEqual(['onboarding.openGuide', 'onboarding.goMqtt'])
  })
})
