import { afterEach, describe, expect, it } from 'vitest'
import { safeStorage } from './storage'

const desc = Object.getOwnPropertyDescriptor(globalThis, 'localStorage')

function restore(): void {
  if (desc) Object.defineProperty(globalThis, 'localStorage', desc)
  else delete (globalThis as { localStorage?: unknown }).localStorage
}

function fakeStorage(): Storage {
  const m = new Map<string, string>()
  return {
    get length() { return m.size },
    clear: () => m.clear(),
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    key: (i: number) => [...m.keys()][i] ?? null,
    removeItem: (k: string) => { m.delete(k) },
    setItem: (k: string, v: string) => { m.set(k, String(v)) },
  } as Storage
}

describe('safeStorage', () => {
  afterEach(restore)

  it('restituisce localStorage quando è accessibile', () => {
    const real = fakeStorage()
    Object.defineProperty(globalThis, 'localStorage', { configurable: true, get: () => real })
    expect(safeStorage()).toBe(real)
  })

  it('con accesso negato (SecurityError) restituisce uno shim funzionante in memoria', () => {
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() { throw new Error('SecurityError: access denied') },
    })
    const s = safeStorage()
    s.clear()
    expect(s.getItem('x')).toBeNull()
    s.setItem('x', 'valore')
    expect(s.getItem('x')).toBe('valore')
    expect(s.length).toBe(1)
    expect(s.key(0)).toBe('x')
    s.removeItem('x')
    expect(s.getItem('x')).toBeNull()
    s.setItem('a', '1')
    s.clear()
    expect(s.length).toBe(0)
  })

  it('lo shim non lancia quando l\'accesso è negato anche più volte', () => {
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get() { throw new Error('SecurityError') },
    })
    expect(() => safeStorage().setItem('k', 'v')).not.toThrow()
    expect(safeStorage().getItem('k')).toBe('v')
  })

  it('senza localStorage definito restituisce lo shim, senza errori', () => {
    delete (globalThis as { localStorage?: unknown }).localStorage
    const s = safeStorage()
    s.setItem('k', 'v')
    expect(s.getItem('k')).toBe('v')
  })
})
