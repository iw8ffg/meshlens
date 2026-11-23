import { afterEach, describe, expect, it, vi } from 'vitest'
import { setLang } from './i18n/index.svelte'
import { statusIcon, statusLabel } from './chat'
import { brokerRows, mqttSummary, refusedTopics } from './mqttstatus'
import { heardName, mqttDelivery, mqttFailText } from './send'
import { dispatch } from './ws'
import type { BrokerStatus, MqttStatus } from './types'

afterEach(() => setLang('it'))

const names: Record<string, string> = { '!0badcafe': 'Gateway Monte' }
const nodeName = (id: string) => names[id] ?? id
const radios = [{ id: 'r1', name: 'Heltec' }]

describe('mqttDelivery', () => {
  it('invio, accettato dal broker con la spiegazione', () => {
    expect(mqttDelivery({ status: 'sending' }, nodeName)).toMatchObject({ text: 'Invio…', tone: 'wait' })
    const sent = mqttDelivery({ status: 'sent' }, nodeName)!
    expect(sent.text).toBe('Accettato dal broker')
    expect(sent.title).toMatch(/non garantisce/)
  })
  it('sentito in radio: nome del nodo, id sconosciuto e altri', () => {
    expect(mqttDelivery({ status: 'heard', heard_by: ['!0badcafe'] }, nodeName)!.text).toBe('Sentito in radio da Gateway Monte')
    expect(mqttDelivery({ status: 'heard', heard_by: ['!12345678'] }, nodeName)!.text).toBe('Sentito in radio da !12345678')
    const more = mqttDelivery({ status: 'heard', heard_by: ['!0badcafe', 'radio:r1', '!00000001'] }, nodeName, radios)!
    expect(more.text).toBe('Sentito in radio da Gateway Monte e altri 2')
    expect(more.title).toContain('Gateway Monte, Heltec, !00000001')
    expect(more.tone).toBe('good')
    expect(mqttDelivery({ status: 'heard', heard_by: null }, nodeName)!.text).toBe('Sentito in radio')
  })
  it('non confermato con l’errore del server, tradotto in inglese', () => {
    const d = mqttDelivery({ status: 'failed', error: 'Il broker non ha confermato il messaggio' }, nodeName)!
    expect(d).toMatchObject({ text: 'Non confermato', title: 'Il broker non ha confermato il messaggio', tone: 'bad' })
    setLang('en')
    expect(mqttFailText('Il broker non ha confermato il messaggio')).toBe('The broker did not confirm the message')
    expect(mqttDelivery({ status: 'sent' }, nodeName)!.text).toBe('Accepted by the broker')
    expect(mqttDelivery({ status: 'heard', heard_by: ['!0badcafe'] }, nodeName)!.text).toBe('Heard on radio by Gateway Monte')
  })
  it('stato assente: niente', () => {
    expect(mqttDelivery({ status: null }, nodeName)).toBeNull()
  })
  it('heardName: radio locale per nome o per id', () => {
    expect(heardName('radio:r1', nodeName, radios)).toBe('Heltec')
    expect(heardName('radio:zz', nodeName, radios)).toBe('zz')
  })
  it('stato heard nelle etichette generiche', () => {
    expect(statusIcon('heard')).toBe('📡')
    expect(statusLabel('heard')).toBe('Sentito in radio')
  })
})

describe('message_status con heard_by', () => {
  it('passa chi l’ha sentito al gestore', () => {
    const messageStatus = vi.fn()
    const h = { messageStatus } as unknown as Parameters<typeof dispatch>[1]
    dispatch({ type: 'message_status', key: 'k', status: 'heard', error: null, heard_by: ['!0badcafe'] }, h)
    expect(messageStatus).toHaveBeenCalledWith('k', 'heard', null, ['!0badcafe'])
  })
})

const broker = (over: Partial<BrokerStatus>): BrokerStatus => ({
  connected: true, msgs_per_s: 0, undecodable: 0, id: 'b', name: 'LoRa Italia', enabled: true,
  host: 'h', tls: false, encryption: true, ...over,
})

describe('sottoscrizioni rifiutate', () => {
  it('riga del broker in avviso con i topic', () => {
    const s: MqttStatus = { connected: true, msgs_per_s: 0, undecodable: 0, brokers: [broker({ refused_topics: ['msh/IT/#'] })] }
    const [row] = brokerRows(s, 0)
    expect(row.tone).toBe('warn')
    expect(row.detail).toBe('Sottoscrizioni rifiutate: msh/IT/#')
  })
  it('riepilogo: avviso e riga dei topic; con più broker il nome davanti', () => {
    const one: MqttStatus = { connected: true, msgs_per_s: 0, undecodable: 0, last_msg_age_s: 1, brokers: [broker({ refused_topics: ['msh/IT/#'] })] }
    const r = mqttSummary(one, 0)
    expect(r.tone).toBe('warn')
    expect(r.rows).toContainEqual({ label: 'Topic rifiutati', value: 'msh/IT/#' })
    const two: MqttStatus = { ...one, brokers: [broker({ refused_topics: ['a/#'] }), broker({ id: 'c', name: 'Altro', refused_topics: [] })] }
    expect(refusedTopics(two)).toEqual(['LoRa Italia: a/#'])
  })
  it('broker non connesso o disattivato: non conta', () => {
    const s: MqttStatus = { connected: false, msgs_per_s: 0, undecodable: 0, brokers: [broker({ connected: false, refused_topics: ['x/#'] }), broker({ enabled: false, refused_topics: ['y/#'] })] }
    expect(refusedTopics(s)).toEqual([])
    expect(refusedTopics({ connected: true, msgs_per_s: 0, undecodable: 0, refused_topics: ['z/#'] })).toEqual(['z/#'])
  })
})
