import { expect, test, vi } from 'vitest'

// stores.svelte legge la vista salvata all'import: serve un localStorage finto
const mem = new Map<string, string>()
vi.stubGlobal('localStorage', { getItem: (k: string) => mem.get(k) ?? null, setItem: (k: string, v: string) => void mem.set(k, v), removeItem: (k: string) => void mem.delete(k) })
const { attachChat, carryOpenChat, openChat, setOpenChat } = await import('./stores.svelte')

test('carryOpenChat: la conversazione aperta passa alla chat ricreata, con la vecchia ancora attaccata o già staccata', () => {
  const opened: string[] = []
  const old = attachChat((k) => opened.push('old:' + k))
  setOpenChat('dm:1:!a')
  carryOpenChat()
  const fresh = attachChat((k) => opened.push('new:' + k))
  old.detach() // staccare la vecchia dopo la nuova non deve cancellare nulla della nuova
  expect(fresh.pending).toBe('dm:1:!a')
  openChat('ch:1:0')
  expect(opened).toEqual(['new:ch:1:0'])
  fresh.detach()
})

test('carryOpenChat con l\'elenco aperto non riapre nulla', () => {
  const a = attachChat(() => {})
  setOpenChat(null)
  carryOpenChat()
  a.detach()
  const b = attachChat(() => {})
  expect(b.pending).toBeNull()
  b.detach()
})
