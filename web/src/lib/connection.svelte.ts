import { locale, t } from './i18n/index.svelte'

export const SHOW_AFTER_MS = 3000
export const RESTORED_MS = 4000

export interface ConnState {
  online: boolean
  lostAt: number | null
  attempts: number
  restoredAt: number | null
}

export const conn = $state<ConnState>({ online: true, lostAt: null, attempts: 0, restoredAt: null })

export function markOnline(now: number): void {
  if (!conn.online) conn.restoredAt = now
  conn.online = true
  conn.lostAt = null
  conn.attempts = 0
}

/** Azzera lo stato (nuovo accesso): nessun "Connessione ripristinata" spurio. */
export function resetConn(): void {
  conn.online = true
  conn.lostAt = null
  conn.attempts = 0
  conn.restoredAt = null
}

export function markOffline(now: number): void {
  conn.online = false
  if (conn.lostAt === null) conn.lostAt = now
  conn.attempts++
}

export interface ConnView {
  show: boolean
  tone: 'warn' | 'ok'
  text: string
  retry: boolean
}

const HIDDEN: ConnView = { show: false, tone: 'warn', text: '', retry: false }
const hhmm = (ms: number) => new Intl.DateTimeFormat(locale(), { hour: '2-digit', minute: '2-digit' }).format(ms)

export function connectionView(c: ConnState, nowMs: number, browserOnline: boolean): ConnView {
  if (!c.online) {
    if (c.lostAt === null || nowMs - c.lostAt < SHOW_AFTER_MS) return HIDDEN
    if (!browserOnline) {
      return { show: true, tone: 'warn', text: t('shell.connOffline'), retry: false }
    }
    return {
      show: true,
      tone: 'warn',
      text: t('shell.connLost', { time: hhmm(c.lostAt) }),
      retry: true,
    }
  }
  if (c.restoredAt !== null && nowMs - c.restoredAt < RESTORED_MS) {
    return { show: true, tone: 'ok', text: t('shell.connRestored'), retry: false }
  }
  return HIDDEN
}
