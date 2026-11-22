import type { Port, RadioState } from './types'
import { t } from './i18n/index.svelte'

/** Prima le porte probabili Meshtastic, poi per nome del dispositivo; non modifica l'input. */
export function sortPorts(ports: Port[]): Port[] {
  return [...ports].sort(
    (a, b) =>
      Number(b.likely_meshtastic) - Number(a.likely_meshtastic) ||
      a.device.localeCompare(b.device, undefined, { numeric: true }),
  )
}

/** Classe colore del pallino di stato: verde, giallo, rosso, grigio. */
export function stateClass(state: RadioState): 'green' | 'yellow' | 'red' | 'gray' {
  if (state === 'connected') return 'green'
  if (state === 'connecting' || state === 'reconnecting') return 'yellow'
  if (state === 'error') return 'red'
  return 'gray'
}

export function stateLabel(state: RadioState): string {
  switch (state) {
    case 'connected':
      return t('radios.state.connected')
    case 'connecting':
      return t('radios.state.connecting')
    case 'reconnecting':
      return t('radios.state.reconnecting')
    case 'error':
      return t('radios.state.error')
    default:
      return t('radios.state.disconnected')
  }
}
