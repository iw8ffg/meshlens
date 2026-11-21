import { test, expect } from 'vitest'
import { byteLength, conversationKey, groupMessages, insertMessage, mergeRadioMessages, pickSendRadio, pruneSet, reactionDest, statusIcon } from './chat'
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

test('pickSendRadio: scelta manuale persistente, reset su cambio conversazione o radio persa', () => {
  const ids = ['r1', 'r2']
  expect(pickSendRadio('r2', 'r1', ids, false)).toBe('r2')
  expect(pickSendRadio('r2', 'r1', ids, true)).toBe('r1')
  expect(pickSendRadio('r2', 'r1', ['r1'], false)).toBe('r1')
  expect(pickSendRadio('r2', 'r9', ['r1'], false)).toBe('r1')
  expect(pickSendRadio('r2', 'r1', [], false)).toBe('')
  expect(pickSendRadio('', 'r2', ids, false)).toBe('r2')
})

test('mergeRadioMessages: dedup, ordine, tetto sui piu recenti, replaces', () => {
  const list: Message[] = []
  const rep = new Set<string>()
  mergeRadioMessages(list, [msg({ key: 'c', time: 30 }), msg({ key: 'a', time: 10 })], rep, 3)
  mergeRadioMessages(list, [msg({ key: 'b', time: 20 }), msg({ key: 'a', time: 10 })], rep, 3)
  expect(list.map((m) => m.key)).toEqual(['a', 'b', 'c'])
  mergeRadioMessages(list, [msg({ key: 'd', time: 40 })], rep, 3)
  expect(list.map((m) => m.key)).toEqual(['b', 'c', 'd'])
  mergeRadioMessages(list, [msg({ key: 'e', time: 50, replaces: 'd' })], rep, 3)
  expect(list.map((m) => m.key)).toEqual(['b', 'c', 'e'])
})

test('pruneSet: conserva gli ultimi inseriti', () => {
  const s = new Set(['a', 'b', 'c', 'd'])
  pruneSet(s, 2)
  expect([...s]).toEqual(['c', 'd'])
})

test('sendTargets: canale solo radio con canale omonimo, diretto qualunque radio connessa', async () => {
  const { sendTargets } = await import('./chat')
  const radio = (id: string, state: string, channels: [number, string][]) =>
    ({ id, name: id, state, channels: channels.map(([index, name]) => ({ index, name, role: 'SECONDARY' })) }) as never
  const radios = [
    radio('A', 'connected', [[0, 'LongFast'], [1, 'Amici']]),
    radio('B', 'connected', [[0, 'Amici'], [2, 'Altro']]),
    radio('C', 'connected', [[0, 'LongFast']]),
    radio('D', 'disconnected', [[0, 'Amici']]),
  ]
  expect(sendTargets(radios, 'ch:A:1').map((t) => [t.radio.id, t.index])).toEqual([['A', 1], ['B', 0]])
  expect(sendTargets(radios, 'ch:A:0').map((t) => t.radio.id)).toEqual(['A', 'C'])
  expect(sendTargets(radios, 'ch:Z:0')).toEqual([])
  expect(sendTargets(radios, 'dm:A:!00000001').map((t) => t.radio.id)).toEqual(['A', 'B', 'C'])
})

test('removeByKey rimuove la copia stantia dal feed', async () => {
  const { removeByKey } = await import('./chat')
  const list = [{ key: 'a' }, { key: 'b' }] as Message[]
  expect(removeByKey(list, 'a')).toBe(true)
  expect(list.map((x) => x.key)).toEqual(['b'])
  expect(removeByKey(list, 'zzz')).toBe(false)
  expect(list).toHaveLength(1)
})

test('reactionDest: un diretto riceve la reazione, mai il broadcast', () => {
  expect(reactionDest({ from: '!b', to: '!a', direction: 'in' }, null)).toBe('!b')
  expect(reactionDest({ from: '!a', to: '!b', direction: 'out' }, null)).toBe('!b')
  expect(reactionDest({ from: '!b', to: '!ffffffff', direction: 'in' }, null)).toBe(null)
  expect(reactionDest({ from: '!b', to: '!ffffffff', direction: 'in' }, '!c')).toBe('!c')
})
