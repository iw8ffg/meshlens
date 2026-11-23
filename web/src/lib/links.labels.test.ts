import { describe, expect, it } from 'vitest'
import { linkLabel, linksToGeoJSON } from './links'
import type { Link, Node } from './types'

const f = (v: number) => `${v < 0 ? '−' : ''}${Math.abs(v).toString().replace('.', ',')} dB`
const node = (id: string, lat: number): Node => ({ id, lat, lon: 9 }) as unknown as Node
const nodes = new Map([['!a', node('!a', 45)], ['!b', node('!b', 46)]])
const link = (o: Partial<Link>): Link => ({ from_id: '!a', to_id: '!b', source: 'neighborinfo', snr: -7.5, time: 100, ...o })

describe('linkLabel', () => {
  it('SNR e diretto', () => {
    expect(linkLabel(-7.5, 'neighborinfo', f, 'diretto')).toBe('−7,5 dB')
    expect(linkLabel(-7.5, 'rf_direct', f, 'diretto')).toBe('−7,5 dB · diretto')
    expect(linkLabel(null, 'rf_direct', f, 'diretto')).toBe('diretto')
    expect(linkLabel(null, 'traceroute', f, 'diretto')).toBe('')
  })
})

describe('linksToGeoJSON con etichette', () => {
  it('senza il quarto parametro non c\'e\' label', () => {
    const g = linksToGeoJSON([link({})], nodes, 10)
    expect(g.features[0].properties).not.toHaveProperty('label')
  })
  it('con il quarto parametro ogni feature ha label; fusione con SNR migliore e sorgente piu\' recente', () => {
    const g = linksToGeoJSON(
      [link({ snr: -9, source: 'neighborinfo', time: 100 }), link({ from_id: '!b', to_id: '!a', snr: -3, source: 'rf_direct', time: 200 })],
      nodes,
      300,
      (snr, source) => linkLabel(snr, source, f, 'diretto'),
    )
    expect(g.features).toHaveLength(1)
    expect(g.features[0].properties!.label).toBe('−3 dB · diretto')
    const none = linksToGeoJSON([link({ snr: null, source: 'traceroute' })], nodes, 10, (s, src) => linkLabel(s, src, f, 'diretto'))
    expect(none.features[0].properties!.label).toBe('')
  })
})
