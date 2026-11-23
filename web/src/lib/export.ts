import type { Feature, FeatureCollection, Geometry } from 'geojson'
import { coverageGeoJSON } from './coverage'
import type { CoverageDetail, Message, Node } from './types'
import { i18n, t } from './i18n/index.svelte'

export type SnrClass = 'good' | 'mid' | 'bad' | 'none'
const SNR_CLASSES: SnrClass[] = ['good', 'mid', 'bad', 'none']

type Cell = string | number | null | undefined

/** Separatore di campo e virgola decimale: italiani (; e ,) o inglesi (, e .) secondo la lingua. */
function csvFormat(): { sep: string; decimal: string } {
  return i18n.lang === 'en' ? { sep: ',', decimal: '.' } : { sep: ';', decimal: ',' }
}

function cell(v: Cell, sep: string, decimal: string): string {
  if (v === null || v === undefined) return ''
  // Italiano: virgola decimale, perche' Excel in italiano apre il file in colonne con i numeri veri
  let s = typeof v === 'number' ? (Number.isFinite(v) ? String(v).replace('.', decimal) : '') : v
  // Un testo che Excel leggerebbe come formula (nomi dei nodi dalla rete) si disinnesca con «'»
  if (typeof v === 'string' && /^[=+\-@\t\r]/.test(s)) s = `'${s}`
  return s.includes(sep) || /["\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** CSV per Excel: BOM, righe CRLF; in italiano separatore «;» e virgola decimale, in inglese «,» e punto. */
export function csv(header: string[], rows: Cell[][]): string {
  const { sep, decimal } = csvFormat()
  return '﻿' + [header, ...rows].map((r) => r.map((c) => cell(c, sep, decimal)).join(sep) + '\r\n').join('')
}

const iso = (t: number | null | undefined): string => (t === null || t === undefined || !Number.isFinite(t) ? '' : new Date(t * 1000).toISOString())

export function networkCsv(nodes: Node[]): string {
  const header = t('export.networkHeader').split(',')
  return csv(
    header,
    nodes.map((n) => [n.id, n.long_name, n.short_name, n.hw_model, n.role, n.firmware, n.country, iso(n.last_heard), n.battery, n.voltage, n.last_snr, n.hops, n.channel_util, n.air_util_tx, n.lat, n.lon, n.sources.join('+')]),
  )
}

/** Testo XML sicuro: escape dei cinque caratteri speciali e via i caratteri di controllo non ammessi. */
function xml(s: string): string {
  return s
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F￾￿]/g, '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&apos;')
}

export function gpx(name: string, pts: { time: number; lat: number; lon: number }[]): string {
  const seg = pts.map((p) => `      <trkpt lat="${p.lat.toFixed(7)}" lon="${p.lon.toFixed(7)}"><time>${iso(p.time)}</time></trkpt>`).join('\n')
  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<gpx version="1.1" creator="MeshLens" xmlns="http://www.topografix.com/GPX/1/1">\n' +
    `  <trk>\n    <name>${xml(name)}</name>\n    <trkseg>\n${seg}${seg ? '\n' : ''}    </trkseg>\n  </trk>\n</gpx>\n`
  )
}

export function coverageGeoJSONFile(detail: CoverageDetail): string {
  const g = coverageGeoJSON(detail)
  const tag = (fc: FeatureCollection<Geometry>, kind: string): Feature<Geometry>[] =>
    fc.features.map((f) => ({ ...f, properties: { ...(f.properties ?? {}), kind } }))
  const out: FeatureCollection<Geometry> = {
    type: 'FeatureCollection',
    features: [...tag(g.points, 'point'), ...tag(g.missing, 'missing'), ...tag(g.track, 'track'), ...tag(g.base, 'base')],
  }
  return JSON.stringify(out)
}

export function snrClass(snr: number | null): SnrClass {
  if (snr === null) return 'none'
  if (snr >= 0) return 'good'
  if (snr >= -10) return 'mid'
  return 'bad'
}

/** `#rrggbb` o `#rgb` → `ffbbggrr` di KML (opaco); grigio per un valore non valido. */
export function cssToKml(color: string): string {
  let c = color.trim()
  if (/^#[0-9a-f]{3}$/i.test(c)) c = '#' + [...c.slice(1)].map((x) => x + x).join('')
  const m = /^#([0-9a-f]{2})([0-9a-f]{2})([0-9a-f]{2})$/i.exec(c)
  return m ? `ff${m[3]}${m[2]}${m[1]}`.toLowerCase() : 'ff888888'
}

const withUnit = (v: number | null, unit: string) => (v === null ? '–' : `${v} ${unit}`)

export function coverageKml(detail: CoverageDetail, colors: Record<SnrClass, string>): string {
  const styles = SNR_CLASSES.map(
    (k) => `    <Style id="snr-${k}"><IconStyle><color>${cssToKml(colors[k])}</color><scale>0.8</scale></IconStyle></Style>`,
  ).join('\n')
  const marks: string[] = []
  for (const p of detail.points) {
    if (p.lat === null || p.lon === null) continue
    const desc = t('export.kmlPoint', { snr: withUnit(p.snr, 'dB'), rssi: withUnit(p.rssi, 'dBm'), hops: p.hops ?? '–', seq: p.seq ?? '–' })
    marks.push(
      `    <Placemark><name>${xml(String(p.seq ?? p.id))}</name><description>${xml(desc)}</description><styleUrl>#snr-${snrClass(p.snr)}</styleUrl>` +
        `<Point><coordinates>${p.lon},${p.lat},0</coordinates></Point></Placemark>`,
    )
  }
  const track = [...detail.track].sort((a, b) => a.time - b.time)
  if (track.length > 1) {
    marks.push(
      `    <Placemark><name>${xml(t('export.kmlTrack'))}</name><Style><LineStyle><color>ffffffff</color><width>2</width></LineStyle></Style>` +
        `<LineString><coordinates>${track.map((pt) => `${pt.lon},${pt.lat},0`).join(' ')}</coordinates></LineString></Placemark>`,
    )
  }
  if (detail.base_lat !== null && detail.base_lon !== null) {
    marks.push(`    <Placemark><name>${xml(t('export.kmlBase'))}</name><Point><coordinates>${detail.base_lon},${detail.base_lat},0</coordinates></Point></Placemark>`)
  }
  return (
    '<?xml version="1.0" encoding="UTF-8"?>\n' +
    '<kml xmlns="http://www.opengis.net/kml/2.2">\n  <Document>\n' +
    `    <name>${xml(detail.name)}</name>\n${styles}\n${marks.join('\n')}\n  </Document>\n</kml>\n`
  )
}

export function coverageCsv(detail: CoverageDetail): string {
  const rows: { time: number; row: Cell[] }[] = []
  for (const p of detail.points) {
    rows.push({ time: p.time, row: [p.seq, p.segment, iso(p.time), p.lat, p.lon, p.snr, p.rssi, p.hops, p.distance_m, t('export.received')] })
  }
  for (const m of detail.missing_points) {
    rows.push({ time: m.time, row: [m.seq, null, iso(m.time), m.lat, m.lon, null, null, null, null, t('export.missing')] })
  }
  rows.sort((a, b) => a.time - b.time)
  return csv(t('export.coverageHeader').split(','), rows.map((r) => r.row))
}

/** `AAAAMMGG` in ora locale. */
export function fileStamp(d: Date): string {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`
}

/** Parte di nome file sicura: minuscole, solo a-z 0-9 e trattini, al massimo 40 caratteri. */
export function slug(s: string): string {
  const out = s
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
    .replace(/-+$/g, '')
  return out || t('export.unnamed')
}

// ---- esportazione di una conversazione (WP1: E4) ----

export type ConvExportFormat = 'txt' | 'csv' | 'json'

/** Risposta di `GET /api/conversations/{key}/export`: i file si costruiscono qui, nel browser. */
export interface ConvExport {
  key: string
  messages: (Message & { to_name: string | null })[]
  total: number
  truncated: boolean
}

const two = (n: number) => String(n).padStart(2, '0')

/** `AAAA-MM-GG HH:MM` in ora locale. */
function localStamp(sec: number): string {
  const d = new Date(sec * 1000)
  return `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())} ${two(d.getHours())}:${two(d.getMinutes())}`
}

function senderName(m: Message): string {
  return m.direction === 'out' ? t('chat.export.you') : (m.from_name ?? m.from)
}

/** Testo semplice: intestazione e una riga per messaggio `[AAAA-MM-GG HH:MM] Mittente: testo`; le righe successive di un testo a capo sono rientrate di 2 spazi. */
export function conversationTxt(d: ConvExport, label: string, now: Date = new Date()): string {
  const head = [
    t('chat.export.title', { label }),
    t('chat.export.exportedAt', { date: localStamp(now.getTime() / 1000) }),
    t('chat.export.count', { n: d.messages.length }),
  ]
  if (d.truncated) head.push(t('chat.export.truncated', { n: d.messages.length, total: d.total }))
  const lines = d.messages.map((m) => {
    const stamp = `[${localStamp(m.time)}]`
    if (m.emoji) return `${stamp} ${t('chat.export.reaction', { name: senderName(m), emoji: m.text })}`
    const [first, ...rest] = m.text.replace(/\r\n?/g, '\n').split('\n')
    return [`${stamp} ${senderName(m)}: ${first}`, ...rest.map((r) => `  ${r}`)].join('\n')
  })
  return head.join('\n') + '\n\n' + lines.join('\n') + (lines.length ? '\n' : '')
}

/** CSV per Excel (`;` in italiano, `,` in inglese; BOM, CRLF, formule disinnescate). */
export function conversationCsv(d: ConvExport): string {
  return csv(
    t('chat.export.header').split(','),
    d.messages.map((m) => [iso(m.time), m.from, m.from_name, m.to, m.to_name, m.emoji ? '' : m.text, m.channel, m.source, m.status ?? null, m.emoji ? m.text : null]),
  )
}

/** JSON indentato; ogni messaggio ha anche `time_iso`. */
export function conversationJson(d: ConvExport, now: Date = new Date()): string {
  return JSON.stringify(
    {
      key: d.key,
      exported: now.toISOString(),
      total: d.total,
      truncated: d.truncated,
      messages: d.messages.map((m) => ({ ...m, time_iso: iso(m.time) })),
    },
    null,
    2,
  )
}

/** `messaggi-<slug>-<AAAAMMGG>.<ext>`. */
export function conversationFileName(label: string, format: ConvExportFormat, now: Date): string {
  return `messaggi-${slug(label)}-${fileStamp(now)}.${format}`
}

/** Percorso (senza `/api`) dell'esportazione; `:` e `!` della chiave sono codificati. */
export function exportPath(key: string, since?: number | null, until?: number | null): string {
  const q: string[] = []
  if (since !== null && since !== undefined) q.push(`since=${since}`)
  if (until !== null && until !== undefined) q.push(`until=${until}`)
  const enc = encodeURIComponent(key).replace(/!/g, '%21')
  return `/conversations/${enc}/export${q.length ? '?' + q.join('&') : ''}`
}

/** Colori `--snr-*` dai token CSS, per i file KML. */
export function snrColorsFromTokens(): Record<SnrClass, string> {
  const st = getComputedStyle(document.documentElement)
  const out = {} as Record<SnrClass, string>
  for (const k of SNR_CLASSES) out[k] = st.getPropertyValue(`--snr-${k}`).trim()
  return out
}
