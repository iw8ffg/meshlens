import { describe, expect, it } from 'vitest'
import {
  buildBrokerRetention, bytes, effectiveBrokerDays, exportUrl, integrityDamaged, reasonLabel, sortedTableBytes,
  TABLE_LABELS, tableLabel, validateBrokerDays,
} from './maintenance'

describe('bytes', () => {
  it('formatta con la virgola italiana', () => {
    expect(bytes(1_536_000)).toBe('1,5 MB')
  })
  it('zero', () => {
    expect(bytes(0)).toBe('0 B')
  })
})

describe('reasonLabel', () => {
  it('etichette italiane', () => {
    expect(reasonLabel('pre-migrazione')).toBe('Prima della migrazione')
    expect(reasonLabel('pre-aggiornamento')).toBe("Prima dell'aggiornamento")
    expect(reasonLabel('settimanale')).toBe('Settimanale')
    expect(reasonLabel('manuale')).toBe('Manuale')
  })
  it('motivo sconosciuto invariato', () => {
    expect(reasonLabel('boh')).toBe('boh')
  })
})

describe('exportUrl', () => {
  it('senza e con segreti', () => {
    expect(exportUrl(false)).toBe('/api/settings/export?secrets=0')
    expect(exportUrl(true)).toBe('/api/settings/export?secrets=1')
  })
})

describe('integrityDamaged', () => {
  it('neutro per ok, non controllata e in corso', () => {
    expect(integrityDamaged('ok')).toBe(false)
    expect(integrityDamaged('non controllata')).toBe(false)
    expect(integrityDamaged('in corso')).toBe(false)
  })
  it('danneggiato per qualsiasi altro esito', () => {
    expect(integrityDamaged('*** in database main ***')).toBe(true)
    expect(integrityDamaged('non leggibile (file is not a database)')).toBe(true)
  })
})

describe('sortedTableBytes', () => {
  it('ordina per spazio e calcola la quota', () => {
    const r = sortedTableBytes({ table_bytes: { nodes: 100, messages: 300, packets: 600 }, rows: { messages: 5, nodes: 2 } })
    expect(r.map((x) => x.name)).toEqual(['packets', 'messages', 'nodes'])
    expect(r.reduce((a, x) => a + x.share, 0)).toBeCloseTo(1, 6)
    expect(r[1]).toEqual({ name: 'messages', bytes: 300, rows: 5, share: 0.3 })
    expect(r[0].rows).toBeNull()
  })
  it('totale zero o campo assente: nessuna divisione per zero', () => {
    expect(sortedTableBytes({ table_bytes: { a: 0 }, rows: {} })[0].share).toBe(0)
    expect(sortedTableBytes({ rows: {} })).toEqual([])
  })
})

describe('conservazione per broker', () => {
  it('vale il minore', () => {
    expect(effectiveBrokerDays(7, 90)).toBe(7)
    expect(effectiveBrokerDays(120, 90)).toBe(90)
    expect(effectiveBrokerDays(null, 90)).toBe(90)
  })
  it('validazione dei giorni', () => {
    expect(validateBrokerDays(0)).toBe('retention.err.days')
    expect(validateBrokerDays(3651)).toBe('retention.err.days')
    expect(validateBrokerDays(1.5)).toBe('retention.err.days')
    expect(validateBrokerDays(7)).toBeNull()
  })
  it('le voci vuote non si salvano', () => {
    expect(buildBrokerRetention({ a: 7, b: null, c: undefined })).toEqual({ a: 7 })
  })
})

describe('tableLabel', () => {
  it('etichette storiche, nuove e nome grezzo', () => {
    expect(tableLabel('sensor_events')).toBe('Eventi dei sensori')
    expect(tableLabel('nodes')).toBe(TABLE_LABELS.nodes)
    expect(tableLabel('boh')).toBe('boh')
  })
})
