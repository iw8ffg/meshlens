import { describe, expect, it } from 'vitest'
import { loadNotifyPrefs, notifySupported, saveNotifyPrefs, shouldNotify, titleFor } from './notify'
import type { Message } from './types'

const m = { key: 'k', from: '!b', from_name: null, to: '!a', channel: '0', text: 'x', time: 1, country: null, source: 'rf' } as Message
const on = { dm: true }

describe('titleFor', () => {
  it('tre casi', () => {
    expect(titleFor('MeshLens', 0)).toBe('MeshLens')
    expect(titleFor('MeshLens', 3)).toBe('(3) MeshLens')
    expect(titleFor('MeshLens', 120)).toBe('(99+) MeshLens')
  })
})

describe('shouldNotify', () => {
  it('vero solo per DM, concesso, nascosto, non reazione', () => {
    expect(shouldNotify(m, 'dm:r1:!b', on, 'granted', true)).toBe(true)
    expect(shouldNotify(m, 'ch:r1:0', on, 'granted', true)).toBe(false)
    expect(shouldNotify({ ...m, emoji: true }, 'dm:r1:!b', on, 'granted', true)).toBe(false)
    expect(shouldNotify(m, 'dm:r1:!b', on, 'denied', true)).toBe(false)
    expect(shouldNotify(m, 'dm:r1:!b', on, 'granted', false)).toBe(false)
    expect(shouldNotify(m, 'dm:r1:!b', { dm: false }, 'granted', true)).toBe(false)
  })
})

describe('preferenze', () => {
  it('JSON rotto o assente: dm falso', () => {
    expect(loadNotifyPrefs({ getItem: () => '{rotto' })).toEqual({ dm: false })
    expect(loadNotifyPrefs({ getItem: () => null })).toEqual({ dm: false })
  })
  it('salva e rilegge', () => {
    const store: Record<string, string> = {}
    saveNotifyPrefs({ setItem: (k, v) => (store[k] = v) }, { dm: true })
    expect(loadNotifyPrefs({ getItem: (k) => store[k] ?? null })).toEqual({ dm: true })
  })
})

describe('notifySupported', () => {
  it('richiede contesto sicuro e Notification', () => {
    expect(notifySupported({ isSecureContext: false, Notification: function () {} })).toBe(false)
    expect(notifySupported({ isSecureContext: true, Notification: function () {} })).toBe(true)
    expect(notifySupported({ isSecureContext: true })).toBe(false)
  })
})
