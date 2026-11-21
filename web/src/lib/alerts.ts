import type { IconName } from './ui/icons'
import type { Alert } from './types'
import { num } from './format'
import { T } from './strings/messaggi'

/** Testo italiano di un avviso, senza nome del nodo. */
export function alertLabel(a: Pick<Alert, 'kind' | 'value' | 'detail'> & { node_name?: string }): string {
  switch (a.kind) {
    case 'battery_low':
      return `Batteria al ${Math.round(a.value)}%`
    case 'silent':
      return `Silenzioso da ${Math.round(a.value)} h`
    case 'key_changed':
      return T.alertKeyChanged(a.node_name ?? '')
    case 'chutil_high':
      return `Canale occupato al ${num(a.value, 1)}% (media 30 min)`
    case 'back_online':
      return `Di nuovo online dopo ${Math.round(a.value)} h`
    case 'firmware_old':
      return `Firmware vecchio (${(a.detail ?? '').split('.').slice(0, 3).join('.')})`
    default:
      return 'Avviso'
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
