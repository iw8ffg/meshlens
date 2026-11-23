import { afterEach, describe, expect, it, vi } from 'vitest'
import { exportMime, hitConvKey, mergePages, periodRange, searchMessages, searchPath, senderOptions, snippetParts } from './msgsearch'
import type { Message, MessageSearchHit } from './types'

const hit = (key: string, over: Partial<Message> = {}, conv: string | null = 'ch:r1:0'): MessageSearchHit => ({
  message: { key, from: '!0000000a', from_name: 'Zeta', to: '!ffffffff', channel: '', text: 't', time: 1, country: null, source: 'rf', ...over } as Message,
  snippet: null,
  conv,
})

afterEach(() => vi.unstubAllGlobals())

describe('snippetParts', () => {
  it('segmenta sui marcatori', () => {
    expect(snippetParts('ciao \x02mondo\x03 bello')).toEqual([
      { text: 'ciao ', hit: false },
      { text: 'mondo', hit: true },
      { text: ' bello', hit: false },
    ])
  })
  it('null e marcatori sbilanciati non lanciano e non producono HTML', () => {
    expect(snippetParts(null)).toEqual([])
    expect(snippetParts('a\x03b\x02c')).toEqual([
      { text: 'a', hit: false },
      { text: 'b', hit: false },
      { text: 'c', hit: true },
    ])
    expect(snippetParts('<b>x</b>')[0].text).toBe('<b>x</b>')
  })
})

describe('searchPath', () => {
  it('codifica e omette i parametri nulli', () => {
    expect(searchPath({ q: 'a b&c', cursor: '12.5:k:1', limit: 20 })).toBe('/messages/search?q=a%20b%26c&cursor=12.5%3Ak%3A1&limit=20')
    expect(searchPath({ q: 'x', conv: null, sender: '', since: null, until: 0 })).toBe('/messages/search?q=x&until=0')
  })
})

describe('periodRange', () => {
  it('tutto, giorno, settimana, mese', () => {
    expect(periodRange('all', 5)).toEqual({ since: null, until: null })
    expect(periodRange('week', 1_000_000)).toEqual({ since: 1_000_000 - 7 * 86400, until: null })
    expect(periodRange('day', 1_000_000).since).toBe(1_000_000 - 86400)
    expect(periodRange('month', 1_000_000).since).toBe(1_000_000 - 30 * 86400)
  })
})

describe('hitConvKey', () => {
  it('canale radio, MQTT con e senza broker', () => {
    expect(hitConvKey(hit('a'))).toBe('ch:r1:0')
    expect(hitConvKey(hit('a', { broker: 'b1' }, null))).toBe('mqtt:b1')
    expect(hitConvKey(hit('a', { broker: null }, null))).toBe('mqtt')
  })
})

describe('searchMessages', () => {
  it('chiama l\'URL atteso', async () => {
    const fn = vi.fn(async () => new Response(JSON.stringify({ hits: [], next: null, engine: 'like' }), { status: 200 }))
    vi.stubGlobal('fetch', fn)
    const r = await searchMessages({ q: 'ciao', conv: 'mqtt' })
    expect(r.engine).toBe('like')
    expect((fn.mock.calls[0] as unknown as [string])[0]).toBe('/api/messages/search?q=ciao&conv=mqtt')
  })
})

describe('supporto ai componenti', () => {
  it('senderOptions: distinti e ordinati per nome', () => {
    const hits = [hit('1', { from: '!2', from_name: 'Zeta' }), hit('2', { from: '!1', from_name: 'Alfa' }), hit('3', { from: '!2', from_name: 'Zeta' }), hit('4', { from: '!3', from_name: null })]
    expect(senderOptions(hits)).toEqual([
      { id: '!3', name: '!3' },
      { id: '!1', name: 'Alfa' },
      { id: '!2', name: 'Zeta' },
    ].sort((a, b) => a.name.localeCompare(b.name)))
  })
  it('mergePages non duplica per chiave', () => {
    const out = mergePages([hit('1'), hit('2')], [hit('2'), hit('3')])
    expect(out.map((h) => h.message.key)).toEqual(['1', '2', '3'])
  })
  it('exportMime', () => {
    expect(exportMime('csv')).toBe('text/csv')
    expect(exportMime('json')).toBe('application/json')
    expect(exportMime('txt')).toBe('text/plain')
  })
})
