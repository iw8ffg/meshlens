import { beforeEach, describe, expect, it, vi } from 'vitest'

const getJSON = vi.fn()
vi.mock('../api', () => ({ getJSON: (p: string) => getJSON(p) }))

type Handler = (m: Record<string, unknown>) => void
const wsHandlers = new Map<string, Handler>()
const resync: { fn: (() => void) | null } = { fn: null }
const offEvent = vi.fn()
const offResync = vi.fn()
const onWsEvent = vi.fn((type: string, fn: Handler) => {
  wsHandlers.set(type, fn)
  return offEvent
})
const onWsResync = vi.fn((fn: () => void) => {
  resync.fn = fn
  return offResync
})
vi.mock('../wsext', () => ({ onWsEvent: (t: string, f: Handler) => onWsEvent(t, f), onWsResync: (f: () => void) => onWsResync(f) }))

import { contactName, mergeContact, takRoleKey, takTeamKey } from './takData'
import { loadTak, startTakLive, tak } from './takData.svelte'
import type { TakContact } from '../types'

const c = (o: Partial<TakContact>): TakContact => ({ node_id: '!a', callsign: 'ALFA', device_callsign: null, team: null, role: null, battery: null, lat: 45, lon: 9, altitude: null, speed: null, course: null, compressed: false, time: 100, source: 'rf', ...o })

beforeEach(() => {
  getJSON.mockReset()
  onWsEvent.mockClear()
  onWsResync.mockClear()
  offEvent.mockClear()
  offResync.mockClear()
  wsHandlers.clear()
  tak.contacts = new Map()
  tak.loaded = false
  tak.error = false
  tak.summary = null
})

describe('mergeContact', () => {
  it('aggiunge, sostituisce il piu\' nuovo, ignora il piu\' vecchio, non muta', () => {
    const base = new Map<string, TakContact>()
    const one = mergeContact(base, c({ time: 100 }))
    expect(base.size).toBe(0)
    expect(one.get('!a')!.time).toBe(100)
    expect(mergeContact(one, c({ time: 200, callsign: 'B' })).get('!a')!.callsign).toBe('B')
    const kept = mergeContact(one, c({ time: 50, callsign: 'OLD' }))
    expect(kept.get('!a')!.callsign).toBe('ALFA')
    expect(one.get('!a')!.callsign).toBe('ALFA')
  })
})

describe('chiavi e nomi', () => {
  it('ruolo e squadra', () => {
    expect(takRoleKey('TeamLead')).toBe('tak.role.TeamLead')
    expect(takRoleKey('Boh')).toBeNull()
    expect(takRoleKey(null)).toBeNull()
    expect(takTeamKey('Dark_Blue')).toBe('tak.team.Dark_Blue')
    expect(takTeamKey('Boh')).toBeNull()
  })
  it('contactName', () => {
    expect(contactName(c({}), () => 'nodo')).toBe('ALFA')
    expect(contactName(c({ callsign: null }), (id) => `nodo ${id}`)).toBe('nodo !a')
  })
})

describe('loadTak', () => {
  it('carica contatti e riepilogo', async () => {
    getJSON.mockImplementation(async (p: string) => (p.startsWith('/tak/contacts') ? [c({}), c({ node_id: '!b' })] : { contacts: 2, compressed: 0, unsupported_v2: 0 }))
    await loadTak()
    expect(getJSON.mock.calls.map((x) => x[0]).sort()).toEqual(['/tak/contacts?hours=24', '/tak/summary?hours=24'])
    expect(tak.loaded).toBe(true)
    expect(tak.contacts.size).toBe(2)
  })
  it('errore: error true, nessuna eccezione', async () => {
    getJSON.mockRejectedValue(new Error('x'))
    await expect(loadTak()).resolves.toBeUndefined()
    expect(tak.error).toBe(true)
  })
})

describe('startTakLive', () => {
  it('registra, aggiorna e conta i riferimenti', () => {
    const stop1 = startTakLive()
    const stop2 = startTakLive()
    expect(onWsEvent).toHaveBeenCalledTimes(1)
    expect(onWsEvent.mock.calls[0][0]).toBe('tak_contact')
    expect(onWsResync).toHaveBeenCalledTimes(1)
    wsHandlers.get('tak_contact')!({ type: 'tak_contact', contact: c({ time: 300 }) })
    expect(tak.contacts.get('!a')!.time).toBe(300)
    stop1()
    stop1()
    expect(offEvent).not.toHaveBeenCalled()
    stop2()
    expect(offEvent).toHaveBeenCalledTimes(1)
    expect(offResync).toHaveBeenCalledTimes(1)
  })
})
