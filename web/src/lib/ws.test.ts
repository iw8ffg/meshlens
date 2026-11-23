import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { connectWS, dispatch, reconnectNow, type WSHandlers } from './ws'

function handlers() {
  return {
    nodes: vi.fn(), message: vi.fn(), status: vi.fn(), radios: vi.fn(), alerts: vi.fn(),
    traceroute: vi.fn(), coverage: vi.fn(), messageStatus: vi.fn(), resync: vi.fn(),
    waypoint: vi.fn(), waypointDeleted: vi.fn(), convRead: vi.fn(),
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
  it('waypoint, waypoint_deleted, conv_read e message_status con errore', () => {
    const h = handlers()
    const waypoint = { id: 7 }
    dispatch({ type: 'waypoint', waypoint }, h)
    expect(h.waypoint).toHaveBeenCalledWith(waypoint)
    dispatch({ type: 'waypoint_deleted', id: 7 }, h)
    expect(h.waypointDeleted).toHaveBeenCalledWith(7)
    dispatch({ type: 'conv_read', key: 'dm:r1:!b', time: 5 }, h)
    expect(h.convRead).toHaveBeenCalledWith('dm:r1:!b', 5)
    dispatch({ type: 'message_status', key: 'k', status: 'failed', error: 'NO_ROUTE' }, h)
    expect(h.messageStatus).toHaveBeenCalledWith('k', 'failed', 'NO_ROUTE')
  })
  it('sf_job e sf_routers chiamano i gestori', () => {
    const sf_job = vi.fn()
    const sf_routers = vi.fn()
    const h = { ...handlers(), sf_job, sf_routers }
    dispatch({ type: 'sf_job', job: { id: 'j' } }, h)
    dispatch({ type: 'sf_routers', routers: [{ id: '!a' }] }, h)
    expect(sf_job).toHaveBeenCalledWith({ id: 'j' })
    expect(sf_routers).toHaveBeenCalledWith([{ id: '!a' }])
  })
  it('prediction_job chiama il gestore; senza gestore non solleva', () => {
    const prediction_job = vi.fn()
    dispatch({ type: 'prediction_job', job: { id: 'p' } }, { ...handlers(), prediction_job })
    expect(prediction_job).toHaveBeenCalledWith({ id: 'p' })
    expect(() => dispatch({ type: 'prediction_job', job: {} }, handlers())).not.toThrow()
  })
  it('sf_job senza gestore: nessuna eccezione', () => {
    expect(() => dispatch({ type: 'sf_job', job: {} }, handlers())).not.toThrow()
  })
  it('tipo ignoto o null: nessuna chiamata, nessuna eccezione', () => {
    const h = handlers()
    expect(() => { dispatch({ type: 'boh' }, h); dispatch(null, h); dispatch('x', h) }).not.toThrow()
    for (const f of Object.values(h)) expect(f).not.toHaveBeenCalled()
  })
})

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  onopen: (() => void) | null = null
  onclose: ((ev: { code: number }) => void) | null = null
  onmessage: ((ev: { data: string }) => void) | null = null
  constructor(public url: string) { FakeWebSocket.instances.push(this) }
  close() {}
}

describe('connectWS: connessione', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:8000' })
    vi.stubGlobal('window', { dispatchEvent: vi.fn() })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })
  const make = () => {
    const connection = vi.fn()
    const stop = connectWS({ ...handlers(), connection })
    return { connection, stop }
  }

  it('onopen: connection(true)', () => {
    const { connection, stop } = make()
    FakeWebSocket.instances[0].onopen?.()
    expect(connection).toHaveBeenCalledWith(true)
    stop()
  })
  it('onclose 1006: connection(false)', () => {
    const { connection, stop } = make()
    FakeWebSocket.instances[0].onclose?.({ code: 1006 })
    expect(connection).toHaveBeenCalledWith(false)
    stop()
  })
  it('onclose 4401: chiama authLost', () => {
    const authLost = vi.fn()
    const stop = connectWS({ ...handlers(), authLost })
    FakeWebSocket.instances[0].onclose?.({ code: 4401 })
    expect(authLost).toHaveBeenCalledOnce()
    stop()
  })

  it('onclose 4401: nessun connection(false)', () => {
    const { connection, stop } = make()
    FakeWebSocket.instances[0].onclose?.({ code: 4401 })
    expect(connection).not.toHaveBeenCalled()
    stop()
  })
  it('reconnectNow dopo una chiusura apre subito un secondo WebSocket', () => {
    const { stop } = make()
    FakeWebSocket.instances[0].onclose?.({ code: 1006 })
    expect(FakeWebSocket.instances).toHaveLength(1)
    reconnectNow()
    expect(FakeWebSocket.instances).toHaveLength(2)
    vi.advanceTimersByTime(3000)
    expect(FakeWebSocket.instances).toHaveLength(2) // il timer annullato non apre un terzo
    stop()
  })
  it('dopo la chiusura voluta reconnectNow non apre nulla', () => {
    const { connection, stop } = make()
    FakeWebSocket.instances[0].onclose?.({ code: 1006 })
    stop()
    reconnectNow()
    expect(FakeWebSocket.instances).toHaveLength(1)
    connection.mockClear()
    FakeWebSocket.instances[0].onclose?.({ code: 1000 })
    expect(connection).not.toHaveBeenCalled()
  })
})

describe('connectWS: socket mezzo aperto', () => {
  let winListeners: Record<string, () => void>
  let docListeners: Record<string, () => void>
  beforeEach(() => {
    vi.useFakeTimers()
    FakeWebSocket.instances = []
    winListeners = {}
    docListeners = {}
    vi.stubGlobal('WebSocket', FakeWebSocket)
    vi.stubGlobal('location', { protocol: 'http:', host: 'localhost:8000' })
    vi.stubGlobal('window', { dispatchEvent: vi.fn(), addEventListener: (n: string, f: () => void) => (winListeners[n] = f), removeEventListener: vi.fn() })
    vi.stubGlobal('document', {
      addEventListener: (n: string, f: () => void) => (docListeners[n] = f),
      removeEventListener: vi.fn(),
      visibilityState: 'visible',
    })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('senza messaggi per 20 s chiude e riapre', () => {
    const connection = vi.fn()
    const stop = connectWS({ ...handlers(), connection })
    FakeWebSocket.instances[0].onopen?.()
    vi.advanceTimersByTime(10_000)
    expect(FakeWebSocket.instances).toHaveLength(1)
    vi.advanceTimersByTime(15_000)
    expect(FakeWebSocket.instances).toHaveLength(2)
    expect(connection).toHaveBeenCalledWith(false)
    stop()
  })
  it('i messaggi periodici tengono viva la connessione', () => {
    const stop = connectWS(handlers())
    const ws = FakeWebSocket.instances[0]
    ws.onopen?.()
    for (let i = 0; i < 10; i++) {
      vi.advanceTimersByTime(5_000)
      ws.onmessage?.({ data: JSON.stringify({ type: 'status', mqtt: {} }) })
    }
    expect(FakeWebSocket.instances).toHaveLength(1)
    stop()
  })
  it('visibilitychange con socket fermo da oltre 20 s riapre; con socket fresco no', () => {
    const stop = connectWS(handlers())
    FakeWebSocket.instances[0].onopen?.()
    docListeners.visibilitychange?.()
    expect(FakeWebSocket.instances).toHaveLength(1)
    vi.setSystemTime(Date.now() + 30_000)
    docListeners.visibilitychange?.()
    expect(FakeWebSocket.instances).toHaveLength(2)
    stop()
  })
  it('online durante l attesa del tentativo lo anticipa', () => {
    const stop = connectWS(handlers())
    FakeWebSocket.instances[0].onclose?.({ code: 1006 })
    winListeners.online?.()
    expect(FakeWebSocket.instances).toHaveLength(2)
    stop()
  })
})
