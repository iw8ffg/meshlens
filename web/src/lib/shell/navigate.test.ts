import { afterEach, describe, expect, it, vi } from 'vitest'
import { emptyFeedHint, emptyRadioHint, navigate, setNavigator } from './navigate'

afterEach(() => setNavigator(null))

describe('navigate', () => {
  it('senza navigatore registrato restituisce false', () => {
    expect(navigate('chat')).toBe(false)
  })
  it('con navigatore lo chiama e restituisce true', () => {
    const fn = vi.fn()
    setNavigator(fn)
    expect(navigate('chat')).toBe(true)
    expect(fn).toHaveBeenCalledWith('chat')
  })
})

describe('emptyFeedHint', () => {
  it('MQTT non connesso propone Impostazioni', () => {
    const h = emptyFeedHint({ connected: false })
    expect(h.action?.tab).toBe('settings')
    expect(h.action?.label).toBe('Apri Impostazioni')
    expect(h.text).toBe('MQTT non è connesso: controlla broker e argomento.')
  })
  it('stato nullo: messaggio neutro senza azione', () => {
    const h = emptyFeedHint(null)
    expect(h.action).toBeNull()
    expect(h.title).toBe('Nessun messaggio')
  })
  it('MQTT connesso senza azione', () => {
    const h = emptyFeedHint({ connected: true })
    expect(h.action).toBeNull()
    expect(h.text).toBe('Nessun messaggio ricevuto finora con i filtri attuali.')
  })
})

describe('emptyRadioHint', () => {
  it('senza radio connesse propone Radio', () => {
    const h = emptyRadioHint(0)
    expect(h.action).toEqual({ label: 'Vai a Radio', tab: 'radio' })
    expect(h.text).toBe('Collega una radio per leggere e inviare sui canali della tua rete.')
  })
  it('con radio connesse nessuna azione', () => {
    const h = emptyRadioHint(1)
    expect(h.action).toBeNull()
    expect(h.text).toBe('Ancora nessun messaggio su questa conversazione.')
  })
})
