import { test, expect } from 'vitest'
import { mergeHistory, shouldStore } from './traceroute'
import type { Traceroute } from './types'

const tr = (o: Partial<Traceroute>): Traceroute => ({
  id: 1, radio_id: 'r', target_id: '!00000042', time: 1, status: 'pending', error: null, forward: [], back: [], ...o,
})

test('un pending non declassa un esito finale con lo stesso id', () => {
  expect(shouldStore(tr({ status: 'ok' }), tr({ status: 'pending' }))).toBe(false)
  expect(shouldStore(tr({ status: 'timeout' }), tr({ status: 'pending' }))).toBe(false)
  expect(shouldStore(tr({ status: 'pending' }), tr({ status: 'ok' }))).toBe(true)
  expect(shouldStore(tr({ status: 'ok' }), tr({ id: 2, status: 'pending' }))).toBe(true)
  expect(shouldStore(undefined, tr({}))).toBe(true)
})

test('mergeHistory sostituisce per id o antepone', () => {
  const old = tr({ status: 'pending' })
  const done = tr({ status: 'ok' })
  expect(mergeHistory([old], done)).toEqual([done])
  expect(mergeHistory([old], tr({ id: 2 }))[0].id).toBe(2)
})

test('mergeHistory restituisce lo stesso array se la voce è già uguale (niente cicli negli effetti)', () => {
  const list = [tr({ status: 'ok' })]
  expect(mergeHistory(list, tr({ status: 'ok' }))).toBe(list)
  expect(mergeHistory(list, tr({ status: 'failed', error: 'x' }))).not.toBe(list)
})
