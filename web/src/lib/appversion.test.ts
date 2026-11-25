import { beforeEach, describe, expect, it } from 'vitest'
import { noteServerVersion, staleVersion, ver } from './appversion.svelte'

describe('appversion', () => {
  beforeEach(() => {
    ver.loaded = null
    ver.server = null
  })
  it('la prima versione letta e quella caricata, nessun avviso', () => {
    noteServerVersion('1.6.1')
    expect(ver.loaded).toBe('1.6.1')
    expect(staleVersion(ver)).toBeNull()
  })
  it('stessa versione dopo una riconnessione: nessun avviso', () => {
    noteServerVersion('1.6.1')
    noteServerVersion('1.6.1')
    expect(staleVersion(ver)).toBeNull()
  })
  it('versione diversa: avviso con la nuova versione', () => {
    noteServerVersion('1.6.1')
    noteServerVersion('1.7.0')
    expect(ver.loaded).toBe('1.6.1')
    expect(staleVersion(ver)).toBe('1.7.0')
  })
  it('ignora valori non validi', () => {
    noteServerVersion(undefined)
    noteServerVersion('')
    expect(ver.loaded).toBeNull()
  })
})
