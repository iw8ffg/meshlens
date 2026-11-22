import { describe, expect, it } from 'vitest'
import { t } from '../i18n/index.svelte'
import { CHAT_EXPANDED_KEY, loadChatExpanded, saveChatExpanded } from './nav'
import { PANEL_DEFAULT, PANEL_KEY, PANEL_MAX, PANEL_MIN, PHONE_NAV, clampPanelWidth, effectiveTab, isMoreTab, isPageTab, loadPanelWidth, navActive, savePanelWidth, sheetVisible } from './nav'

describe('schede', () => {
  it('la barra in basso ha cinque voci nell\'ordine del design', () => {
    expect(PHONE_NAV.map((n) => t(n.labelKey))).toEqual(['Mappa', 'Nodi', 'Messaggi', 'Copertura', 'Altro'])
  })
  it('Rete, Radio e Impostazioni accendono «Altro»', () => {
    expect(navActive('network')).toBe('more')
    expect(navActive('radio')).toBe('more')
    expect(navActive('settings')).toBe('more')
    expect(navActive('chat')).toBe('chat')
    expect(isMoreTab('coverage')).toBe(false)
  })
  it('su desktop mappa e altro diventano nodi', () => {
    expect(effectiveTab('map', false)).toBe('nodes')
    expect(effectiveTab('more', false)).toBe('nodes')
    expect(effectiveTab('chat', false)).toBe('chat')
    expect(effectiveTab('map', true)).toBe('map')
  })
  it('pagine lunghe e visibilità dello sheet', () => {
    expect(isPageTab('network')).toBe(true)
    expect(isPageTab('chat')).toBe(false)
    expect(isPageTab('chat', true)).toBe(true)
    expect(isPageTab('nodes', true)).toBe(false)
    expect(sheetVisible('map', false)).toBe(false)
    expect(sheetVisible('map', true)).toBe(true)
    expect(sheetVisible('nodes', false)).toBe(true)
  })
})

describe('larghezza del pannello', () => {
  it('limita tra 320 e 560', () => {
    expect(clampPanelWidth(100)).toBe(PANEL_MIN)
    expect(clampPanelWidth(900)).toBe(PANEL_MAX)
    expect(clampPanelWidth(400.4)).toBe(400)
    expect(clampPanelWidth(NaN)).toBe(PANEL_DEFAULT)
  })
  it('legge e salva in localStorage', () => {
    const m = new Map<string, string>()
    const st = { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }
    expect(loadPanelWidth(st)).toBe(PANEL_DEFAULT)
    savePanelWidth(st, 9999)
    expect(m.get(PANEL_KEY)).toBe('560')
    expect(loadPanelWidth(st)).toBe(560)
    m.set(PANEL_KEY, 'boh')
    expect(loadPanelWidth(st)).toBe(PANEL_DEFAULT)
    expect(loadPanelWidth(null)).toBe(PANEL_DEFAULT)
  })
  it('non si rompe se lo storage lancia', () => {
    const bad = { getItem: () => { throw new Error('x') }, setItem: () => { throw new Error('x') } }
    expect(loadPanelWidth(bad)).toBe(PANEL_DEFAULT)
    expect(() => savePanelWidth(bad, 400)).not.toThrow()
  })
})

describe('Messaggi espansi', () => {
  it('predefinito ridotto, scelta salvata e riletta, storage rotto tollerato', () => {
    const m = new Map<string, string>()
    const st = { getItem: (k: string) => m.get(k) ?? null, setItem: (k: string, v: string) => void m.set(k, v) }
    expect(loadChatExpanded(st)).toBe(false)
    saveChatExpanded(st, true)
    expect(m.get(CHAT_EXPANDED_KEY)).toBe('1')
    expect(loadChatExpanded(st)).toBe(true)
    saveChatExpanded(st, false)
    expect(loadChatExpanded(st)).toBe(false)
    const broken = { getItem: () => { throw new Error('x') }, setItem: () => { throw new Error('x') } }
    expect(loadChatExpanded(broken)).toBe(false)
    expect(() => saveChatExpanded(broken, true)).not.toThrow()
    expect(loadChatExpanded(null)).toBe(false)
  })
})
