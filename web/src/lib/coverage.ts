import type { Feature, FeatureCollection, LineString, Point } from 'geojson'
import { formatMeters } from './geo'
import { snrColor } from './links'
import type {
  ConfigJob,
  CoverageCheck,
  CoverageDetail,
  CoverageMode,
  CoveragePoint,
  CoverageSession,
  CoverageTrackPoint,
} from './types'
import { decSep } from './format'
import { t } from './i18n/index.svelte'
import { translateServer } from './i18n/server'

export interface ChecklistItem {
  key: 'radio' | 'mobile' | 'gps' | 'precision' | 'rangetest'
  ok: boolean | null
  label: string
  hint: string
}

/** Passi guidati della preparazione, con stato: true ok, false problema, null non ancora noto. */
export function checklist(check: CoverageCheck | null, mode: CoverageMode): ChecklistItem[] {
  const c = check
  const items: ChecklistItem[] = [
    {
      key: 'radio',
      ok: c ? c.radio_connected : null,
      label: t('coverage.check.radio.label'),
      hint: c && !c.radio_connected ? t('coverage.check.radio.hint') : '',
    },
    {
      key: 'mobile',
      ok: c ? c.mobile_known : null,
      label: t('coverage.check.mobile.label'),
      hint: c && !c.mobile_known ? t('coverage.check.mobile.hint') : '',
    },
    {
      key: 'gps',
      ok: c ? c.gps_ok : null,
      label: t('coverage.check.gps.label'),
      hint: c && !c.gps_ok ? t('coverage.check.gps.hint') : '',
    },
  ]
  let precOk: boolean | null = null
  let precLabel = t('coverage.check.precision.label')
  let precHint = ''
  if (c) {
    if (c.precision_m !== null) {
      precOk = false
      precLabel = t('coverage.check.precision.approx', { m: formatMeters(c.precision_m) })
      precHint = t('coverage.check.precision.hint')
    } else if (c.precision_bits !== null) {
      precOk = true
      precLabel = t('coverage.check.precision.exact')
    }
  }
  items.push({ key: 'precision', ok: precOk, label: precLabel, hint: precHint })
  if (mode === 'rangetest') {
    items.push({
      key: 'rangetest',
      ok: c ? c.rangetest_age_s !== null : null,
      label: t('coverage.check.rangetest.label'),
      hint:
        c && c.rangetest_age_s === null
          ? t('coverage.check.rangetest.hint')
          : '',
    })
  }
  return items
}

/** Intervallo ammesso dal server: intero tra 10 e 600 secondi. */
export function validInterval(n: unknown): n is number {
  return typeof n === 'number' && Number.isInteger(n) && n >= 10 && n <= 600
}

/** Perdita pacchetti in percentuale ("6,7%"), "—" se non disponibile. */
export function formatLoss(s: CoverageSession | number | null): string {
  const v = s !== null && typeof s === 'object' ? s.loss_pct : s
  if (v === null || v === undefined || !Number.isFinite(v)) return '—'
  return `${decSep(v.toFixed(1))}%`
}

export interface CoverageGeo {
  points: FeatureCollection<Point>
  missing: FeatureCollection<Point>
  track: FeatureCollection<LineString>
  base: FeatureCollection<Point>
}

/** Dati GeoJSON del dettaglio di una prova: punti senza coordinate saltati, percorso ordinato per tempo. */
export function coverageGeoJSON(detail: CoverageDetail): CoverageGeo {
  const points: Feature<Point>[] = []
  for (const p of detail.points) {
    if (p.lat === null || p.lon === null) continue
    points.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
      properties: { color: snrColor(p.snr), snr: p.snr, rssi: p.rssi, seq: p.seq, time: p.time, hops: p.hops, distance_m: p.distance_m },
    })
  }
  const missing: Feature<Point>[] = []
  for (const m of detail.missing_points) {
    if (m.lat === null || m.lon === null) continue
    missing.push({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [m.lon, m.lat] },
      properties: { seq: m.seq, time: m.time },
    })
  }
  const sorted = [...detail.track].sort((a, b) => a.time - b.time)
  const track: Feature<LineString>[] =
    sorted.length > 1
      ? [{ type: 'Feature', geometry: { type: 'LineString', coordinates: sorted.map((t) => [t.lon, t.lat]) }, properties: {} }]
      : []
  const base: Feature<Point>[] =
    detail.base_lat !== null && detail.base_lon !== null
      ? [{ type: 'Feature', geometry: { type: 'Point', coordinates: [detail.base_lon, detail.base_lat] }, properties: {} }]
      : []
  const fc = <G extends Point | LineString>(features: Feature<G>[]): FeatureCollection<G> => ({ type: 'FeatureCollection', features })
  return { points: fc(points), missing: fc(missing), track: fc(track), base: fc(base) }
}

/** Nuovo percorso con la posizione aggiunta (ordinato per tempo); invariato se gia' presente. */
export function appendTrackPoint(track: CoverageTrackPoint[], t: CoverageTrackPoint): CoverageTrackPoint[] {
  if (track.some((x) => x.time === t.time && x.lat === t.lat && x.lon === t.lon)) return track
  return [...track, t].sort((a, b) => a.time - b.time)
}

/** Nuova lista con il punto aggiunto o, se già presente (stesso id, o stesso tratto e seq), sostituito. */
export function upsertPoint(points: CoveragePoint[], p: CoveragePoint): CoveragePoint[] {
  let i = points.findIndex((x) => x.id === p.id)
  if (i < 0 && p.seq !== null) i = points.findIndex((x) => x.segment === p.segment && x.seq === p.seq)
  if (i < 0) return [...points, p]
  const out = [...points]
  out[i] = p
  return out
}

export type NodeState = 'waiting' | 'running' | 'ok' | 'mismatch' | 'failed'
export interface NodeStatus {
  node_id: string
  role: string
  state: NodeState
  text: string
}
export interface PrepareStatus {
  nodes: NodeStatus[]
  summary: string
  /** tutti i lavori sono terminati (o uno e' fallito e gli altri non partiranno) */
  finished: boolean
  failed: boolean
}

const roleName = (role: string | undefined): string | null =>
  role === 'mobile' ? t('coverage.role.mobile') : role === 'base' ? t('coverage.role.base') : null
/** Parole del piano nella lingua corrente (si leggono a ogni chiamata, quindi seguono il cambio lingua). */
function words(kind: 'prepare' | 'restore') {
  return kind === 'prepare'
    ? { part: t('coverage.prep.part'), notPart: t('coverage.prep.notPart'), running: t('coverage.prep.running'), done: t('coverage.prep.done'), ok: t('coverage.prep.ok'), verified: t('coverage.prep.verified'), diff: t('coverage.prep.diff'), hint: t('coverage.prep.hint') }
    : { part: t('coverage.rest.part'), notPart: t('coverage.rest.notPart'), running: t('coverage.rest.running'), done: t('coverage.rest.done'), ok: t('coverage.rest.ok'), verified: t('coverage.rest.verified'), diff: t('coverage.rest.diff'), hint: '' }
}

/** Stato per nodo di un piano (mobile, poi base) dagli esiti dei lavori; il ruolo viene da `step.role`. */
export function prepareStatus(
  plan: { steps: { node_id: string; role?: string }[]; jobs: (ConfigJob | null | undefined)[] },
  kind: 'prepare' | 'restore' = 'prepare',
): PrepareStatus {
  const w = words(kind)
  const and = ` ${t('coverage.and')} `
  const nodes: NodeStatus[] = plan.steps.map((s, i) => {
    const role = roleName(s.role) ?? t('coverage.role.node', { n: i + 1 })
    const j = plan.jobs[i]
    if (!j) return { node_id: s.node_id, role, state: 'waiting', text: t('coverage.state.waiting') }
    if (j.status === 'running') return { node_id: s.node_id, role, state: 'running', text: t('coverage.state.running', { step: j.step ? translateServer(j.step) : t('coverage.state.writing') }) }
    if (j.status === 'failed') {
      return { node_id: s.node_id, role, state: 'failed', text: t('coverage.state.failed', { error: j.error ? translateServer(j.error) : t('coverage.state.unknownError') }) }
    }
    if (j.verify === 'mismatch') return { node_id: s.node_id, role, state: 'mismatch', text: w.diff }
    return { node_id: s.node_id, role, state: 'ok', text: j.verify === 'verified' ? w.verified : w.ok }
  })
  const applied = (n: NodeStatus) => n.state === 'ok' || n.state === 'mismatch'
  const failedAt = nodes.findIndex((n) => n.state === 'failed')
  const failed = failedAt >= 0
  const running = nodes.some((n) => n.state === 'running')
  const allApplied = nodes.length > 0 && nodes.every(applied)
  let summary: string
  if (failed) {
    const okNames = nodes.filter(applied).map((n) => n.role)
    const later = nodes.slice(failedAt + 1).map((n) => n.role.toLowerCase())
    if (okNames.length === 0) {
      summary = `${nodes[failedAt].role} ${w.notPart}` + (later.length ? t('coverage.sum.untouched', { later: later.join(and) }) : '')
    } else summary = `${okNames.join(and)} ${w.part}, ${nodes[failedAt].role.toLowerCase()} ${t('coverage.sum.partialNo')}${w.hint}`
  } else if (running || (!allApplied && nodes.some(applied))) summary = w.running
  else if (allApplied) {
    summary = nodes.some((n) => n.state === 'mismatch') ? t('coverage.sum.mismatch') : w.done
  } else summary = t('coverage.state.waiting')
  return { nodes, summary, finished: failed || allApplied, failed }
}
