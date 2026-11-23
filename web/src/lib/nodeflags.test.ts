import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ getJSON: vi.fn(async () => ({})), send: vi.fn(async () => ({})) }))

import { getJSON, send } from './api'
import { getIgnoredNodes, getRadioFlags, ignoredNodes, setIgnored, setRadioFlags } from './nodes'
import type { Node } from './types'

beforeEach(() => vi.clearAllMocks())

const node = (id: string, name: string | null, ignored?: boolean) =>
  ({ id, num: parseInt(id.slice(1), 16), long_name: name, short_name: null, is_ignored: ignored }) as unknown as Node

describe('flag dei nodi (WP4)', () => {
  it('ignoredNodes filtra e ordina per nome', () => {
    const list = [node('!00000003', 'zeta', true), node('!00000001', 'Alfa'), node('!00000002', 'beta', true), node('!00000004', null, true)]
    // senza nome vale l'id ("!..." viene prima delle lettere)
    expect(ignoredNodes(list).map((n) => n.id)).toEqual(['!00000004', '!00000002', '!00000003'])
  })

  it('chiamate HTTP', async () => {
    await setIgnored('!00000042', true)
    expect(send).toHaveBeenLastCalledWith('PUT', '/nodes/!00000042/ignored', { ignored: true, radio: true })
    await setIgnored('!00000042', false, false)
    expect(send).toHaveBeenLastCalledWith('PUT', '/nodes/!00000042/ignored', { ignored: false, radio: false })
    await getRadioFlags('!00000042')
    expect(getJSON).toHaveBeenLastCalledWith('/nodes/!00000042/radio-flags')
    await setRadioFlags('!00000042', { favorite: true })
    expect(send).toHaveBeenLastCalledWith('PUT', '/nodes/!00000042/radio-flags', { favorite: true, radio_id: null })
    await setRadioFlags('!00000042', { ignored: false }, 'r1')
    expect(send).toHaveBeenLastCalledWith('PUT', '/nodes/!00000042/radio-flags', { ignored: false, radio_id: 'r1' })
    await getIgnoredNodes()
    expect(getJSON).toHaveBeenLastCalledWith('/nodes/ignored')
  })
})
