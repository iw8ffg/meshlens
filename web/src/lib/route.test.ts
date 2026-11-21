import { describe, expect, it } from 'vitest'
import { formatHash, nodeLink, parseHash } from './route'

describe('parseHash', () => {
  it('link a un nodo: id normalizzato con ! e minuscole', () => {
    expect(parseHash('#/nodes/!ABCDEF01')).toEqual({ tab: 'nodes', nodeId: '!abcdef01' })
    expect(parseHash('#/nodes/abcdef01')).toEqual({ tab: 'nodes', nodeId: '!abcdef01' })
  })
  it('id malformato: nessuna route', () => {
    expect(parseHash('#/nodes/!abc')).toEqual({ tab: null, nodeId: null })
    expect(parseHash('#/nodes/!abcdef012')).toEqual({ tab: null, nodeId: null })
    expect(parseHash('#/nodes/!abcdefgh')).toEqual({ tab: null, nodeId: null })
  })
  it('schede note', () => {
    expect(parseHash('#/network')).toEqual({ tab: 'network', nodeId: null })
    expect(parseHash('#/map')).toEqual({ tab: 'map', nodeId: null })
    expect(parseHash('#/nodes')).toEqual({ tab: 'nodes', nodeId: null })
  })
  it('«more», vuoto e sconosciuti: tutto null', () => {
    expect(parseHash('#/more')).toEqual({ tab: null, nodeId: null })
    expect(parseHash('')).toEqual({ tab: null, nodeId: null })
    expect(parseHash('#/boh')).toEqual({ tab: null, nodeId: null })
    expect(parseHash('#/network/x')).toEqual({ tab: null, nodeId: null })
  })
})

describe('formatHash', () => {
  it('scheda', () => {
    expect(formatHash({ tab: 'chat', nodeId: null })).toBe('#/chat')
  })
  it('il nodo vince sulla scheda', () => {
    expect(formatHash({ tab: 'map', nodeId: '!0000abcd' })).toBe('#/nodes/!0000abcd')
  })
  it('nessuna scheda: stringa vuota', () => {
    expect(formatHash({ tab: null, nodeId: null })).toBe('')
  })
})

describe('nodeLink', () => {
  it('origine + percorso + hash del nodo', () => {
    expect(nodeLink('!0000abcd', { origin: 'http://127.0.0.1:8686', pathname: '/' })).toBe(
      'http://127.0.0.1:8686/#/nodes/!0000abcd',
    )
  })
})
