import { describe, expect, it, vi } from 'vitest'
import { dispatch, type WSHandlers } from './ws'

function handlers() {
  return {
    nodes: vi.fn(), message: vi.fn(), status: vi.fn(), radios: vi.fn(), alerts: vi.fn(),
    traceroute: vi.fn(), coverage: vi.fn(), messageStatus: vi.fn(), resync: vi.fn(),
  } satisfies WSHandlers
}

describe('dispatch', () => {
  it('resync chiama h.resync', () => {
    const h = handlers()
    dispatch({ type: 'resync' }, h)
    expect(h.resync).toHaveBeenCalledOnce()
  })
  it('status passa mqtt', () => {
    const h = handlers()
    const mqtt = { connected: true }
    dispatch({ type: 'status', mqtt }, h)
    expect(h.status).toHaveBeenCalledWith({ mqtt })
  })
  it('tipo ignoto o null: nessuna chiamata, nessuna eccezione', () => {
    const h = handlers()
    expect(() => { dispatch({ type: 'boh' }, h); dispatch(null, h); dispatch('x', h) }).not.toThrow()
    for (const f of Object.values(h)) expect(f).not.toHaveBeenCalled()
  })
})
