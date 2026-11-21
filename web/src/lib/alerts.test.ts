import { describe, expect, it } from 'vitest'
import { alertIcon, alertLabel, alertTone } from './alerts'
import type { Alert } from './types'

describe('alertLabel', () => {
  it('testo per ogni tipo', () => {
    expect(alertLabel({ kind: 'battery_low', value: 12 })).toBe('Batteria al 12%')
    expect(alertLabel({ kind: 'silent', value: 30 })).toBe('Silenzioso da 30 h')
    expect(alertLabel({ kind: 'chutil_high', value: 31.3 })).toBe('Canale occupato al 31,3% (media 30 min)')
    expect(alertLabel({ kind: 'back_online', value: 7 })).toBe('Di nuovo online dopo 7 h')
    expect(alertLabel({ kind: 'firmware_old', value: 0, detail: '2.3.2.63df972' })).toBe('Firmware vecchio (2.3.2)')
  })
  it('key_changed con il nome del nodo', () => {
    expect(alertLabel({ kind: 'key_changed', value: 0, node_name: 'Base' })).toBe('Chiave pubblica di Base cambiata')
    expect(alertTone('key_changed')).toBe('warn')
    expect(alertIcon('key_changed')).toBe('key')
  })
  it('tipo sconosciuto: «Avviso»', () => {
    expect(alertLabel({ kind: 'qualcosa_di_nuovo' as Alert['kind'], value: 0 })).toBe('Avviso')
  })
})

describe('alertTone e alertIcon', () => {
  it('back_online è ok, gli altri warn', () => {
    expect(alertTone('back_online')).toBe('ok')
    expect(alertTone('silent')).toBe('warn')
    expect(alertTone('chutil_high')).toBe('warn')
    expect(alertTone('firmware_old')).toBe('warn')
  })
  it('icona per tipo', () => {
    expect(alertIcon('battery_low')).toBe('battery')
    expect(alertIcon('silent')).toBe('clock')
    expect(alertIcon('chutil_high')).toBe('bars')
    expect(alertIcon('back_online')).toBe('check')
    expect(alertIcon('firmware_old')).toBe('alert')
    expect(alertIcon('sconosciuto')).toBe('alert')
  })
})
