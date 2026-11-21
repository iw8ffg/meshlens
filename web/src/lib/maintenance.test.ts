import { describe, expect, it } from 'vitest'
import { bytes, exportUrl, reasonLabel } from './maintenance'

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
