import { describe, expect, it, vi } from 'vitest'
import { en } from './i18n/en'
import { t } from './i18n/index.svelte'
import { it as itCat } from './i18n/it'
import { SETTINGS_ENTRIES, mergeNodeHits, moveActive, normalize, rankLocal, searchableConversations, settingsItems } from './globalsearch'
import type { NodeLike } from './globalsearch'

const node = (id: string, long_name: string | null, short_name: string | null = null, is_ignored = false): NodeLike => ({ id, long_name, short_name, is_ignored })
const noop = () => {}
const actions = [
  { id: 'a1', title: 'Apri la guida di avvio', run: noop },
  { id: 'a2', title: 'Vai a Impostazioni', run: noop },
  { id: 'a3', title: 'Vai a Mappa', run: noop },
  { id: 'a4', title: 'Vai a Nodi', run: noop },
  { id: 'a5', title: 'Vai a Rete', run: noop },
]
const src = (over: Partial<Parameters<typeof rankLocal>[1]> = {}) => ({ nodes: [], conversations: [], settings: [], actions, ...over })

describe('normalize', () => {
  it('minuscole e senza diacritici', () => {
    expect(normalize('Perché CITTÀ')).toBe('perche citta')
  })
})

describe('rankLocal', () => {
  it('q vuota: solo le azioni, al massimo 4', () => {
    const r = rankLocal('', src({ nodes: [node('!00000001', 'Rifugio')] }))
    expect(r.map((x) => x.group)).toEqual(['action', 'action', 'action', 'action'])
  })
  it('inizio parola prima di una corrispondenza interna', () => {
    const r = rankLocal('rif', src({ nodes: [node('!00000001', 'Garifa'), node('!00000002', 'Rifugio')] }))
    expect(r.filter((x) => x.group === 'node').map((x) => x.title)).toEqual(['Rifugio', 'Garifa'])
  })
  it('id con e senza «!», solo da 2 caratteri', () => {
    const nodes = [node('!a1b2c3d4', null), node('!0000ffff', 'Altro')]
    expect(rankLocal('a1b2', src({ nodes })).map((x) => x.id)).toContain('!a1b2c3d4')
    expect(rankLocal('!a1b2', src({ nodes })).map((x) => x.id)).toContain('!a1b2c3d4')
    expect(rankLocal('a', src({ nodes })).some((x) => x.id === '!a1b2c3d4')).toBe(false)
  })
  it('i nodi ignorati non compaiono', () => {
    const r = rankLocal('rif', src({ nodes: [node('!00000001', 'Rifugio Ignorato', null, true), node('!00000002', 'Rifugio')] }))
    expect(r.filter((x) => x.group === 'node').map((x) => x.id)).toEqual(['!00000002'])
  })
  it('limiti per gruppo', () => {
    const nodes = Array.from({ length: 20 }, (_, i) => node(`!${String(i).padStart(8, '0')}`, `Rif ${i}`))
    const conversations = Array.from({ length: 9 }, (_, i) => ({ key: `ch:r:${i}`, label: `Rif canale ${i}` }))
    const r = rankLocal('rif', src({ nodes, conversations }))
    expect(r.filter((x) => x.group === 'node')).toHaveLength(8)
    expect(r.filter((x) => x.group === 'conversation')).toHaveLength(5)
  })
  it('«impo» trova l\'azione di navigazione e una voce delle impostazioni', () => {
    const settings = settingsItems(t, 'Impostazioni')
    const r = rankLocal('impo', src({ settings }))
    expect(r.some((x) => x.group === 'action' && x.title === 'Vai a Impostazioni')).toBe(true)
    expect(r.some((x) => x.group === 'setting')).toBe(true)
  })
  it('i gruppi escono nell\'ordine azioni, nodi, conversazioni, impostazioni e i gestori si chiamano', () => {
    const onNode = vi.fn()
    const r = rankLocal('rete', src({ nodes: [node('!00000001', 'Rete Alpe')], conversations: [{ key: 'k', label: 'Rete' }], settings: [{ id: 'net', title: 'Impostazioni › Rete' }] }), { node: onNode })
    expect(r.map((x) => x.group)).toEqual(['action', 'node', 'conversation', 'setting'])
    r[1].run()
    expect(onNode).toHaveBeenCalledWith('!00000001')
  })
})

describe('mergeNodeHits', () => {
  it('non duplica e tiene i locali per primi; scarta gli ignorati', () => {
    const l = [{ id: 'a', v: 'locale' }]
    const r = [{ id: 'a', v: 'remoto' }, { id: 'b', v: 'remoto' }, { id: 'c', v: 'remoto' }]
    expect(mergeNodeHits(l, r, new Set(['c']))).toEqual([{ id: 'a', v: 'locale' }, { id: 'b', v: 'remoto' }])
  })
})

describe('moveActive', () => {
  it('circolare e -1 senza risultati', () => {
    expect(moveActive(0, -1, 3)).toBe(2)
    expect(moveActive(2, 1, 3)).toBe(0)
    expect(moveActive(0, 1, 0)).toBe(-1)
    expect(moveActive(-1, 1, 3)).toBe(0)
    expect(moveActive(-1, -1, 3)).toBe(2)
  })
})

describe('searchableConversations', () => {
  it('include il pubblico MQTT e i canali delle radio', () => {
    const radios = [{ id: 'r1', name: 'Base', kind: 'usb', address: '', auto_connect: true, state: 'connected', error: null, my_node_id: '!00000001', my_node_name: null, channels: [{ index: 0, name: 'LongFast', role: 'PRIMARY' }] }]
    const list = searchableConversations({ radios: radios as never, radioMessages: [], summaries: {}, counts: {}, nodes: new Map(), brokers: [] })
    expect(list.map((c) => c.key)).toEqual(['mqtt', 'ch:r1:0'])
    expect(list[1].label).toContain('LongFast')
  })
})

describe('chiavi', () => {
  it('le voci delle impostazioni hanno titolo in IT e EN', () => {
    for (const e of SETTINGS_ENTRIES) {
      expect(Object.hasOwn(itCat, e.titleKey), e.titleKey).toBe(true)
      expect(Object.hasOwn(en, e.titleKey), e.titleKey).toBe(true)
    }
  })
})
