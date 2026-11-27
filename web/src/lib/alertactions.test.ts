import { afterEach, describe, expect, it, vi } from 'vitest'
import { withoutAlert, withoutKeyChanged } from './alerts'
import { acceptNewKey, dismiss, restoreHidden } from './alertactions'
import { app, setAlerts } from './stores.svelte'
import type { Alert } from './types'

const al = (key: string, kind: Alert['kind'], node_id = '!00000001'): Alert => ({ key, kind, node_id, node_name: 'N', value: 1, since: 1 })
const LIST = [al('battery:!00000001', 'battery_low'), al('pki:!00000001', 'key_changed'), al('pki:!00000002', 'key_changed', '!00000002')]

type Call = [string, RequestInit | undefined]
function mockFetch(reply: (url: string) => unknown) {
  const fn = vi.fn(async (url: string, _init?: RequestInit) => new Response(JSON.stringify(reply(url)), { status: 200 }))
  vi.stubGlobal('fetch', fn)
  return fn
}

afterEach(() => {
  vi.unstubAllGlobals()
  setAlerts([], 0)
})

describe('helper puri', () => {
  it('withoutAlert toglie solo la chiave', () => {
    expect(withoutAlert(LIST, 'battery:!00000001').map((a) => a.key)).toEqual(['pki:!00000001', 'pki:!00000002'])
  })
  it('withoutKeyChanged toglie solo la chiave cambiata di quel nodo', () => {
    expect(withoutKeyChanged(LIST, '!00000001').map((a) => a.key)).toEqual(['battery:!00000001', 'pki:!00000002'])
  })
})

describe('setAlerts', () => {
  it('aggiorna il conteggio dei nascosti solo se arriva', () => {
    setAlerts(LIST, 2)
    expect(app.alertsHidden).toBe(2)
    setAlerts([], undefined)
    expect(app.alertsHidden).toBe(2)
  })
})

describe('azioni', () => {
  it('dismiss: POST con la chiave codificata e avviso tolto subito', async () => {
    const fn = mockFetch(() => ({ hidden: 1 }))
    setAlerts(LIST, 0)
    await dismiss('battery:!00000001')
    const [url, init] = fn.mock.calls[0] as unknown as Call
    expect(url).toBe('/api/alerts/battery%3A!00000001/dismiss')
    expect(init?.method).toBe('POST')
    expect(app.alerts.map((a) => a.key)).not.toContain('battery:!00000001')
    expect(app.alertsHidden).toBe(1)
  })
  it('restoreHidden: POST e ricarica gli avvisi', async () => {
    const fn = mockFetch((url) => (url.endsWith('/restore') ? { hidden: 0 } : LIST))
    setAlerts([], 3)
    await restoreHidden()
    expect((fn.mock.calls[0] as unknown as Call)[0]).toBe('/api/alerts/dismissed/restore')
    expect(app.alerts).toHaveLength(3)
    expect(app.alertsHidden).toBe(0)
  })
  it('acceptNewKey: POST sul nodo e avviso di chiave tolto', async () => {
    const fn = mockFetch(() => ({ id: '!00000001', num: 1, key_changed: null }))
    setAlerts(LIST, 0)
    await acceptNewKey('!00000001')
    expect((fn.mock.calls[0] as unknown as Call)[0]).toBe('/api/nodes/!00000001/accept-key')
    expect(app.alerts.map((a) => a.key)).toEqual(['battery:!00000001', 'pki:!00000002'])
  })
})
