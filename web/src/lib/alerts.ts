import type { IconName } from './ui/icons'
import type { Alert } from './types'
import { num } from './format'
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
    default:
      return 'alert'
  }
}
