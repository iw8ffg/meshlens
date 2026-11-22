// Ponte a callback (senza stato reattivo) per cambiare scheda da componenti lontani da App.
import type { Tab } from './nav'
import { t } from '../i18n/index.svelte'

let navigator: ((tab: Tab) => void) | null = null

export function setNavigator(fn: ((tab: Tab) => void) | null): void {
  navigator = fn
}

/** Apre la scheda; `false` se nessun navigatore è registrato. */
export function navigate(tab: Tab): boolean {
  if (!navigator) return false
  navigator(tab)
  return true
}

export interface EmptyHint {
  title: string
  text: string
  action: { label: string; tab: Tab } | null
}

export function emptyFeedHint(mqtt: { connected: boolean } | null): EmptyHint {
  const title = t('chat.empty.title')
  if (mqtt === null) return { title, text: t('chat.empty.feedNone'), action: null }
  if (!mqtt.connected) {
    return { title, text: t('chat.empty.mqttDown'), action: { label: t('chat.empty.openSettings'), tab: 'settings' } }
  }
  return { title, text: t('chat.empty.feedFiltered'), action: null }
}

export function emptyRadioHint(connectedRadios: number): EmptyHint {
  const title = t('chat.empty.title')
  if (connectedRadios === 0) {
    return { title, text: t('chat.empty.noRadio'), action: { label: t('chat.empty.goRadio'), tab: 'radio' } }
  }
  return { title, text: t('chat.empty.convNone'), action: null }
}
