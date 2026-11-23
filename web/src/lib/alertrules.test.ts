import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  RULE_KINDS,
  RULE_LIMITS,
  addVertex,
  channelOptions,
  circleZone,
  createRule,
  deleteRule,
  draftErrors,
  draftFromRule,
  draftToBody,
  emptyDraft,
  listRules,
  parseWords,
  patchRule,
  pointInPolygon,
  polygonBounds,
  polygonIssue,
  polygonToGeoJSON,
  ruleIcon,
  ruleSummary,
  undoVertex,
  type Polygon,
  type RuleDraft,
} from './alertrules'
import { haversineM } from './distance'
import { setLang } from './i18n/index.svelte'
import type { AlertRule, AlertRuleKind } from './types'

afterEach(() => {
  vi.unstubAllGlobals()
  setLang('it')
})

const SQUARE: Polygon = [[10, 40], [11, 40], [11, 41], [10, 41]]

function rule(kind: AlertRuleKind, over: Partial<AlertRule> = {}): AlertRule {
  const base: AlertRule = {
    id: 3, kind, name: 'Casa', enabled: true, node_id: '!00000009', channel: null, threshold: null,
    params: {}, cooldown_min: 30, created: 1, updated: 2, last_fired: null,
  }
  const per: Record<AlertRuleKind, Partial<AlertRule>> = {
    keyword: { node_id: null, channel: 'ch:r1:2', params: { words: ['Aiuto', 'sos'], whole_word: true } },
    snr_low: { threshold: -7.5, params: { window_min: 30, min_samples: 4 } },
    geofence: { params: { trigger: 'both', polygon: SQUARE } },
    battery: { threshold: 20 },
    silent: { threshold: 2.5 },
    detection: { node_id: null, params: { match: 'porta' } },
  }
  return { ...base, ...per[kind], ...over }
}

describe('bozze', () => {
  it('emptyDraft: predefiniti', () => {
    for (const kind of RULE_KINDS) {
      const d = emptyDraft(kind)
      expect(d).toMatchObject({
        id: null, kind, enabled: true, cooldownMin: '60', windowMin: '60', minSamples: '3', trigger: 'exit',
        threshold: '', polygon: [], nodeId: null, channel: null, wholeWord: false,
      })
    }
  })

  it('draftToBody(draftFromRule(r)) è l’identità sui campi del corpo', () => {
    for (const kind of RULE_KINDS) {
      const r = rule(kind)
      const body = draftToBody(draftFromRule(r))
      expect(body).toEqual({
        kind: r.kind, name: r.name, enabled: r.enabled, node_id: r.node_id, channel: r.channel,
        threshold: r.threshold, params: r.params, cooldown_min: r.cooldown_min,
      })
    }
  })

  it('parseWords: separatori, strip e doppioni', () => {
    expect(parseWords('Aiuto, sos;\naiuto ,  ')).toEqual(['Aiuto', 'sos'])
    expect(parseWords('Perché, perche')).toEqual(['Perché'])
  })

  it('soglia con virgola decimale', () => {
    const d = { ...emptyDraft('snr_low'), nodeId: '!00000009', threshold: '-7,5' }
    expect(draftToBody(d).threshold).toBe(-7.5)
  })

  it('test_form_flow_helpers: params per tipo', () => {
    const bat = { ...emptyDraft('battery'), nodeId: '!00000001', threshold: '20' }
    expect(draftToBody(bat).params).toEqual({})
    const geo = { ...emptyDraft('geofence'), nodeId: '!00000001', polygon: SQUARE, trigger: 'enter' as const }
    expect(draftToBody(geo).params).toEqual({ trigger: 'enter', polygon: SQUARE })
    const kw = { ...emptyDraft('keyword'), wordsText: 'aiuto, sos', wholeWord: true }
    expect(draftToBody(kw).params).toEqual({ words: ['aiuto', 'sos'], whole_word: true })
    expect(draftToBody(kw).threshold).toBeNull()
    const snr = { ...emptyDraft('snr_low'), nodeId: '!00000001', threshold: '-5' }
    expect(draftToBody(snr).params).toEqual({ window_min: 60, min_samples: 3 })
    const det = { ...emptyDraft('detection'), match: ' porta ' }
    expect(draftToBody(det).params).toEqual({ match: 'porta' })
    expect(draftToBody({ ...kw, channel: 'ch:r1:1' }).channel).toBe('ch:r1:1')
    expect(draftToBody({ ...bat, channel: 'ch:r1:1' }).channel).toBeNull()
  })
})

describe('draftErrors', () => {
  const ok = (kind: AlertRuleKind) => draftFromRule(rule(kind))
  it('bozze valide: nessun errore', () => {
    for (const kind of RULE_KINDS) expect(draftErrors(ok(kind))).toEqual({})
  })
  it('limiti violati', () => {
    const bat = ok('battery')
    expect(draftErrors({ ...bat, threshold: '0' }).threshold).toBe('alertrules.err.threshold')
    expect(draftErrors({ ...bat, threshold: '100' }).threshold).toBe('alertrules.err.threshold')
    expect(draftErrors({ ...bat, threshold: '20,5' }).threshold).toBe('alertrules.err.threshold')
    expect(draftErrors({ ...bat, nodeId: null }).node).toBe('alertrules.err.node')
    const snr = ok('snr_low')
    expect(draftErrors({ ...snr, threshold: '-31' }).threshold).toBeDefined()
    expect(draftErrors({ ...snr, threshold: '21' }).threshold).toBeDefined()
    expect(draftErrors({ ...snr, windowMin: '14' }).window).toBe('alertrules.err.window')
    expect(draftErrors({ ...snr, minSamples: '0' }).samples).toBe('alertrules.err.samples')
    const sil = ok('silent')
    expect(draftErrors({ ...sil, threshold: '0,2' }).threshold).toBeDefined()
    expect(draftErrors({ ...sil, threshold: '169' }).threshold).toBeDefined()
    const kw = ok('keyword')
    const eleven = Array.from({ length: 11 }, (_, i) => `parola${i}`).join(',')
    expect(draftErrors({ ...kw, wordsText: eleven }).words).toBe('alertrules.err.words')
    expect(draftErrors({ ...kw, wordsText: 'a' }).words).toBe('alertrules.err.words')
    expect(draftErrors({ ...kw, wordsText: '' }).words).toBe('alertrules.err.words')
    expect(draftErrors({ ...kw, wordsText: 'x'.repeat(33) }).words).toBe('alertrules.err.words')
    const geo = ok('geofence')
    expect(draftErrors({ ...geo, polygon: SQUARE.slice(0, 2) }).polygon).toBe('alertrules.err.polygon')
    expect(draftErrors({ ...bat, cooldownMin: '0' }).cooldown).toBe('alertrules.err.cooldown')
    expect(draftErrors({ ...bat, cooldownMin: '1441' }).cooldown).toBe('alertrules.err.cooldown')
    expect(draftErrors({ ...bat, name: 'n'.repeat(61) }).name).toBe('alertrules.err.name')
    expect(draftErrors({ ...ok('detection'), match: 'm'.repeat(33) }).match).toBe('alertrules.err.match')
  })
  it('limiti esportati coerenti col server', () => {
    expect(RULE_LIMITS.cooldown).toEqual([1, 1440])
    expect(RULE_LIMITS.battery).toEqual([1, 99])
    expect(RULE_LIMITS.vertices).toEqual([3, 64])
  })
})

describe('riepilogo e canali', () => {
  const name = (id: string) => (id === '!00000009' ? 'Mio' : id)
  it('ruleSummary in italiano e inglese', () => {
    expect(ruleSummary(rule('battery'), name)).toBe('Batteria sotto il 20% · Mio')
    expect(ruleSummary(rule('keyword'), name)).toBe('Parole «Aiuto, sos» · Qualsiasi nodo')
    expect(ruleSummary(rule('snr_low'), name)).toBe('SNR medio sotto -7.5 dB · Mio')
    expect(ruleSummary(rule('silent'), name)).toBe('Silenzio oltre 2.5 h · Mio')
    expect(ruleSummary(rule('geofence'), name)).toBe('Zona · Entra o esce · Mio')
    expect(ruleSummary(rule('detection'), name)).toBe('Sensore «porta» · Qualsiasi nodo')
    expect(ruleSummary(rule('detection', { params: { match: '' } }), name)).toBe('Sensore, ogni rilevamento · Qualsiasi nodo')
    setLang('en')
    expect(ruleSummary(rule('battery'), name)).toBe('Battery below 20% · Mio')
    expect(ruleSummary(rule('geofence', { params: { trigger: 'exit', polygon: SQUARE } }), name)).toBe('Zone · Leaves the zone · Mio')
  })
  it('ruleIcon', () => {
    expect(RULE_KINDS.map(ruleIcon)).toEqual(['chat', 'bars', 'battery', 'clock', 'pin', 'eye'])
  })
  it('channelOptions', () => {
    const o = channelOptions([{ id: 'r1', name: 'Base' }], ['Meteo'])
    expect(o).toHaveLength(9)
    expect(o.slice(0, 8).map((x) => x.value)).toEqual(Array.from({ length: 8 }, (_, i) => `ch:r1:${i}`))
    expect(o[0].label).toContain('Base')
    expect(o[8]).toEqual({ value: 'mqtt:Meteo', label: 'MQTT · Meteo' })
  })
})

describe('geometria delle zone', () => {
  it('pointInPolygon', () => {
    expect(pointInPolygon(10.5, 40.5, SQUARE)).toBe(true)
    expect(pointInPolygon(12, 40.5, SQUARE)).toBe(false)
    expect(pointInPolygon(10, 40, SQUARE)).toBe(true)
    expect(pointInPolygon(10.5, 40, SQUARE)).toBe(true)
    const ell: Polygon = [[0, 0], [4, 0], [4, 1], [1, 1], [1, 4], [0, 4]]
    expect(pointInPolygon(0.5, 3, ell)).toBe(true)
    expect(pointInPolygon(3, 3, ell)).toBe(false)
  })
  it('polygonIssue', () => {
    expect(polygonIssue(SQUARE)).toBeNull()
    expect(polygonIssue([...SQUARE, SQUARE[0]])).toBeNull()
    expect(polygonIssue([[0, 0], [1, 1], [1, 0], [0, 1]])).toBe('cross')
    expect(polygonIssue([[0, 0], [1, 1], [2, 2]])).toBe('area')
    expect(polygonIssue(Array.from({ length: 65 }, (_, i) => [Math.cos(i) , Math.sin(i)] as [number, number]))).toBe('many')
    expect(polygonIssue([[0, 91], [1, 0], [0, 1]])).toBe('range')
    expect(polygonIssue([[0, 0], [1, 0]])).toBe('few')
    expect(polygonIssue([])).toBe('few')
  })
  it('polygonToGeoJSON chiude l’anello senza mutare l’ingresso', () => {
    const p: Polygon = SQUARE.map((x) => [...x] as [number, number])
    const f = polygonToGeoJSON(p)
    const ring = f.geometry.coordinates[0]
    expect(ring).toHaveLength(5)
    expect(ring[0]).toEqual(ring[4])
    expect(p).toEqual(SQUARE)
    expect(polygonToGeoJSON([]).geometry.coordinates[0]).toEqual([])
  })
  it('addVertex si ferma a 64 e non muta; undoVertex', () => {
    let p: Polygon = []
    for (let i = 0; i < 70; i++) p = addVertex(p, i, 0)
    expect(p).toHaveLength(64)
    const q: Polygon = [[0, 0]]
    expect(addVertex(q, 1, 1)).toEqual([[0, 0], [1, 1]])
    expect(q).toEqual([[0, 0]])
    expect(undoVertex([[0, 0], [1, 1]])).toEqual([[0, 0]])
    expect(undoVertex([])).toEqual([])
  })
  it('circleZone: 32 punti a ~500 m dal centro, senza chiusura', () => {
    const z = circleZone(45, 9, 500)
    expect(z).toHaveLength(32)
    expect(z[0]).not.toEqual(z[31])
    for (const [lon, lat] of z) {
      const d = haversineM({ lat: 45, lon: 9 }, { lat, lon })
      expect(Math.abs(d - 500) / 500).toBeLessThan(0.01)
    }
    expect(polygonIssue(z)).toBeNull()
  })
  it('test_zone_editing_helpers: sequenza d’uso', () => {
    let p: Polygon = []
    p = addVertex(p, 10, 40)
    p = addVertex(p, 11, 40)
    p = addVertex(p, 11, 41)
    expect(polygonIssue(p)).toBeNull()
    p = addVertex(p, 10, 41)
    expect(polygonIssue(p)).toBeNull()
    expect(undoVertex(p)).toHaveLength(3)
    expect(polygonBounds([])).toBeNull()
    expect(polygonBounds(SQUARE)).toEqual([10, 40, 11, 41])
  })
})

describe('chiamate HTTP', () => {
  function mockFetch(body: unknown = {}) {
    const fn = vi.fn(async () => new Response(JSON.stringify(body), { status: 200 }))
    vi.stubGlobal('fetch', fn)
    return fn
  }
  const call = (fn: ReturnType<typeof mockFetch>) => fn.mock.calls[0] as unknown as [string, RequestInit]

  it('listRules', async () => {
    const fn = mockFetch([])
    await listRules()
    expect(call(fn)[0]).toBe('/api/alert-rules')
    expect(call(fn)[1].method).toBe('GET')
  })
  it('createRule / patchRule', async () => {
    const body = draftToBody({ ...emptyDraft('detection') } as RuleDraft)
    let fn = mockFetch(rule('detection'))
    await createRule(body)
    expect(call(fn)[0]).toBe('/api/alert-rules')
    expect(call(fn)[1].method).toBe('POST')
    expect(call(fn)[1].headers).toEqual({ 'Content-Type': 'application/json' })
    expect(JSON.parse(call(fn)[1].body as string)).toEqual(body)
    fn = mockFetch(rule('detection'))
    await patchRule(7, { enabled: false })
    expect(call(fn)[0]).toBe('/api/alert-rules/7')
    expect(call(fn)[1].method).toBe('PATCH')
    expect(call(fn)[1].body).toBe('{"enabled":false}')
  })
  it('deleteRule manda la conferma', async () => {
    const fn = mockFetch({ ok: true })
    await deleteRule(7)
    expect(call(fn)[0]).toBe('/api/alert-rules/7')
    expect(call(fn)[1].method).toBe('DELETE')
    expect(call(fn)[1].body).toBe('{"confirm":true}')
  })
})
