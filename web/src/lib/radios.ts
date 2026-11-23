import type { Port, RadioKind, RadioState } from './types'
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

/** Icona della scheda radio per tipo di collegamento. */
export function kindIcon(kind: RadioKind): 'usb' | 'bt' | 'globe' {
  return kind === 'usb' ? 'usb' : kind === 'tcp' ? 'globe' : 'bt'
}

export function kindLabel(kind: RadioKind): string {
  return kind === 'usb' ? t('radios.usb') : kind === 'tcp' ? t('radios.network') : t('radios.bluetooth')
}

/** Indirizzo salvato dal form «Rete (IP)»: host, oppure host:porta se la porta non è quella predefinita. */
export const DEFAULT_TCP_PORT = 4403
export function tcpAddress(host: string, port: string): string {
  const h = host.trim()
  const p = port.trim()
  const hh = h.split(':').length > 2 && !h.startsWith('[') ? `[${h}]` : h
  return p === '' || p === String(DEFAULT_TCP_PORT) ? hh : `${hh}:${p}`
}
