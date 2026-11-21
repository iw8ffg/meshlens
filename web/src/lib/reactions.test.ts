import { describe, expect, it } from 'vitest'
import { keyChangedRecently, routingErrorText, threadItems } from './reactions'
import { T } from './strings/messaggi'
import type { Message, Node } from './types'

let seq = 0
const msg = (o: Partial<Message>): Message => ({
  key: `k${++seq}`,
  from: '!aaaa0001',
  from_name: null,
  to: '!ffffffff',
  channel: 'c',
  text: 't',
  time: 100 + seq,
  country: null,
  source: 'rf',
  radio_id: 'r1',
  ...o,
})
const name = (id: string) => `N${id.slice(-1)}`

describe('threadItems', () => {
  it('raggruppa le reazioni sul bersaglio', () => {
    const a = msg({ packet_id: 10 })
    const r1 = msg({ from: '!aaaa0002', emoji: true, text: '👍', reply_id: 10 })
    const r2 = msg({ from: '!aaaa0003', emoji: true, text: '👍', reply_id: 10 })
    const items = threadItems([a, r1, r2], name, new Set())
    expect(items).toHaveLength(1)
    expect(items[0].reactions[0].count).toBe(2)
    expect(items[0].reactions[0].names).toEqual(['N2', 'N3'])
    expect(items[0].reactions[0].mine).toBe(false)
  })
  it('reazione senza bersaglio: orfana, senza eccezioni', () => {
    const items = threadItems([msg({ emoji: true, text: '👍', reply_id: 999 })], name, new Set())
    expect(items).toHaveLength(1)
    expect(items[0].orphan).toBe(true)
  })
  it('risposta con bersaglio assente o presente', () => {
    const a = msg({ packet_id: 10 })
    const missing = msg({ reply_id: 999 })
    const ok = msg({ reply_id: 10 })
    const items = threadItems([a, missing, ok], name, new Set())
    expect(items[1].replyMissing).toBe(true)
    expect(items[1].replyTo).toBeNull()
    expect(items[2].replyTo?.packet_id).toBe(10)
    expect(items[2].replyMissing).toBe(false)
  })
  it('reazione propria: mine', () => {
    const a = msg({ packet_id: 10 })
    const r = msg({ from: '!aaaa0009', emoji: true, text: '❤️', reply_id: 10 })
    expect(threadItems([a, r], name, new Set(['!aaaa0009']))[0].reactions[0].mine).toBe(true)
    const out = msg({ direction: 'out', emoji: true, text: '❤️', reply_id: 10 })
    expect(threadItems([a, out], name, new Set())[0].reactions[0].mine).toBe(true)
  })
})

describe('routingErrorText', () => {
  it('codice noto dalla tabella', () => {
    expect(routingErrorText('PKI_UNKNOWN_PUBKEY')).toBe(T.routingErrors.PKI_UNKNOWN_PUBKEY)
    expect(routingErrorText('TIMEOUT')).toBe('Nessuna conferma entro il tempo massimo')
  })
  it('codice ignoto', () => {
    expect(routingErrorText('XYZ')).toContain('XYZ')
    expect(routingErrorText('constructor')).toContain('constructor')
  })
})

describe('keyChangedRecently', () => {
  const now = 1_000_000_000
  const node = (d: number) => ({ key_changed: now - d * 86400 }) as Node
  it('entro 7 giorni', () => {
    expect(keyChangedRecently(node(6), now)).toBe(true)
    expect(keyChangedRecently(node(8), now)).toBe(false)
    expect(keyChangedRecently(undefined, now)).toBe(false)
    expect(keyChangedRecently({ key_changed: null } as Node, now)).toBe(false)
  })
})
