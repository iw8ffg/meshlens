import { describe, expect, it } from 'vitest'
import { canInstall, updateLabel } from './update'
import type { UpdateJob, UpdateStatus } from './types'

const status = (over: Partial<UpdateStatus> = {}): UpdateStatus => ({
  current: '1.0.0',
  latest: '1.0.0',
  available: false,
  notes: null,
  published_at: null,
  checked_at: 1,
  error: null,
  job: null,
  can_install: true,
  ...over,
})
const job = (over: Partial<UpdateJob> = {}): UpdateJob => ({ id: 1, status: 'done', bytes_done: 10, bytes_total: 10, error: null, ...over })

describe('updateLabel', () => {
  it('mai controllato', () => {
    expect(updateLabel(null)).toBe('Non ancora controllato')
    expect(updateLabel(status({ latest: null, checked_at: null }))).toBe('Non ancora controllato')
  })
  it('aggiornamento disponibile', () => {
    expect(updateLabel(status({ available: true, latest: '1.2.0' }))).toBe('Disponibile MeshLens 1.2.0')
  })
  it('gia aggiornato', () => {
    expect(updateLabel(status())).toBe('MeshLens è aggiornato')
  })
  it('errore ha la precedenza', () => {
    expect(updateLabel(status({ error: 'Nessuna connessione', available: true, latest: '2.0.0' }))).toBe('Nessuna connessione')
  })
})

describe('canInstall', () => {
  const avail = status({ available: true, latest: '1.2.0' })
  it('serve download completato', () => {
    expect(canInstall(avail, job())).toBe(true)
    expect(canInstall(avail, job({ status: 'running' }))).toBe(false)
    expect(canInstall(avail, job({ status: 'failed' }))).toBe(false)
    expect(canInstall(avail, null)).toBe(false)
  })
  it('non in sviluppo', () => {
    expect(canInstall(status({ available: true, can_install: false }), job())).toBe(false)
  })
  it('serve aggiornamento disponibile', () => {
    expect(canInstall(status(), job())).toBe(false)
    expect(canInstall(null, job())).toBe(false)
  })
})
