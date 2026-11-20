import { test, expect } from 'vitest'
import { byteLength, conversationKey, groupMessages, insertMessage, statusIcon } from './chat'
import type { Message } from './types'

const msg = (o: Partial<Message>): Message => ({
  key: 'k',
  from: '!aaaa0001',
  from_name: null,
  to: '!ffffffff',
  channel: 'LongFast',
  text: 'ciao',
  time: 1,
  country: null,
  source: 'rf',
  direction: 'in',
  radio_id: 'r1',
  channel_index: 0,
  ...o,
})
const local = new Set(['!bbbb0002'])

test('conversationKey: canale, diretto in/out, mqtt', () => {
  expect(conversationKey(msg({ channel_index: 2 }), local)).toBe('ch:r1:2')
  expect(conversationKey(msg({ to: '!bbbb0002' }), local)).toBe('dm:r1:!aaaa0001')
  expect(conversationKey(msg({ from: '!bbbb0002', to: '!aaaa0001', direction: 'out' }), local)).toBe('dm:r1:!aaaa0001')
  expect(conversationKey(msg({ from: '!bbbb0002', to: '!aaaa0001', direction: undefined }), local)).toBe('dm:r1:!aaaa0001')
  expect(conversationKey(msg({ radio_id: null, source: 'mqtt' }), local)).toBe('mqtt')
})

test('groupMessages: raggruppa, ordina, salta mqtt', () => {
  const g = groupMessages(
    [msg({ key: 'a', time: 5 }), msg({ key: 'b', time: 2 }), msg({ key: 'c', radio_id: null }), msg({ key: 'd', to: '!bbbb0002', time: 3 })],
    local,
  )
  expect([...g.keys()].sort()).toEqual(['ch:r1:0', 'dm:r1:!aaaa0001'])
  expect(g.get('ch:r1:0')!.map((m) => m.key)).toEqual(['b', 'a'])
})

test('byteLength: UTF-8 con emoji e accenti', () => {
  expect(byteLength('abc')).toBe(3)
  expect(byteLength('è')).toBe(2)
  expect(byteLength('😀')).toBe(4)
  expect(byteLength('')).toBe(0)
})

test('insertMessage: replaces sostituisce il provvisorio, anche se arriva dopo', () => {
  const list: Message[] = []
  const rep = new Set<string>()
  insertMessage(list, msg({ key: 'out:r1:0', status: 'sending' }), rep)
  insertMessage(list, msg({ key: 'out:r1:9', replaces: 'out:r1:0', status: 'sent' }), rep)
  expect(list.map((m) => m.key)).toEqual(['out:r1:9'])
  insertMessage(list, msg({ key: 'out:r1:0', status: 'sending' }), rep)
  expect(list.map((m) => m.key)).toEqual(['out:r1:9'])
  insertMessage(list, msg({ key: 'out:r1:9' }), rep)
  expect(list).toHaveLength(1)
})

test('statusIcon', () => {
  expect(statusIcon('sending')).toBe('⏳')
  expect(statusIcon('acked')).toBe('✓✓')
  expect(statusIcon('failed')).toBe('⚠')
  expect(statusIcon(null)).toBe('')
})
