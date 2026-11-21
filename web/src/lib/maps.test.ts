import { describe, expect, it } from 'vitest'
import { bboxFromBounds, formatBytes, jobPercent } from './maps'
import type { MapJob } from './types'

const job = (over: Partial<MapJob>): MapJob => ({
  id: 1,
  kind: 'italy',
  name: 'Italia',
  status: 'running',
  step: 'Scarico',
  bytes_done: 0,
  bytes_total: null,
  error: null,
  started: 0,
  ended: null,
  ...over,
})

describe('formatBytes', () => {
  it('formatta in unita decimali con la virgola', () => {
    expect(formatBytes(2_000_000_000)).toBe('2,0 GB')
    expect(formatBytes(200_000_000)).toBe('200,0 MB')
    expect(formatBytes(1500)).toBe('2 KB')
    expect(formatBytes(512)).toBe('512 B')
    expect(formatBytes(0)).toBe('0 B')
  })
  it('valori non validi', () => {
    expect(formatBytes(-5)).toBe('0 B')
    expect(formatBytes(NaN)).toBe('0 B')
  })
})

describe('jobPercent', () => {
  it('bytes_total nullo: nessuna percentuale', () => {
    expect(jobPercent(job({ bytes_done: 10, bytes_total: null }))).toBeNull()
    expect(jobPercent(job({ bytes_total: 0 }))).toBeNull()
  })
  it('percentuale arrotondata e limitata a 0..100', () => {
    expect(jobPercent(job({ bytes_done: 1, bytes_total: 3 }))).toBe(33)
    expect(jobPercent(job({ bytes_done: 5, bytes_total: 4 }))).toBe(100)
    expect(jobPercent(job({ bytes_done: -1, bytes_total: 4 }))).toBe(0)
  })
})

describe('bboxFromBounds', () => {
  it('arrotonda a 4 decimali (oggetto LngLatBounds)', () => {
    const b = { getWest: () => 6.123456, getSouth: () => 36.99999, getEast: () => 18.00004, getNorth: () => 47.5 }
    expect(bboxFromBounds(b)).toEqual([6.1235, 37, 18, 47.5])
  })
  it('accetta anche un array', () => {
    expect(bboxFromBounds([1.23456, 2.34567, 3.45678, 4.56789])).toEqual([1.2346, 2.3457, 3.4568, 4.5679])
  })
  it('limita longitudine a ±180 e latitudine a ±85', () => {
    expect(bboxFromBounds([-200, -89.9, 250, 90])).toEqual([-180, -85, 180, 85])
  })
})
