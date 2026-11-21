import { describe, expect, it } from 'vitest'
import { DROP_LABELS, mqttSummary } from './mqttstatus'
import type { MqttStatus } from './types'

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
