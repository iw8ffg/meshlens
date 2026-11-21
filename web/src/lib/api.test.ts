import { afterEach, describe, expect, it, vi } from 'vitest'
import { applyPlan, previewRestore, revealPsk, restorePlan } from './api'

function mockFetch() {
  const fn = vi.fn(async () => new Response('{}', { status: 200 }))
  vi.stubGlobal('fetch', fn)
  return fn
}
const init = (fn: ReturnType<typeof mockFetch>) => (fn.mock.calls[0] as unknown as [string, RequestInit])[1]

afterEach(() => vi.unstubAllGlobals())

describe('POST senza dati: il server esige JSON (415 altrimenti)', () => {
  it('previewRestore invia {} con Content-Type JSON', async () => {
    const fn = mockFetch()
    await previewRestore(3)
    expect(init(fn).body).toBe('{}')
    expect(init(fn).headers).toEqual({ 'Content-Type': 'application/json' })
  })
  it('revealPsk invia {} con Content-Type JSON', async () => {
    const fn = mockFetch()
    await revealPsk('!aabbccdd', 1)
    expect(init(fn).body).toBe('{}')
    expect(init(fn).headers).toEqual({ 'Content-Type': 'application/json' })
  })
  it('applyPlan e restorePlan usano il numero del piano', async () => {
    const fn = mockFetch()
    await applyPlan(7, true)
    expect((fn.mock.calls[0] as unknown as [string])[0]).toBe('/api/coverage/prepare/7/apply')
    await restorePlan(7)
    expect(JSON.parse(String((fn.mock.calls[1] as unknown as [string, RequestInit])[1].body))).toEqual({ plan_id: 7 })
  })
})
