import { describe, expect, it } from 'vitest'
import { MQTT_CONV, groupMessages } from './chat'
import { buildConversations, convLabel, filterConversations, previewText } from './conversations'
import { isMqttConv, mqttConvBroker, mqttConvKey } from './chat'
import { t } from './i18n/index.svelte'
import type { ConvSummary, Message, Radio } from './types'

const radio = (id: string, my: string, channels: [number, string][]): Radio =>
  ({ id, name: `R-${id}`, state: 'connected', my_node_id: my, channels: channels.map(([index, name]) => ({ index, name, role: 'PRIMARY' })) }) as never
const msg = (o: Partial<Message> = {}): Message => ({
  key: 'k1', from: '!b', from_name: 'B', to: '!a', channel: '0', text: 'ciao', time: 100, country: null,
  source: 'rf', direction: 'in', radio_id: 'r1', ...o,
})
const local = new Set(['!a', '!c'])
const nodeName = (id: string) => (id === '!b' ? 'Bruno' : id)
const label = (k: string) => k
const previewOf = (m: Message) => previewText(m, nodeName, local)
const summary = (o: Partial<ConvSummary>): ConvSummary => ({
  key: '', last_time: 0, last_text: '', last_from: '', last_emoji: false, unread: 0, read_time: 0, ...o,
})

describe('buildConversations', () => {
  const radios = [radio('r1', '!a', [[0, 'LongFast']]), radio('r2', '!c', [[0, 'Zeta']])]

  it('mqtt per primo, poi per attività: DM recente prima del canale vuoto', () => {
    const groups = groupMessages([msg({ time: 500 })], local)
    const items = buildConversations({ radios, groups, summaries: {}, counts: { 'dm:r1:!b': 2 }, label, previewOf })
    expect(items[0].key).toBe(MQTT_CONV)
    expect(items[0].kind).toBe('mqtt')
    expect(items[1]).toMatchObject({ key: 'dm:r1:!b', kind: 'dm', lastTime: 500, preview: 'ciao', unread: 2 })
    expect(items.slice(2).map((i) => i.key)).toEqual(['ch:r1:0', 'ch:r2:0'])
    expect(items[2].kind).toBe('ch')
  })

  it('un riepilogo del server più recente sposta la sua conversazione in alto', () => {
    const groups = groupMessages([msg({ time: 500 }), msg({ key: 'k2', to: '!ffffffff', time: 300, channel_index: 0 })], local)
    const summaries = { 'ch:r2:0': summary({ key: 'ch:r2:0', last_time: 900, last_text: 'dal server', last_from: '!z' }) }
    const items = buildConversations({ radios, groups, summaries, counts: {}, label, previewOf })
    expect(items.map((i) => i.key)).toEqual([MQTT_CONV, 'ch:r2:0', 'dm:r1:!b', 'ch:r1:0'])
    expect(items[1]).toMatchObject({ lastTime: 900, preview: 'dal server' })
  })

  it('a parità di attività ordina per etichetta', () => {
    const items = buildConversations({ radios, groups: new Map(), summaries: {}, counts: {}, label: (k) => (k === 'ch:r1:0' ? 'b' : 'a'), previewOf })
    expect(items.map((i) => i.key)).toEqual([MQTT_CONV, 'ch:r2:0', 'ch:r1:0'])
  })
})

describe('filterConversations', () => {
  it('trova senza maiuscole né accenti nel testo dei messaggi caricati', () => {
    const groups = groupMessages([msg({ time: 500, text: 'Perché no?' }), msg({ key: 'k2', from: '!d', time: 10, text: 'altro' })], local)
    const items = buildConversations({ radios: [], groups, summaries: {}, counts: {}, label, previewOf })
    const found = filterConversations(items, 'perche', groups)
    expect(found.map((i) => i.key)).toEqual(['dm:r1:!b'])
  })
  it("cerca anche nell'etichetta; la query vuota restituisce tutto", () => {
    const items = buildConversations({ radios: [], groups: new Map(), summaries: {}, counts: {}, label: (k) => (k === MQTT_CONV ? 'Pubblico (MQTT)' : k), previewOf })
    expect(filterConversations(items, 'PUBBLICO', new Map()).map((i) => i.key)).toEqual([MQTT_CONV])
    expect(filterConversations(items, '  ', new Map())).toEqual(items)
  })
})

describe('previewText', () => {
  it('un proprio messaggio inizia con «Tu: »', () => {
    expect(previewText(msg({ from: '!a', to: '!b', direction: 'out' }), nodeName, local).startsWith('Tu: ')).toBe(true)
  })
  it('una reazione dà T.reactionPreview', () => {
    expect(previewText(msg({ text: '👍', emoji: true, reply_id: 5 }), nodeName, local)).toBe(t('chat.reactionPreview', { name: 'Bruno', emoji: '👍' }))
  })
  it('100 caratteri diventano 80 più «…»', () => {
    expect(previewText(msg({ text: 'a'.repeat(100) }), nodeName, local)).toBe('a'.repeat(80) + '…')
  })
})

describe('pubblico per broker', () => {
  it('chiavi: tutti i broker e un solo broker', () => {
    expect(mqttConvKey('sos')).toBe('mqtt:sos')
    expect(isMqttConv(MQTT_CONV)).toBe(true)
    expect(isMqttConv('mqtt:sos')).toBe(true)
    expect(isMqttConv('ch:r1:0')).toBe(false)
    expect(mqttConvBroker('mqtt:sos')).toBe('sos')
    expect(mqttConvBroker(MQTT_CONV)).toBeNull()
    expect(mqttConvBroker('dm:r1:!a')).toBeNull()
  })

  it('con due broker: «tutti» e poi uno per broker, prima delle conversazioni radio', () => {
    const items = buildConversations({ radios: [], groups: new Map(), summaries: { 'mqtt:x': {} as never }, counts: {}, label: (k) => k, previewOf: () => '', brokers: [{ id: 'default' }, { id: 'sos' }] })
    expect(items.map((i) => i.key)).toEqual([MQTT_CONV, 'mqtt:default', 'mqtt:sos'])
    expect(items.every((i) => i.kind === 'mqtt')).toBe(true)
  })

  it('con un solo broker resta la conversazione unica', () => {
    const items = buildConversations({ radios: [], groups: new Map(), summaries: {}, counts: {}, label: (k) => k, previewOf: () => '', brokers: [{ id: 'default' }] })
    expect(items.map((i) => i.key)).toEqual([MQTT_CONV])
  })

  it('etichette', () => {
    const b = [{ id: 'default', name: 'mqtt.meshtastic.org' }, { id: 'sos', name: 'SOS-Italia' }]
    expect(convLabel(MQTT_CONV, [], (x) => x, b)).toBe(t('chat.mqttAllBrokers'))
    expect(convLabel(MQTT_CONV, [], (x) => x, b.slice(0, 1))).toBe(t('chat.mqttConversation'))
    expect(convLabel('mqtt:sos', [], (x) => x, b)).toBe(t('chat.mqttBrokerConversation', { broker: 'SOS-Italia' }))
    expect(convLabel('mqtt:gone', [], (x) => x, b)).toBe(t('chat.mqttBrokerConversation', { broker: 'gone' }))
  })
})
