import { describe, expect, it } from 'vitest'
import { INFRA_ROLES, isInfrastructure, loadFilter, matchNode } from './filters'
import type { Node } from './types'

const node = (role: string | null): Node =>
  ({ id: '!a', num: 1, role, country: 'IT', last_heard: 1000, sources: ['rf'], is_ignored: false }) as unknown as Node

describe('isInfrastructure', () => {
  it('ruoli router e ripetitori', () => {
    for (const r of ['ROUTER', 'ROUTER_LATE', 'REPEATER', 'ROUTER_CLIENT', 'router']) expect(isInfrastructure({ role: r })).toBe(true)
    for (const r of ['CLIENT', 'CLIENT_BASE', 'TRACKER', 'TAK', null]) expect(isInfrastructure({ role: r })).toBe(false)
    expect([...INFRA_ROLES]).toEqual(['ROUTER', 'ROUTER_CLIENT', 'ROUTER_LATE', 'REPEATER'])
  })
  it('il filtro predefinito non cambia', () => {
    const f = loadFilter({ getItem: () => null, setItem: () => {} })
    expect(matchNode(node('REPEATER'), f, 1100)).toBe(true)
    expect(matchNode(node('CLIENT'), f, 1100)).toBe(true)
  })
})
