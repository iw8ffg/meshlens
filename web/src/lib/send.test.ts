import { expect, test } from 'vitest'
import { MAX_BYTES } from './chat'
import { keyboardLift } from './keyboard'
import {
  MQTT_NODE_REASON,
  PUBLIC_WARNING,
  byteCount,
  classifyMqttError,
  mqttBody,
  mqttChannelNames,
  pickRadioChannel,
  pickVia,
  resendBody,
  statusAria,
  viaOptions,
} from './send'

const rad = (id: string, state: string, my: string | null, channels: [number, string][] = [[0, 'LongFast']]) =>
  ({ id, name: `R-${id}`, state, my_node_id: my, channels: channels.map(([index, name]) => ({ index, name, role: 'PRIMARY' })) }) as never

test('byteCount: limite 200 byte UTF-8, non caratteri', () => {
  expect(byteCount('a'.repeat(200))).toMatchObject({ bytes: 200, over: false, remaining: 0 })
  expect(byteCount('a'.repeat(201)).over).toBe(true)
  // 100 «è» = 200 byte: al limite; 101 lo supera pur avendo pochi caratteri
  expect(byteCount('è'.repeat(100)).over).toBe(false)
  expect(byteCount('è'.repeat(101))).toMatchObject({ bytes: 202, over: true })
  expect(byteCount('😀'.repeat(51)).over).toBe(true)
  expect(MAX_BYTES).toBe(200)
})

test('viaOptions: radio e MQTT disponibili', () => {
  const o = viaOptions({ radios: [rad('a', 'connected', '!aabbccdd')], mqttConnected: true, mqttNodeId: '', unknownNode: false })
  expect(o.map((x) => [x.value, x.disabled])).toEqual([['radio:a', false], ['mqtt', false]])
  expect(o[0].label).toBe('Radio «R-a»')
  expect(o[1].label).toBe('MQTT (LongFast)')
})

test('viaOptions: etichette coi nomi dei canali', () => {
  const o = viaOptions({
    radios: [rad('a', 'connected', '!aabbccdd', [[0, 'LongFast'], [1, 'Amici']])],
    mqttConnected: true,
    mqttNodeId: '',
    unknownNode: false,
    radioChannelName: (r) => r.channels.find((c) => c.index === 1)?.name,
    mqttChannel: 'Medium',
  })
  expect(o.map((x) => x.label)).toEqual(['Radio «R-a» (Amici)', 'MQTT (Medium)'])
})

test('viaOptions: nessuna radio -> radio disattivata col motivo', () => {
  const o = viaOptions({ radios: [], mqttConnected: true, mqttNodeId: '!aabbccdd', unknownNode: false })
  expect(o[0]).toMatchObject({ disabled: true, reason: 'Collega una radio' })
  expect(o[1]).toMatchObject({ value: 'mqtt', disabled: false, reason: null })
})

test('viaOptions: MQTT non connesso e id nodo mancante', () => {
  const down = viaOptions({ radios: [rad('a', 'connected', '!aabbccdd')], mqttConnected: false, mqttNodeId: '', unknownNode: false })
  expect(down[1]).toMatchObject({ disabled: true, reason: 'MQTT non connesso' })
  const noId = viaOptions({ radios: [rad('a', 'disconnected', null)], mqttConnected: true, mqttNodeId: '', unknownNode: false })
  expect(noId[0]).toMatchObject({ disabled: true, reason: 'Collega una radio' })
  expect(noId[1]).toMatchObject({ disabled: true, reason: MQTT_NODE_REASON })
  const unknown = viaOptions({ radios: [rad('a', 'connected', '!aabbccdd')], mqttConnected: true, mqttNodeId: '', unknownNode: true })
  expect(unknown[1].reason).toBe(MQTT_NODE_REASON)
})

test('pickVia: scelta persistente, conversazione, ripiego', () => {
  const o = viaOptions({ radios: [rad('a', 'connected', '!aabbccdd'), rad('b', 'connected', '!11223344')], mqttConnected: true, mqttNodeId: '', unknownNode: false })
  expect(pickVia('radio:b', 'ch:a:0', o, false)).toBe('radio:b')
  expect(pickVia('radio:b', 'ch:a:0', o, true)).toBe('radio:a')
  expect(pickVia('radio:b', 'mqtt', o, true)).toBe('mqtt')
  const down = viaOptions({ radios: [rad('a', 'connected', '!aabbccdd')], mqttConnected: false, mqttNodeId: '', unknownNode: false })
  expect(pickVia('mqtt', 'mqtt', down, false)).toBe('radio:a')
  expect(pickVia('', 'mqtt', viaOptions({ radios: [], mqttConnected: false, mqttNodeId: '', unknownNode: false }), true)).toBe('')
})

test('pickRadioChannel: omonimo alla conversazione, poi il primo, scelta persistente', () => {
  const radios = [rad('a', 'connected', null, [[0, 'LongFast'], [1, 'Amici']]), rad('b', 'connected', null, [[0, 'Altro'], [3, 'Amici']])]
  expect(pickRadioChannel('ch:a:1', radios, 'b', 0, true)).toBe(3)
  expect(pickRadioChannel('ch:a:1', radios, 'b', 0, false)).toBe(0)
  expect(pickRadioChannel('mqtt', radios, 'b', 9, true)).toBe(0)
  expect(pickRadioChannel('mqtt', radios, 'zz', 0, true)).toBe(0)
})

test('mqttChannelNames: LongFast per primo, senza doppioni', () => {
  expect(mqttChannelNames([{ name: 'Medium' }, { name: 'LongFast' }, { name: 'Medium' }])).toEqual(['LongFast', 'Medium'])
  expect(mqttChannelNames([])).toEqual(['LongFast'])
})

test('conferma MQTT: 409 chiede conferma e il reinvio porta confirm_public', () => {
  const r = classifyMqttError({ status: 409, code: 'confirm_required', message: 'x' })
  expect(r.kind).toBe('confirm')
  expect(r.message).toBe(PUBLIC_WARNING)
  expect(PUBLIC_WARNING).toBe('Il messaggio sarà pubblico sul broker mqtt.meshtastic.org e potrà essere ritrasmesso via radio dai gateway')
  const first = mqttBody('  ciao ', 'LongFast', null, false)
  expect(first).toEqual({ text: 'ciao', channel: 'LongFast' })
  expect(resendBody(first)).toEqual({ text: 'ciao', channel: 'LongFast', confirm_public: true })
  expect(mqttBody('x', 'LongFast', '!aabbccdd', true)).toEqual({ text: 'x', channel: 'LongFast', to: '!aabbccdd', confirm_public: true })
})

test('classifyMqttError: nodo, 429, 503, generico', () => {
  expect(classifyMqttError({ status: 400, code: 'unknown_node', message: 'Collega una radio o imposta il tuo id nodo' })).toEqual({ kind: 'unknown_node', message: MQTT_NODE_REASON })
  expect(classifyMqttError({ status: 429, code: 'rate_limited', message: 'Attendi 7 s' })).toEqual({ kind: 'rate_limited', message: 'Attendi 7 s' })
  expect(classifyMqttError({ status: 429, code: null, message: 'Too Many Requests', retryAfter: 5 }).message).toBe('Attendi 5 s')
  expect(classifyMqttError({ status: 503, code: 'mqtt_disconnected', message: 'MQTT non connesso' }).kind).toBe('disconnected')
  expect(classifyMqttError({ status: 400, code: 'invalid_text', message: 'Testo troppo lungo' })).toEqual({ kind: 'other', message: 'Testo troppo lungo' })
})

test('statusAria: stato e via MQTT', () => {
  expect(statusAria('sent', 'mqtt')).toBe('Inviato · via MQTT')
  expect(statusAria('acked', 'radio')).toBe('Consegnato')
  expect(statusAria(null, 'mqtt')).toBe('via MQTT')
  expect(statusAria('failed', undefined)).toBe('Non consegnato')
})

test('keyboardLift: solleva solo quanto la tastiera copre', () => {
  expect(keyboardLift(700, 0, 500, 0)).toBe(200)
  // gia' sollevato di 200: il bordo misurato e' 500, quello naturale resta 700
  expect(keyboardLift(500, 200, 500, 0)).toBe(200)
  // tastiera chiusa
  expect(keyboardLift(500, 200, 800, 0)).toBe(0)
  expect(keyboardLift(700, 0, 800, 0)).toBe(0)
})
