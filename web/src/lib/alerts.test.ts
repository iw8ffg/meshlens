import { afterEach, describe, expect, it } from 'vitest'
import { alertIcon, alertLabel, alertTone } from './alerts'
import { setLang } from './i18n/index.svelte'
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

describe('avvisi delle regole su misura (1.6)', () => {
  afterEach(() => setLang('it'))
  it('testi italiani', () => {
    expect(alertLabel({ kind: 'rule_keyword', value: 0, detail: 'aiuto' })).toBe('Parola «aiuto» in chat')
    // il segno è il meno tipografico di signed()
    expect(alertLabel({ kind: 'rule_snr', value: -9.25 })).toBe('Segnale debole: SNR medio −9,3 dB')
    expect(alertLabel({ kind: 'rule_geofence', value: 1, detail: 'Casa' })).toBe('Entrato in «Casa»')
    expect(alertLabel({ kind: 'rule_geofence', value: 0, detail: 'Casa' })).toBe('Uscito da «Casa»')
    expect(alertLabel({ kind: 'rule_geofence', value: 1, detail: '' })).toBe('Entrato in «la zona»')
    expect(alertLabel({ kind: 'rule_battery', value: 12 })).toBe('Batteria al 12% (soglia personalizzata)')
    expect(alertLabel({ kind: 'rule_silent', value: 3.5 })).toBe('Silenzioso da 3,5 h')
    expect(alertLabel({ kind: 'sensor_detection', value: 1, detail: 'Porta detected' })).toBe('Rilevamento: Porta detected')
    expect(alertLabel({ kind: 'autonomy_low', value: 0 })).toBe('Avviso')
  })
  it('testi inglesi', () => {
    setLang('en')
    expect(alertLabel({ kind: 'rule_keyword', value: 0, detail: 'help' })).toBe('Keyword "help" in chat')
    expect(alertLabel({ kind: 'rule_geofence', value: 0, detail: '' })).toBe('Left "the zone"')
    expect(alertLabel({ kind: 'rule_silent', value: 3.5 })).toBe('Silent for 3.5 h')
    expect(alertLabel({ kind: 'rule_snr', value: -9.25 })).toBe('Weak signal: average SNR −9.3 dB')
  })
  it('icone e tono', () => {
    expect(alertIcon('rule_keyword')).toBe('chat')
    expect(alertIcon('rule_snr')).toBe('bars')
    expect(alertIcon('rule_geofence')).toBe('pin')
    expect(alertIcon('rule_battery')).toBe('battery')
    expect(alertIcon('rule_silent')).toBe('clock')
    expect(alertIcon('sensor_detection')).toBe('eye')
    expect(alertTone('rule_battery')).toBe('warn')
  })
})
