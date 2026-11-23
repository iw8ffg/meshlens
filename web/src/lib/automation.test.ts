import { afterEach, describe, expect, it, vi } from 'vitest'

const calls: string[] = []
vi.mock('./api', () => ({
  getJSON: vi.fn(async (path: string) => {
    calls.push(path)
    if (path === '/trace-targets') return { enabled: true, max_per_hour: 4, targets: [{ node_id: '!00000001' }] }
    if (path === '/bot') return { status: { enabled: false, queued: 0, sent_last_hour: 0, paused_until: null, last_error: null }, commands: [] }
    throw new Error(path)
  }),
  send: vi.fn(),
}))

import { automation, startAutomation } from './automation.svelte'
import { dispatchExt, notifyWsResync } from './wsext'

const flush = () => new Promise((r) => setTimeout(r, 0))

afterEach(() => {
  calls.length = 0
})

describe('startAutomation', () => {
  it('carica, segue gli eventi e si pulisce', async () => {
    const stop = startAutomation()
    await flush()
    expect(calls).toEqual(['/trace-targets', '/bot'])
    expect(automation.loaded).toBe(true)
    expect(automation.autoEnabled).toBe(true)
    expect(automation.maxPerHour).toBe(4)
    expect(automation.targets.length).toBe(1)

    expect(dispatchExt({ type: 'trace_targets', targets: [] })).toBe(true)
    expect(automation.targets).toEqual([])
    dispatchExt({ type: 'bot', status: { enabled: true, queued: 2, sent_last_hour: 1, paused_until: null, last_error: 'busy' } })
    expect(automation.bot?.queued).toBe(2)
    expect(automation.bot?.last_error).toBe('busy')

    calls.length = 0
    notifyWsResync()
    await flush()
    expect(calls).toEqual(['/trace-targets', '/bot'])

    stop()
    expect(dispatchExt({ type: 'trace_targets', targets: [] })).toBe(false)
    expect(dispatchExt({ type: 'bot', status: {} })).toBe(false)
    calls.length = 0
    notifyWsResync()
    await flush()
    expect(calls).toEqual([])
  })
})
