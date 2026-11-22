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
      label: 'Radio di base collegata',
      hint: c && !c.radio_connected ? 'Collega la radio di base dalla scheda Radio.' : '',
    },
    {
      key: 'mobile',
      ok: c ? c.mobile_known : null,
      label: 'Nodo mobile sentito',
      hint: c && !c.mobile_known ? 'Accendi il nodo mobile e attendi che la base lo senta.' : '',
    },
    {
      key: 'gps',
      ok: c ? c.gps_ok : null,
      label: 'Posizione GPS recente (≤ 10 min)',
      hint: c && !c.gps_ok ? 'Serve il GPS acceso e la posizione attiva sul nodo mobile.' : '',
    },
  ]
  let precOk: boolean | null = null
  let precLabel = 'Precisione della posizione'
  let precHint = ''
  if (c) {
    if (c.precision_m !== null) {
      precOk = false
      precLabel += `: circa ± ${formatMeters(c.precision_m)}`
      precHint = 'Per una mappa precisa usa un canale privato con precisione piena.'
    } else if (c.precision_bits !== null) {
      precOk = true
      precLabel += ': esatta'
    }
  }
  items.push({ key: 'precision', ok: precOk, label: precLabel, hint: precHint })
  if (mode === 'rangetest') {
    items.push({
      key: 'rangetest',
      ok: c ? c.rangetest_age_s !== null : null,
      label: 'Pacchetti Range Test ricevuti',
      hint:
        c && c.rangetest_age_s === null
          ? 'Attiva il modulo Range Test sul nodo mobile (mittente ogni 30 s) e sulla base (ricevitore).'
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

const ROLE_NAMES: Record<string, string> = { mobile: 'Mobile', base: 'Base' }
const WORDS = {
  prepare: { part: 'preparato', notPart: 'non preparato', running: 'Preparazione in corso', done: 'Radio preparate', ok: 'Applicato', verified: 'Applicato e verificato', diff: 'Applicato, ma la configurazione riletta è diversa dal previsto', hint: ': riprova o ripristina' },
  restore: { part: 'ripristinato', notPart: 'non ripristinato', running: 'Ripristino in corso', done: 'Configurazione ripristinata', ok: 'Ripristinato', verified: 'Ripristinato e verificato', diff: 'Ripristinato, ma la configurazione riletta è diversa dal previsto', hint: '' },
}

/** Stato per nodo di un piano (mobile, poi base) dagli esiti dei lavori; il ruolo viene da `step.role`. */
export function prepareStatus(
  plan: { steps: { node_id: string; role?: string }[]; jobs: (ConfigJob | null | undefined)[] },
  kind: 'prepare' | 'restore' = 'prepare',
): PrepareStatus {
  const w = WORDS[kind]
  const nodes: NodeStatus[] = plan.steps.map((s, i) => {
    const role = (s.role && ROLE_NAMES[s.role]) || `Nodo ${i + 1}`
    const j = plan.jobs[i]
    if (!j) return { node_id: s.node_id, role, state: 'waiting', text: 'In attesa' }
    if (j.status === 'running') return { node_id: s.node_id, role, state: 'running', text: `In corso: ${j.step || 'scrittura'}` }
    if (j.status === 'failed') {
      return { node_id: s.node_id, role, state: 'failed', text: `Non riuscito: ${j.error || 'errore sconosciuto'}` }
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
      summary = `${nodes[failedAt].role} ${w.notPart}` + (later.length ? `, ${later.join(' e ')} non toccata` : '')
    } else summary = `${okNames.join(' e ')} ${w.part}, ${nodes[failedAt].role.toLowerCase()} no${w.hint}`
  } else if (running || (!allApplied && nodes.some(applied))) summary = w.running
  else if (allApplied) {
    summary = nodes.some((n) => n.state === 'mismatch') ? 'Applicato, ma controlla le differenze rilette' : w.done
  } else summary = 'In attesa'
  return { nodes, summary, finished: failed || allApplied, failed }
}
