import { describe, expect, it } from 'vitest'
import { coverageCsv, coverageGeoJSONFile, coverageKml, cssToKml, csv, fileStamp, gpx, networkCsv, slug, snrClass } from './export'
import type { CoverageDetail, Node } from './types'

// Ambiente node, senza DOMParser: controllo minimo di buona formazione (tag bilanciati, nessun & non protetto)
function wellFormed(out: string): boolean {
  const body = out.replace(/^<\?xml[^>]*\?>\s*/, '')
  if (/&(?!(amp|lt|gt|quot|apos);)/.test(body.replace(/<[^>]*>/g, ''))) return false
  if (/<[^>]*[<&](?!(amp|lt|gt|quot|apos);)/.test(body.replace(/&(amp|lt|gt|quot|apos);/g, ''))) return false
  const stack: string[] = []
  for (const m of body.matchAll(/<(\/?)([A-Za-z][\w:-]*)[^>]*?(\/?)>/g)) {
    if (m[3]) continue
    if (m[1]) {
      if (stack.pop() !== m[2]) return false
    } else stack.push(m[2])
  }
  return stack.length === 0 && body.replace(/<[^>]*>/g, '').indexOf('<') < 0
}

const colors = { good: '#2e9d4b', mid: '#d9a400', bad: '#c8382e', none: '#8a8a8a' }

function detail(over: Partial<CoverageDetail> = {}): CoverageDetail {
  return {
    id: 7, name: 'Prova 🚀 A & <B>', radio_id: 'r', mobile_id: '!m', mode: 'rangetest', channel_index: 0, interval_s: 30,
    started: 1000, ended: 2000, end_reason: 'manual', base_lat: 45.1, base_lon: 7.2, notes: '', received: 2, expected: 4,
    missing: 1, loss_pct: 25, best_snr: 5, worst_snr: -12, max_distance_m: 900, approx_precision_m: null,
    points: [
      { id: 1, segment: 0, seq: 1, time: 1100, snr: 5, rssi: -80, hops: 0, lat: 45.11, lon: 7.21, precision_bits: 32, distance_m: 100 },
      { id: 2, segment: 0, seq: 3, time: 1300, snr: -12, rssi: -110, hops: 1, lat: 45.13, lon: 7.23, precision_bits: 32, distance_m: 900 },
      { id: 3, segment: 0, seq: 4, time: 1400, snr: null, rssi: null, hops: null, lat: null, lon: null, precision_bits: null, distance_m: null },
    ],
    missing_points: [{ seq: 2, time: 1200, lat: 45.12, lon: 7.22 }],
    track: [
      { time: 1300, lat: 45.13, lon: 7.23, precision_bits: 32 },
      { time: 1100, lat: 45.11, lon: 7.21, precision_bits: 32 },
    ],
    ...over,
  }
}

describe('csv: formule', () => {
  it('prefissa con apice i testi che iniziano come formule, non i numeri', () => {
    const out = csv(['n'], [['=HYPERLINK("x")'], ['+1'], ['-2+3'], ['@SUM(A1)'], ['\tx'], ['\rx'], ['ok'], [-5]])
    const lines = out.split('\r\n')
    expect(lines).toContain(`"'=HYPERLINK(""x"")"`)
    expect(lines).toContain("'+1")
    expect(lines).toContain("'-2+3")
    expect(lines).toContain("'@SUM(A1)")
    expect(lines).toContain("'\tx")
    expect(out).toContain('"\'\rx"')
    expect(lines).toContain('ok')
    expect(lines).toContain('-5')
  })
})

describe('csv', () => {
  it('BOM, separatore ;, virgola decimale, CRLF', () => {
    expect(csv(['a', 'b'], [['x;y', 'di "lui"'], [1.5, null]])).toBe('﻿a;b\r\n"x;y";"di ""lui"""\r\n1,5;\r\n')
  })
  it('un a capo nel nome resta tra virgolette', () => {
    expect(csv(['n'], [['a\nb']])).toBe('﻿n\r\n"a\nb"\r\n')
  })
  it('numeri non finiti diventano vuoti', () => {
    expect(csv(['n'], [[NaN]])).toBe('﻿n\r\n\r\n')
  })
})

describe('networkCsv', () => {
  it('ISO UTC, fonti unite da + e intestazione', () => {
    const n = { id: '!a', long_name: 'A', last_heard: 0, sources: ['rf', 'mqtt'], lat: 45.5, lon: 7.25, battery: null } as unknown as Node
    const out = networkCsv([n])
    expect(out).toContain('1970-01-01T00:00:00.000Z')
    expect(out).toContain('rf+mqtt')
    expect(out).toContain('45,5;7,25;')
    expect(out.split('\r\n')[0]).toBe('﻿id;nome;nome_breve;modello;ruolo;firmware;nazione;ultimo_contatto;batteria;tensione;snr;salti;uso_canale;tx_aria;lat;lon;fonti')
  })
})

describe('gpx', () => {
  const pts = [{ time: 0, lat: 45.1, lon: 7.2 }, { time: 60, lat: 45.2, lon: 7.3 }]
  it('escape del nome, ordine e XML valido', () => {
    const out = gpx('A & <B> "x" \'y\'', pts)
    expect(out).toContain('<name>A &amp; &lt;B&gt; &quot;x&quot; &apos;y&apos;</name>')
    expect(out).toContain('creator="MeshLens"')
    expect(out).toContain('lat="45.1000000" lon="7.2000000"><time>1970-01-01T00:00:00.000Z</time>')
    expect(out.indexOf('45.1000000')).toBeLessThan(out.indexOf('45.2000000'))
    expect(wellFormed(out)).toBe(true)
    expect(out.match(/<trkpt /g)).toHaveLength(2)
  })
})

describe('coverage', () => {
  it('GeoJSON unico con kind', () => {
    const fc = JSON.parse(coverageGeoJSONFile(detail()))
    expect(fc.type).toBe('FeatureCollection')
    const kinds = fc.features.map((f: { properties: { kind: string } }) => f.properties.kind)
    expect(kinds.filter((k: string) => k === 'point')).toHaveLength(2)
    expect(kinds).toEqual(expect.arrayContaining(['missing', 'track', 'base']))
  })
  it('KML valido con nome con emoji e &', () => {
    const out = coverageKml(detail(), colors)
    expect(wellFormed(out)).toBe(true)
    expect(out).toContain('<name>Prova 🚀 A &amp; &lt;B&gt;</name>')
    expect(out).toContain('<Style id="snr-good">')
    expect(out).toContain('<color>ff4b9d2e</color>')
    const pts = out.split('<Placemark>').filter((m) => m.includes('<description>'))
    expect(pts).toHaveLength(2)
    expect(pts[1]).toContain('<styleUrl>#snr-bad</styleUrl>')
    expect(pts[1]).toContain('<description>SNR -12 dB, RSSI -110 dBm, salti 1, seq 3</description>')
    expect(out.match(/<LineString>/g)).toHaveLength(1)
  })
  it('CSV in ordine di tempo con stato', () => {
    const lines = coverageCsv(detail()).split('\r\n')
    expect(lines[0]).toBe('﻿seq;segmento;ora;lat;lon;snr;rssi;salti;distanza_m;stato')
    expect(lines.slice(1, 5).map((l) => l.split(';')[0])).toEqual(['1', '2', '3', '4'])
    expect(lines[1].endsWith(';ricevuto')).toBe(true)
    expect(lines[2].endsWith(';mancante')).toBe(true)
  })
})

describe('utilità', () => {
  it('snrClass', () => {
    expect([snrClass(3), snrClass(0), snrClass(-5), snrClass(-10), snrClass(-12), snrClass(null)]).toEqual(['good', 'good', 'mid', 'mid', 'bad', 'none'])
  })
  it('cssToKml', () => {
    expect(cssToKml('#2e9d4b')).toBe('ff4b9d2e')
    expect(cssToKml('#abc')).toBe('ffccbbaa')
    expect(cssToKml('rosso')).toBe('ff888888')
  })
  it('slug e fileStamp', () => {
    expect(slug('Prova #1: Monte Bianco!')).toBe('prova-1-monte-bianco')
    expect(slug('')).toBe('senza-nome')
    expect(slug('🚀')).toBe('senza-nome')
    expect(slug('x'.repeat(80)).length).toBe(40)
    expect(fileStamp(new Date(2026, 10, 21))).toBe('20261121')
  })
})
