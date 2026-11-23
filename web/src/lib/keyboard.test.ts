import { describe, expect, it } from 'vitest'
import { isSearchShortcut } from './keyboard'

const ev = (over: Partial<Parameters<typeof isSearchShortcut>[0]>) => ({ key: 'k', ctrlKey: false, metaKey: false, altKey: false, shiftKey: false, ...over })

describe('isSearchShortcut', () => {
  it('Ctrl+K, Cmd+K e K maiuscola (CapsLock)', () => {
    expect(isSearchShortcut(ev({ ctrlKey: true }))).toBe(true)
    expect(isSearchShortcut(ev({ metaKey: true }))).toBe(true)
    expect(isSearchShortcut(ev({ ctrlKey: true, key: 'K' }))).toBe(true)
  })
  it('non scatta senza modificatori, con Alt, con Maiusc o con un altro tasto', () => {
    expect(isSearchShortcut(ev({}))).toBe(false)
    expect(isSearchShortcut(ev({ ctrlKey: true, altKey: true }))).toBe(false)
    expect(isSearchShortcut(ev({ ctrlKey: true, shiftKey: true }))).toBe(false)
    expect(isSearchShortcut(ev({ ctrlKey: true, key: 'j' }))).toBe(false)
  })
  it('ignora composizione IME, ripetizione ed eventi gia gestiti', () => {
    expect(isSearchShortcut(ev({ ctrlKey: true, isComposing: true }))).toBe(false)
    expect(isSearchShortcut(ev({ ctrlKey: true, repeat: true }))).toBe(false)
    expect(isSearchShortcut(ev({ ctrlKey: true, defaultPrevented: true }))).toBe(false)
  })
})
