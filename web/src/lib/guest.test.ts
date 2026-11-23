import { describe, expect, it, vi, beforeEach } from 'vitest'
import { allowedTab, guestPinError, netViewsFor, safeTab, tabsFor, GUEST_TABS } from './guest'
import { DESKTOP_TABS, MORE_TABS, PHONE_NAV } from './shell/nav'

describe('schede per ruolo', () => {
  it("l'admin vede tutto", () => {
    expect(tabsFor(DESKTOP_TABS, 'admin')).toEqual(DESKTOP_TABS)
    for (const t of ['chat', 'radio', 'coverage', 'settings'] as const) expect(allowedTab(t, 'admin')).toBe(true)
  })

  it("l'ospite vede solo mappa, nodi, rete e impostazioni ridotte", () => {
    expect(tabsFor(DESKTOP_TABS, 'guest').map((t) => t.id)).toEqual(['nodes', 'network', 'settings'])
    expect(tabsFor(PHONE_NAV, 'guest').map((t) => t.id)).toEqual(['map', 'nodes', 'more'])
    expect(tabsFor(MORE_TABS, 'guest').map((t) => t.id)).toEqual(['network', 'settings'])
    for (const t of ['chat', 'radio', 'coverage'] as const) expect(allowedTab(t, 'guest')).toBe(false)
    expect(GUEST_TABS).not.toContain('chat')
  })

  it('una scheda non ammessa ricade su nodi', () => {
    expect(safeTab('chat', 'guest')).toBe('nodes')
    expect(safeTab('map', 'guest')).toBe('map')
    expect(safeTab('chat', 'admin')).toBe('chat')
  })

  it("le viste di Rete dell'ospite non hanno il registro pacchetti", () => {
    const views = [{ value: 'nodes' }, { value: 'stats' }, { value: 'packets' }, { value: 'topology' }] as const
    expect(netViewsFor([...views], 'guest').map((v) => v.value)).toEqual(['nodes', 'stats', 'topology'])
    expect(netViewsFor([...views], 'admin')).toHaveLength(4)
  })
})

describe('PIN ospite', () => {
  it('servono 6-12 cifre', () => {
    expect(guestPinError('12345')).not.toBeNull()
    expect(guestPinError('12a456')).not.toBeNull()
    expect(guestPinError('1234567890123')).not.toBeNull()
    expect(guestPinError('123456')).toBeNull()
  })
})

describe('chiamate API', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('usano le rotte dedicate', async () => {
    const calls: [string, string | undefined][] = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      calls.push([url, init?.method])
      return new Response(JSON.stringify({ enabled: false }), { status: 200, headers: { 'Content-Type': 'application/json' } })
    }))
    const g = await import('./guest')
    await g.guestStatus()
    await g.setGuestPin('123456')
    await g.clearGuestPin()
    await g.setGuestEnabled(true)
    expect(calls).toEqual([
      ['/api/auth/guest', 'GET'],
      ['/api/auth/guest/pin', 'PUT'],
      ['/api/auth/guest/pin', 'DELETE'],
      ['/api/auth/guest', 'PUT'],
    ])
    vi.unstubAllGlobals()
  })
})
