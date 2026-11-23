import { describe, expect, it, vi } from 'vitest'
import { CORE_WS_TYPES, dispatchExt, notifyWsResync, onWsEvent, onWsResync } from './wsext'
import { dispatch, type WSHandlers } from './ws'

function handlers() {
  return {
    nodes: vi.fn(), message: vi.fn(), status: vi.fn(), radios: vi.fn(), alerts: vi.fn(),
    traceroute: vi.fn(), coverage: vi.fn(), messageStatus: vi.fn(),
  } satisfies WSHandlers
}

describe('wsext', () => {
  it('un tipo nuovo arriva al gestore registrato, fino alla rimozione', () => {
    const fn = vi.fn()
    const off = onWsEvent('sensor_event', fn)
    const msg = { type: 'sensor_event', event: { id: 1 } }
    dispatch(msg, handlers())
    expect(fn).toHaveBeenCalledOnce()
    expect(fn).toHaveBeenCalledWith(msg)
    off()
    dispatch(msg, handlers())
    expect(fn).toHaveBeenCalledOnce()
  })

  it('dispatchExt senza gestori restituisce false', () => {
    expect(dispatchExt({ type: 'nessuno' })).toBe(false)
  })

  it('i tipi del nucleo non si registrano', () => {
    expect(() => onWsEvent('nodes', () => {})).toThrow()
    expect(CORE_WS_TYPES).toContain('message')
  })

  it('i tipi del nucleo non passano dalle estensioni', () => {
    const h = handlers()
    dispatch({ type: 'nodes', nodes: [] }, h)
    expect(h.nodes).toHaveBeenCalledOnce()
  })

  it('resync avvisa i gestori registrati', () => {
    const fn = vi.fn()
    const off = onWsResync(fn)
    notifyWsResync()
    expect(fn).toHaveBeenCalledOnce()
    off()
    notifyWsResync()
    expect(fn).toHaveBeenCalledOnce()
  })

  it('un gestore che lancia non ferma gli altri', () => {
    const bad = vi.fn(() => {
      throw new Error('x')
    })
    const good = vi.fn()
    const off1 = onWsEvent('tak_contact', bad)
    const off2 = onWsEvent('tak_contact', good)
    expect(dispatchExt({ type: 'tak_contact' })).toBe(true)
    expect(good).toHaveBeenCalledOnce()
    off1()
    off2()
    const r1 = vi.fn(() => {
      throw new Error('y')
    })
    const r2 = vi.fn()
    const o1 = onWsResync(r1)
    const o2 = onWsResync(r2)
    notifyWsResync()
    expect(r2).toHaveBeenCalledOnce()
    o1()
    o2()
  })
})
