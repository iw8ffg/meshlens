// Accesso ospite (E19): funzioni pure per il guscio in sola lettura e chiamate alle rotte dedicate.
// Il controllo vero e' sul server; qui si nasconde solo cio' che l'ospite non puo' usare.
import { getJSON, send } from './api'
import { t } from './i18n/index.svelte'
import type { Tab } from './shell/nav'
import type { GuestStatus, Role } from './types'

/** Schede dell'ospite: mappa, nodi, rete (statistiche) e impostazioni ridotte (tema, lingua, esci). */
export const GUEST_TABS: readonly Tab[] = ['map', 'nodes', 'network', 'settings', 'more']

export const GUEST_PIN_MIN = 6
export const GUEST_PIN_MAX = 12

export function allowedTab(tab: Tab, role: Role): boolean {
  return role === 'admin' || GUEST_TABS.includes(tab)
}

export function tabsFor<T extends { id: Tab }>(list: readonly T[], role: Role): T[] {
  return list.filter((it) => allowedTab(it.id, role))
}

/** Scheda da mostrare: una non ammessa (link diretto, vista ricordata) ricade su «Nodi». */
export function safeTab(tab: Tab, role: Role): Tab {
  return allowedTab(tab, role) ? tab : 'nodes'
}

/** Viste di Rete: l'ospite non vede il registro dei pacchetti (contiene i testi dei messaggi). */
export function netViewsFor<T extends { value: string }>(views: T[], role: Role): T[] {
  return role === 'admin' ? views : views.filter((v) => v.value !== 'packets')
}

export function guestPinError(pin: string): string | null {
  if (!/^\d+$/.test(pin) || pin.length < GUEST_PIN_MIN || pin.length > GUEST_PIN_MAX)
    return t('guest.pinError', { min: GUEST_PIN_MIN, max: GUEST_PIN_MAX })
  return null
}

export const guestStatus = () => getJSON<GuestStatus>('/auth/guest')
export const setGuestPin = (pin: string) => send<GuestStatus>('PUT', '/auth/guest/pin', { pin })
export const clearGuestPin = () => send<GuestStatus>('DELETE', '/auth/guest/pin')
export const setGuestEnabled = (enabled: boolean) => send<GuestStatus>('PUT', '/auth/guest', { enabled })
