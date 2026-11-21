import { test, expect } from 'vitest'
import { THEME_KEY, colorSchemeFor, createTheme, loadPref, parsePref, resolveTheme, savePref, type ThemeEnv } from './theme'

function mkEnv(stored: string | null, systemDark: boolean) {
  const store = new Map<string, string>()
  if (stored !== null) store.set(THEME_KEY, stored)
  const attrs: Record<string, string> = {}
  const meta: Record<string, string> = {}
  let listener: ((e: { matches: boolean }) => void) | null = null
  const env: ThemeEnv = {
    storage: { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => void store.set(k, v) },
    root: { setAttribute: (n, v) => void (attrs[n] = v) },
    meta: { setAttribute: (n, v) => void (meta[n] = v) },
    media: {
      matches: systemDark,
      addEventListener: (_t, cb) => void (listener = cb),
      removeEventListener: (_t, cb) => {
        if (listener === cb) listener = null
      },
    },
  }
  return { env, store, attrs, meta, fire: (m: boolean) => listener?.({ matches: m }), hasListener: () => listener !== null }
}

test('parsePref e resolveTheme', () => {
  expect(parsePref('dark')).toBe('dark')
  expect(parsePref('boh')).toBe('auto')
  expect(parsePref(null)).toBe('auto')
  expect(resolveTheme('auto', true)).toBe('dark')
  expect(resolveTheme('auto', false)).toBe('light')
  expect(resolveTheme('light', true)).toBe('light')
  expect(resolveTheme('dark', false)).toBe('dark')
  expect(colorSchemeFor('auto')).toBe('dark light')
  expect(colorSchemeFor('light')).toBe('light')
})

test('load/save tollerano storage assente o che lancia', () => {
  expect(loadPref(null)).toBe('auto')
  expect(loadPref({ getItem: () => { throw new Error('x') } })).toBe('auto')
  expect(() => savePref({ setItem: () => { throw new Error('x') } }, 'dark')).not.toThrow()
})

test('createTheme: Auto segue il sistema, la scelta manuale si salva', () => {
  const t = mkEnv(null, true)
  const c = createTheme(t.env)
  expect(t.attrs['data-theme']).toBe('dark')
  expect(t.meta['content']).toBe('dark light')
  t.fire(false)
  expect(t.attrs['data-theme']).toBe('light')
  c.setPref('dark')
  expect(t.store.get(THEME_KEY)).toBe('dark')
  expect(t.attrs['data-theme']).toBe('dark')
  expect(t.meta['content']).toBe('dark')
  t.fire(false) // con tema manuale il sistema non conta
  expect(t.attrs['data-theme']).toBe('dark')
  c.destroy()
  expect(t.hasListener()).toBe(false)
})

test('createTheme legge la preferenza salvata e notifica gli iscritti', () => {
  const t = mkEnv('light', true)
  const c = createTheme(t.env)
  expect(c.pref()).toBe('light')
  expect(t.attrs['data-theme']).toBe('light')
  const seen: string[] = []
  const off = c.subscribe((th) => seen.push(th))
  c.setPref('dark')
  off()
  c.setPref('light')
  expect(seen).toEqual(['dark'])
})
