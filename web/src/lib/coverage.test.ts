import { describe, expect, it } from 'vitest'
import { checklist, coverageGeoJSON, formatLoss, upsertPoint, validInterval } from './coverage'
import type { CoverageCheck, CoverageDetail, CoveragePoint } from './types'

const good: CoverageCheck = {
  radio_connected: true,
  radio_channels: [],
  mobile_known: true,
  position_age_s: 20,
  precision_bits: 32,
  precision_m: null,
  gps_ok: true,
  rangetest_age_s: 15,
  base_position: null,
}

describe('checklist', () => {
  it('senza controlli tutti i passi hanno ok null', () => {
    const l = checklist(null, 'rangetest')
    expect(l.length).toBe(5)
    expect(l.every((s) => s.ok === null)).toBe(true)
  })
  it('gps_ok false segna il passo GPS', () => {
    const l = checklist({ ...good, gps_ok: false, position_age_s: 900 }, 'rangetest')
    expect(l.find((s) => s.key === 'gps')?.ok).toBe(false)
  })
  it('precisione approssimata: ok false e raggio in km', () => {
    const l = checklist({ ...good, precision_bits: 13, precision_m: 2900 }, 'rangetest')
    const p = l.find((s) => s.key === 'precision')!
    expect(p.ok).toBe(false)
    expect(p.label + p.hint).toContain('2,9 km')
  })
  it('posizione esatta: tutto ok', () => {
    expect(checklist(good, 'rangetest').every((s) => s.ok === true)).toBe(true)
  })
  it('in modalita position non c\'e il passo Range Test', () => {
    const l = checklist(good, 'position')
    expect(l.some((s) => s.key === 'rangetest')).toBe(false)
  })
  it('range test mai ricevuto: ok false', () => {
    const l = checklist({ ...good, rangetest_age_s: null }, 'rangetest')
    expect(l.find((s) => s.key === 'rangetest')?.ok).toBe(false)
  })
})

describe('formatLoss', () => {
  it('null -> trattino', () => {
    expect(formatLoss(null)).toBe('—')
  })
  it('valore con virgola', () => {
    expect(formatLoss(6.67)).toBe('6,7%')
  })
})

describe('validInterval', () => {
  it('accetta 10-600 interi', () => {
    expect(validInterval(10)).toBe(true)
    expect(validInterval(600)).toBe(true)
    expect(validInterval(9)).toBe(false)
    expect(validInterval(601)).toBe(false)
    expect(validInterval(30.5)).toBe(false)
    expect(validInterval(null)).toBe(false)
  })
})


const detail = (over: Partial<CoverageDetail> = {}): CoverageDetail =>
  ({
    id: 1,
    base_lat: 45,
    base_lon: 9,
    points: [],
    missing_points: [],
    track: [],
    ...over,
  }) as unknown as CoverageDetail

const pt = (o: object) => ({ id: 1, segment: 0, seq: 0, time: 1, snr: 1, rssi: -90, hops: 0, lat: 45, lon: 9, precision_bits: 32, distance_m: 10, ...o })

describe('coverageGeoJSON', () => {
  it('salta i punti con lat null', () => {
    const g = coverageGeoJSON(detail({ points: [pt({ lat: null }), pt({ seq: 1 })] }))
    expect(g.points.features.length).toBe(1)
  })
  it('percorso ordinato per tempo', () => {
    const g = coverageGeoJSON(
      detail({
        track: [
          { time: 30, lat: 3, lon: 3, precision_bits: 32 },
          { time: 10, lat: 1, lon: 1, precision_bits: 32 },
          { time: 20, lat: 2, lon: 2, precision_bits: 32 },
        ],
      }),
    )
    expect(g.track.features[0].geometry.coordinates).toEqual([
      [1, 1],
      [2, 2],
      [3, 3],
    ])
  })
  it('colore SNR -12 rosso', () => {
    const g = coverageGeoJSON(detail({ points: [pt({ snr: -12 })] }))
    expect(g.points.features[0].properties?.color).toBe('#c8382e')
  })
  it('base assente se base_lat null', () => {
    expect(coverageGeoJSON(detail({ base_lat: null })).base.features.length).toBe(0)
    expect(coverageGeoJSON(detail()).base.features.length).toBe(1)
  })
  it('punti mancanti senza coordinate saltati', () => {
    const g = coverageGeoJSON(
      detail({ missing_points: [{ seq: 1, time: 1, lat: null, lon: null }, { seq: 2, time: 2, lat: 1, lon: 2 }] }),
    )
    expect(g.missing.features.length).toBe(1)
  })
})

describe('upsertPoint', () => {
  const p = (o: Partial<CoveragePoint>) => pt(o) as CoveragePoint
  it('aggiunge un punto nuovo', () => {
    const a = [p({ id: 1, seq: 0 })]
    const out = upsertPoint(a, p({ id: 2, seq: 1 }))
    expect(out.length).toBe(2)
  })
  it('sostituisce per id', () => {
    const a = [p({ id: 1, seq: 0, lat: null }), p({ id: 2, seq: 1 })]
    const out = upsertPoint(a, p({ id: 1, seq: 0, lat: 5 }))
    expect(out.length).toBe(2)
    expect(out[0].lat).toBe(5)
  })
  it('ripiego: stesso tratto e seq', () => {
    const a = [p({ id: 1, segment: 0, seq: 3 })]
    expect(upsertPoint(a, p({ id: 9, segment: 0, seq: 3 })).length).toBe(1)
    expect(upsertPoint(a, p({ id: 9, segment: 1, seq: 3 })).length).toBe(2)
  })
  it('non modifica la lista di partenza', () => {
    const a = [p({ id: 1, lat: null })]
    upsertPoint(a, p({ id: 1, lat: 5 }))
    expect(a[0].lat).toBeNull()
  })
})
