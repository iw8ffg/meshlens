import type { Message } from './types'

export const NOTIFY_KEY = 'meshlens.notify'

export interface NotifyPrefs {
  dm: boolean
}

export function loadNotifyPrefs(storage: Pick<Storage, 'getItem'>): NotifyPrefs {
  try {
    const raw = storage.getItem(NOTIFY_KEY)
    if (!raw) return { dm: false }
    const p = JSON.parse(raw)
    return { dm: p?.dm === true }
  } catch {
    return { dm: false }
  }
}

export function saveNotifyPrefs(storage: Pick<Storage, 'setItem'>, p: NotifyPrefs): void {
  try {
    storage.setItem(NOTIFY_KEY, JSON.stringify({ v: 1, dm: p.dm }))
  } catch {
    /* archivio pieno o non disponibile */
  }
}

export function notifySupported(win: { isSecureContext?: boolean; [k: string]: unknown }): boolean {
  return 'Notification' in win && win.isSecureContext === true
}

/** Solo i diretti, non le reazioni, con permesso concesso e scheda non visibile. */
export function shouldNotify(m: Message, key: string, prefs: NotifyPrefs, permission: NotificationPermission, hidden: boolean): boolean {
  return prefs.dm && key.startsWith('dm:') && !m.emoji && permission === 'granted' && hidden
}

export function titleFor(base: string, n: number): string {
  if (n <= 0) return base
  return `(${n > 99 ? '99+' : n}) ${base}`
}
