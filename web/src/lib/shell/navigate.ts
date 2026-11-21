// Ponte a callback (senza stato reattivo) per cambiare scheda da componenti lontani da App.
import type { Tab } from './nav'

let navigator: ((t: Tab) => void) | null = null

export function setNavigator(fn: ((t: Tab) => void) | null): void {
  navigator = fn
}

/** Apre la scheda; `false` se nessun navigatore è registrato. */
export function navigate(t: Tab): boolean {
  if (!navigator) return false
  navigator(t)
  return true
}

export interface EmptyHint {
  title: string
  text: string
  action: { label: string; tab: Tab } | null
}

export function emptyFeedHint(mqtt: { connected: boolean } | null, _radios: number): EmptyHint {
  if (!mqtt?.connected) {
    return {
      title: 'Nessun messaggio',
      text: 'MQTT non è connesso: controlla broker e argomento.',
      action: { label: 'Apri Impostazioni', tab: 'settings' },
    }
  }
  return { title: 'Nessun messaggio', text: 'Nessun messaggio ricevuto finora con i filtri attuali.', action: null }
}

export function emptyRadioHint(connectedRadios: number): EmptyHint {
  if (connectedRadios === 0) {
    return {
      title: 'Nessun messaggio',
      text: 'Collega una radio per leggere e inviare sui canali della tua rete.',
      action: { label: 'Vai a Radio', tab: 'radio' },
    }
  }
  return { title: 'Nessun messaggio', text: 'Ancora nessun messaggio su questa conversazione.', action: null }
}
