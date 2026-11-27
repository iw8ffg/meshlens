import type { IconName } from './ui/icons'
import type { Alert } from './types'
import { num, signed } from './format'
import { t } from './i18n/index.svelte'

/** Testo di un avviso nella lingua corrente, senza nome del nodo. */
export function alertLabel(a: Pick<Alert, 'kind' | 'value' | 'detail'> & { node_name?: string }): string {
  switch (a.kind) {
    case 'battery_low':
      return t('shell.alertBattery', { n: Math.round(a.value) })
    case 'silent':
      return t('shell.alertSilent', { n: Math.round(a.value) })
    case 'key_changed':
      return t('shell.alertKeyChanged', { name: a.node_name ?? '' })
    case 'chutil_high':
      return t('shell.alertChutil', { n: num(a.value, 1) })
    case 'back_online':
      return t('shell.alertBackOnline', { n: Math.round(a.value) })
    case 'firmware_old':
      return t('shell.alertFirmware', { version: (a.detail ?? '').split('.').slice(0, 3).join('.') })
    // 1.6: avvisi delle regole su misura (value/detail: vedi piano WP2, D3)
    case 'rule_keyword':
      return t('alertrules.alert.keyword', { word: a.detail ?? '' })
    case 'rule_snr':
      return t('alertrules.alert.snr', { n: signed(a.value, 1) })
    case 'rule_geofence':
      return t(a.value >= 1 ? 'alertrules.alert.geoEnter' : 'alertrules.alert.geoExit', {
        zone: a.detail || t('alertrules.alert.zoneFallback'),
      })
    case 'rule_battery':
      return t('alertrules.alert.battery', { n: Math.round(a.value) })
    case 'rule_silent':
      return t('alertrules.alert.silent', { n: num(a.value, 1) })
    case 'sensor_detection':
      return t('alertrules.alert.detection', { text: a.detail ?? '' })
    default:
      return t('shell.alertGeneric')
  }
}

/** Tono visivo: back_online è una buona notizia, tutto il resto va segnalato. */
export function alertTone(kind: string): 'warn' | 'ok' {
  return kind === 'back_online' ? 'ok' : 'warn'
}

export function alertIcon(kind: string): IconName {
  switch (kind) {
    case 'battery_low':
      return 'battery'
    case 'silent':
      return 'clock'
    case 'chutil_high':
      return 'bars'
    case 'key_changed':
      return 'key'
    case 'back_online':
      return 'check'
    case 'rule_keyword':
      return 'chat'
    case 'rule_snr':
      return 'bars'
    case 'rule_geofence':
      return 'pin'
    case 'rule_battery':
      return 'battery'
    case 'rule_silent':
      return 'clock'
    case 'sensor_detection':
      return 'eye'
    default:
      return 'alert'
  }
}

/** Elenco senza l'avviso `key` (subito dopo averlo chiuso, in attesa dell'evento del server). */
export function withoutAlert(list: Alert[], key: string): Alert[] {
  return list.filter((a) => a.key !== key)
}

/** Elenco senza l'avviso di chiave cambiata del nodo (subito dopo averla accettata). */
export function withoutKeyChanged(list: Alert[], nodeId: string): Alert[] {
  return list.filter((a) => !(a.kind === 'key_changed' && a.node_id === nodeId))
}
