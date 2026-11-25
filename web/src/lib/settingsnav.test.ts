import { describe, expect, it } from 'vitest'
import { SETTINGS_SECTIONS, pickActive, requestSettingsJump, takeSettingsJump, visibleSections } from './settingsnav'
import { SETTINGS_ENTRIES } from './globalsearch'

describe('visibleSections', () => {
  it('prima del caricamento restano solo le sezioni sempre presenti', () => {
    expect(visibleSections(false).map((s) => s.id)).toEqual(['appearance', 'diag', 'about'])
  })
  it('a caricamento finito ci sono tutte, in ordine e con id unici', () => {
    const all = visibleSections(true)
    expect(all).toEqual(SETTINGS_SECTIONS)
    expect(new Set(all.map((s) => s.id)).size).toBe(all.length)
  })
  it('gli id della ricerca globale esistono tra le sezioni', () => {
    const ids = SETTINGS_SECTIONS.map((s) => s.id)
    for (const e of SETTINGS_ENTRIES) expect(ids).toContain(e.id)
  })
})

describe('pickActive', () => {
  const tops = [
    { id: 'a', top: -300 },
    { id: 'b', top: -20 },
    { id: 'c', top: 400 },
  ]
  it('ultima sezione oltre la linea', () => expect(pickActive(tops, 0)).toBe('b'))
  it("scorrendo piu' in la passa alla successiva", () => expect(pickActive(tops, 450)).toBe('c'))
  it('se nessuna ha superato la linea resta la prima', () =>
    expect(pickActive([{ id: 'x', top: 90 }, { id: 'y', top: 500 }], 10)).toBe('x'))
  it('elenco vuoto', () => expect(pickActive([], 0)).toBeNull())
})

describe('richiesta di salto', () => {
  it('si consuma una sola volta', () => {
    requestSettingsJump('mqtt')
    expect(takeSettingsJump()).toBe('mqtt')
    expect(takeSettingsJump()).toBeNull()
  })
})
