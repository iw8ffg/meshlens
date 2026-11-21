import { describe, expect, it } from 'vitest'
import { DROP_LABELS, brokerRows, mqttSummary } from './mqttstatus'
import type { BrokerStatus, MqttStatus } from './types'

const base: MqttStatus = { connected: true, msgs_per_s: 2, undecodable: 0 }

describe('mqttSummary', () => {
  it('connesso con messaggi recenti è ok', () => {
    const r = mqttSummary({ ...base, last_msg_age_s: 5 }, 1000)
    expect(r.tone).toBe('ok')
    expect(r.title).toBe('Connesso')
  })
  it('connesso ma muto da 3 minuti è warn', () => {
    const r = mqttSummary({ ...base, last_msg_age_s: 180 }, 1000)
    expect(r.tone).toBe('warn')
    expect(r.title).toBe('Connesso, nessun messaggio da 3 min')
  })
  it('non connesso con errore mostra la riga Ultimo errore', () => {
    const r = mqttSummary({ ...base, connected: false, last_error: 'Utente o password MQTT rifiutati', last_error_at: 990 }, 1000)
    expect(r.tone).toBe('ko')
    expect(r.rows).toContainEqual({ label: 'Ultimo errore', value: 'Utente o password MQTT rifiutati' })
  })
  it('null è in attesa', () => {
    expect(mqttSummary(null, 0).tone).toBe('wait')
  })
  it('mostra solo i motivi di scarto positivi con le etichette', () => {
    const r = mqttSummary({ ...base, last_msg_age_s: 1, drops: { empty: 0, not_protobuf: 4, json_topic: 2 } }, 0)
    const labels = r.rows.map((x) => x.label)
    expect(labels).toContain(`Scartati: ${DROP_LABELS.not_protobuf}`)
    expect(labels).toContain(`Scartati: ${DROP_LABELS.json_topic}`)
    expect(labels.some((l) => l.includes(DROP_LABELS.empty))).toBe(false)
  })
  it('regge uno stato vecchio senza campi nuovi', () => {
    expect(() => mqttSummary({ connected: false, msgs_per_s: 0, undecodable: 3 }, 0)).not.toThrow()
  })
})

const bs = (id: string, o: Partial<BrokerStatus> = {}): BrokerStatus => ({
  id, name: `Nome ${id}`, enabled: true, host: 'h', tls: false, encryption: false,
  connected: true, msgs_per_s: 0, undecodable: 0, ...o,
})

describe('stato per broker', () => {
  it('due attivi, uno solo connesso: warn con conteggio', () => {
    const r = mqttSummary({ ...base, last_msg_age_s: 1, brokers: [bs('a'), bs('b', { connected: false })] }, 0)
    expect(r.tone).toBe('warn')
    expect(r.title).toBe('Connesso a 1 broker su 2')
  })
  it('due attivi, nessuno connesso: ko', () => {
    const r = mqttSummary({ ...base, connected: false, brokers: [bs('a', { connected: false }), bs('b', { connected: false })] }, 0)
    expect(r.tone).toBe('ko')
  })
  it('due attivi, entrambi connessi: ok', () => {
    expect(mqttSummary({ ...base, last_msg_age_s: 1, brokers: [bs('a'), bs('b')] }, 0).tone).toBe('ok')
  })
  it('brokerRows: connesso, con errore, disattivato in fondo', () => {
    const rows = brokerRows({
      ...base,
      brokers: [
        bs('off', { enabled: false, connected: false }),
        bs('a', { msgs_per_s: 1.5 }),
        bs('b', { connected: false, last_error: 'Utente o password MQTT rifiutati' }),
        bs('c', { connected: false }),
      ],
    }, 0)
    expect(rows.map((r) => r.id)).toEqual(['a', 'b', 'c', 'off'])
    expect(rows[0]).toMatchObject({ tone: 'ok', detail: '1,5 msg/s' })
    expect(rows[1]).toMatchObject({ tone: 'ko', detail: 'Utente o password MQTT rifiutati' })
    expect(rows[2]).toMatchObject({ tone: 'ko', detail: 'Non connesso' })
    expect(rows[3]).toMatchObject({ tone: 'wait', detail: 'Disattivato' })
  })
  it('senza brokers (server vecchio): righe vuote e riepilogo invariato', () => {
    expect(brokerRows(base, 0)).toEqual([])
    expect(brokerRows(null, 0)).toEqual([])
    expect(mqttSummary({ ...base, last_msg_age_s: 1 }, 0).title).toBe('Connesso')
  })
})
