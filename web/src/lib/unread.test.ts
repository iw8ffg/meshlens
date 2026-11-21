import { beforeEach, describe, expect, it } from 'vitest'
import { applyRead, applySummaries, noteIncoming, totalUnread, unread } from './unread.svelte'
import type { Message } from './types'

const KEY = 'dm:r1:!b'
const local = new Set(['!a'])
const msg = (o: Partial<Message> = {}): Message => ({
  key: 'k1', from: '!b', from_name: 'B', to: '!a', channel: '0', text: 'ciao', time: 100, country: null,
  source: 'rf', direction: 'in', radio_id: 'r1', ...o,
})

beforeEach(() => {
  applySummaries([{ key: KEY, unread: 2, read_time: 10, last_time: 0, last_text: '', last_from: '', last_emoji: false }])
})

describe('unread', () => {
  it('applySummaries sostituisce contatori e letture', () => {
    expect(unread.counts[KEY]).toBe(2)
    expect(unread.reads[KEY]).toBe(10)
    applySummaries([])
    expect(unread.counts).toEqual({})
  })
  it('un messaggio in ingresso nuovo conta', () => {
    expect(noteIncoming(msg(), local, null, true)).toBe(KEY)
    expect(unread.counts[KEY]).toBe(3)
  })
  it('uscita, reazione, mittente locale, senza radio e gia letto non contano', () => {
    expect(noteIncoming(msg({ direction: 'out' }), local, null, true)).toBeNull()
    expect(noteIncoming(msg({ emoji: true }), local, null, true)).toBeNull()
    expect(noteIncoming(msg({ from: '!a', to: '!b' }), local, null, true)).toBeNull()
    expect(noteIncoming(msg({ radio_id: null }), local, null, true)).toBeNull()
    expect(noteIncoming(msg({ time: 10 }), local, null, true)).toBeNull()
    expect(unread.counts[KEY]).toBe(2)
  })
  it('conversazione attiva e visibile non conta; non visibile si', () => {
    expect(noteIncoming(msg(), local, KEY, true)).toBeNull()
    expect(noteIncoming(msg(), local, KEY, false)).toBe(KEY)
  })
  it('applyRead azzera e non abbassa mai la lettura', () => {
    applyRead(KEY, 50)
    expect(unread.counts[KEY]).toBe(0)
    applyRead(KEY, 20)
    expect(unread.reads[KEY]).toBe(50)
  })
  it('totalUnread somma', () => {
    expect(totalUnread({ a: 2, b: 3 })).toBe(5)
  })
})
