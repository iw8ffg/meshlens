import { beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({ notes: null as unknown, seen: 0, paths: [] as string[] }))
vi.mock('./api', () => ({
  getJSON: vi.fn(async (path: string) => {
    state.paths.push(path)
    return state.notes
  }),
  send: vi.fn(async (method: string, path: string) => {
    if (method === 'POST' && path === '/update/seen') state.seen++
    return { last_seen_version: '1.6.0' }
  }),
}))

import { closeWhatsNew, initWhatsNew, requestWhatsNew, whatsNew } from './whatsnew.svelte'

const rel = { version: '1.6.0', date: '2026-12-01', it: 'Novità', en: 'News' }

beforeEach(() => {
  state.seen = 0
  state.paths = []
  whatsNew.open = false
  whatsNew.data = null
  whatsNew.seen = false
})

describe('whatsNew', () => {
  it('requestWhatsNew scarica con force e apre; markSeen una volta alla chiusura', async () => {
    state.notes = { version: '1.6.0', last_seen: '1.6.0', show: true, releases: [rel] }
    await requestWhatsNew()
    expect(state.paths).toEqual(['/update/notes?force=1'])
    expect(whatsNew.open).toBe(true)
    expect(whatsNew.data?.releases[0].version).toBe('1.6.0')
    await closeWhatsNew()
    await closeWhatsNew()
    expect(whatsNew.open).toBe(false)
    expect(state.seen).toBe(1)
  })

  it('dopo un aggiornamento si apre da solo', async () => {
    state.notes = { version: '1.6.0', last_seen: '1.5.1', show: true, releases: [rel] }
    await initWhatsNew()
    expect(state.paths).toEqual(['/update/notes'])
    expect(whatsNew.open).toBe(true)
    expect(state.seen).toBe(0)
  })

  it('installazione nuova: nessuna finestra, versione registrata in silenzio', async () => {
    state.notes = { version: '1.6.0', last_seen: '', show: false, releases: [rel] }
    await initWhatsNew()
    expect(whatsNew.open).toBe(false)
    expect(state.seen).toBe(1)
  })

  it('stessa versione: niente da fare', async () => {
    state.notes = { version: '1.6.0', last_seen: '1.6.0', show: false, releases: [] }
    await initWhatsNew()
    expect(whatsNew.open).toBe(false)
    expect(state.seen).toBe(0)
  })
})
