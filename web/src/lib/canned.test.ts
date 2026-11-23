import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ getJSON: vi.fn(async () => ({})), send: vi.fn(async () => ({})) }))

import { getJSON, send } from './api'
import { CANNED_MAX_BYTES, cannedBytes, cannedError, getCanned, putCanned, quickToCanned } from './canned'

beforeEach(() => vi.clearAllMocks())

describe('canned', () => {
  it('byte UTF-8 con i separatori', () => {
    expect(CANNED_MAX_BYTES).toBe(200)
    expect(cannedBytes(['è', 'a'])).toBe(4)
    expect(cannedBytes([])).toBe(0)
  })

  it('stesse regole di join_canned', () => {
    expect(cannedError([])).toBe('canned.err.empty')
    expect(cannedError(['a|b'])).toBe('canned.err.pipe')
    expect(cannedError([''])).toBe('canned.err.blank')
    expect(cannedError(['  '])).toBe('canned.err.blank')
    expect(cannedError(['a\u0007'])).toBe('canned.err.control')
    expect(cannedError(['a'.repeat(199), 'b'])).toBe('canned.err.tooLong')
    expect(cannedError([' a '.repeat(1) + 'x'.repeat(197)])).toBeNull()
    expect(cannedError(['a'.repeat(200)])).toBeNull()
  })

  it('chiamate HTTP', async () => {
    await getCanned('!00000042')
    expect(getJSON).toHaveBeenCalledWith('/config/!00000042/canned')
    await getCanned('!00000042', 'r1')
    expect(getJSON).toHaveBeenLastCalledWith('/config/!00000042/canned?radio_id=r1')
    await putCanned('!00000042', ['A', 'B'])
    expect(send).toHaveBeenCalledWith('PUT', '/config/!00000042/canned', { messages: ['A', 'B'], radio_id: null })
  })
})

describe('quickToCanned', () => {
  it('scarta pipe e variabili, rispetta il limite', () => {
    const r = quickToCanned(['Ok', 'a|b', 'Batteria {batteria}', 'Sono qui {posizione}', 'Ciao'])
    expect(r.out).toEqual(['Ok', 'Ciao'])
    expect(r.skippedVars).toBe(2)
    expect(r.skippedPipe).toBe(1)
    expect(r.truncated).toBe(false)
  })
  it('tronca oltre i 200 byte', () => {
    const r = quickToCanned(['a'.repeat(150), 'b'.repeat(100), 'c'])
    expect(r.out).toEqual(['a'.repeat(150)])
    expect(r.truncated).toBe(true)
  })
})
