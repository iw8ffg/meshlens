import { beforeEach, describe, expect, it } from 'vitest'
import { conn, connectionView, markOffline, markOnline, RESTORED_MS, SHOW_AFTER_MS } from './connection.svelte'

const T0 = Date.UTC(2026, 10, 21, 10, 30, 0)
const hhmm = (ms: number) => new Intl.DateTimeFormat('it-IT', { hour: '2-digit', minute: '2-digit' }).format(ms)

describe('connectionView', () => {
  it('offline da meno di 3 s: non mostra', () => {
    const c = { online: false, lostAt: T0, attempts: 1, restoredAt: null }
    expect(connectionView(c, T0 + SHOW_AFTER_MS - 1, true).show).toBe(false)
  })
  it('offline da 3 s con browser offline', () => {
    const c = { online: false, lostAt: T0, attempts: 1, restoredAt: null }
    expect(connectionView(c, T0 + SHOW_AFTER_MS, false)).toEqual({
      show: true, tone: 'warn', text: 'Il dispositivo è offline: i dati sono fermi', retry: false,
    })
  })
  it('offline da 3 s con browser online', () => {
    const c = { online: false, lostAt: T0, attempts: 2, restoredAt: null }
    expect(connectionView(c, T0 + SHOW_AFTER_MS, true)).toEqual({
      show: true, tone: 'warn',
      text: `Connessione al server persa: i dati sono fermi dalle ${hhmm(T0)}. Nuovo tentativo in corso…`,
      retry: true,
    })
  })
  it('online con restoredAt entro 4 s', () => {
    const c = { online: true, lostAt: null, attempts: 0, restoredAt: T0 }
    expect(connectionView(c, T0 + RESTORED_MS - 1, true)).toEqual({
      show: true, tone: 'ok', text: 'Connessione ripristinata', retry: false,
    })
  })
  it('altri casi: non mostra', () => {
    expect(connectionView({ online: true, lostAt: null, attempts: 0, restoredAt: null }, T0, true).show).toBe(false)
    expect(connectionView({ online: true, lostAt: null, attempts: 0, restoredAt: T0 }, T0 + RESTORED_MS, true).show).toBe(false)
  })
})

describe('markOffline / markOnline', () => {
  beforeEach(() => {
    conn.online = true; conn.lostAt = null; conn.attempts = 0; conn.restoredAt = null
  })
  it('markOffline due volte: attempts 2, lostAt invariato', () => {
    markOffline(T0)
    markOffline(T0 + 5000)
    expect(conn.online).toBe(false)
    expect(conn.attempts).toBe(2)
    expect(conn.lostAt).toBe(T0)
  })
  it('markOnline dopo markOffline: restoredAt e attempts 0', () => {
    markOffline(T0)
    markOnline(T0 + 7000)
    expect(conn.online).toBe(true)
    expect(conn.restoredAt).toBe(T0 + 7000)
    expect(conn.attempts).toBe(0)
    expect(conn.lostAt).toBeNull()
  })
  it('markOnline senza offline precedente: nessun restoredAt', () => {
    markOnline(T0)
    expect(conn.restoredAt).toBeNull()
  })
})
