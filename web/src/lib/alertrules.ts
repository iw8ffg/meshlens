// Avvisi su misura (E6): bozze del modulo, validazione (stessi limiti del server), geometria delle
// zone e chiamate HTTP. Nessun testo letterale: tutto passa da t()/tn().
import { getJSON, send } from './api'
import { circlePolygon } from './geo'
import { t, tn, type MsgKey } from './i18n/index.svelte'
import type { AlertRule, AlertRuleBody, AlertRuleKind } from './types'
import type { IconName } from './ui/icons'

export const RULE_KINDS: AlertRuleKind[] = ['keyword', 'snr_low', 'battery', 'silent', 'geofence', 'detection']

export const RULE_LIMITS = {
  cooldown: [1, 1440] as [number, number],
  snr: [-30, 20] as [number, number],
  battery: [1, 99] as [number, number],
  silentH: [0.25, 168] as [number, number],
  windowMin: [15, 1440] as [number, number],
  samples: [1, 50] as [number, number],
  words: 10,
  wordLen: [2, 32] as [number, number],
  vertices: [3, 64] as [number, number],
  matchMax: 32,
  nameMax: 60,
}

export type Trigger = 'exit' | 'enter' | 'both'
export type Polygon = [number, number][]

export type RuleDraft = {
  id: number | null
  kind: AlertRuleKind
  name: string
  enabled: boolean
  nodeId: string | null
  channel: string | null
  threshold: string
  wordsText: string
  wholeWord: boolean
  windowMin: string
  minSamples: string
  trigger: Trigger
  match: string
  polygon: Polygon
  cooldownMin: string
}

export function emptyDraft(kind: AlertRuleKind): RuleDraft {
  return {
    id: null,
    kind,
    name: '',
    enabled: true,
    nodeId: null,
    channel: null,
    threshold: '',
    wordsText: '',
    wholeWord: false,
    windowMin: '60',
    minSamples: '3',
    trigger: 'exit',
    match: '',
    polygon: [],
    cooldownMin: '60',
  }
}

/** Numero con virgola o punto decimale; null se vuoto o non valido. */
export function parseNumber(s: string): number | null {
  const x = s.trim().replace(',', '.')
  if (x === '' || !/^[-+]?(\d+\.?\d*|\.\d+)$/.test(x)) return null
  const n = Number(x)
  return Number.isFinite(n) ? n : null
}

const parseInteger = (s: string): number | null => {
  const n = parseNumber(s)
  return n !== null && Number.isInteger(n) ? n : null
}

/** Parole separate da virgola, punto e virgola o a capo; senza doppioni (maiuscole e accenti non contano). */
export function parseWords(text: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of text.split(/[,;\n]/)) {
    const w = raw.trim()
    if (w === '') continue
    const k = w.normalize('NFKD').replace(/\p{M}/gu, '').toLowerCase()
    if (seen.has(k)) continue
    seen.add(k)
    out.push(w)
  }
  return out
}

export function draftFromRule(r: AlertRule): RuleDraft {
  const d = emptyDraft(r.kind)
  const p = r.params as Record<string, unknown>
  d.id = r.id
  d.name = r.name
  d.enabled = r.enabled
  d.nodeId = r.node_id
  d.channel = r.channel
  d.threshold = r.threshold === null ? '' : String(r.threshold)
  d.cooldownMin = String(r.cooldown_min)
  if (r.kind === 'keyword') {
    d.wordsText = Array.isArray(p.words) ? (p.words as string[]).join(', ') : ''
    d.wholeWord = p.whole_word === true
  } else if (r.kind === 'snr_low') {
    d.windowMin = String(p.window_min ?? 60)
    d.minSamples = String(p.min_samples ?? 3)
  } else if (r.kind === 'geofence') {
    d.trigger = (p.trigger as Trigger) ?? 'exit'
    d.polygon = Array.isArray(p.polygon) ? (p.polygon as Polygon).map(([a, b]) => [a, b] as [number, number]) : []
  } else if (r.kind === 'detection') {
    d.match = typeof p.match === 'string' ? p.match : ''
  }
  return d
}

const THRESHOLD_KINDS: AlertRuleKind[] = ['snr_low', 'battery', 'silent']
const NODE_REQUIRED: AlertRuleKind[] = ['snr_low', 'geofence', 'battery', 'silent']

export function draftToBody(d: RuleDraft): AlertRuleBody {
  let params: Record<string, unknown> = {}
  if (d.kind === 'keyword') params = { words: parseWords(d.wordsText), whole_word: d.wholeWord }
  else if (d.kind === 'snr_low') params = { window_min: parseNumber(d.windowMin), min_samples: parseNumber(d.minSamples) }
  else if (d.kind === 'geofence') params = { trigger: d.trigger, polygon: closeOpen(d.polygon) }
  else if (d.kind === 'detection') params = { match: d.match.trim() }
  return {
    kind: d.kind,
    name: d.name.trim(),
    enabled: d.enabled,
    node_id: d.nodeId,
    channel: d.kind === 'keyword' ? d.channel : null,
    threshold: THRESHOLD_KINDS.includes(d.kind) ? parseNumber(d.threshold) : null,
    params,
    cooldown_min: parseNumber(d.cooldownMin) ?? 0,
  }
}

type ErrKey = 'name' | 'node' | 'threshold' | 'words' | 'window' | 'samples' | 'polygon' | 'cooldown' | 'match'

export function draftErrors(d: RuleDraft): Partial<Record<ErrKey, MsgKey>> {
  const e: Partial<Record<ErrKey, MsgKey>> = {}
  const inRange = (n: number | null, [lo, hi]: [number, number]) => n !== null && n >= lo && n <= hi
  if (d.name.trim().length > RULE_LIMITS.nameMax) e.name = 'alertrules.err.name'
  const cooldown = parseInteger(d.cooldownMin)
  if (!inRange(cooldown, RULE_LIMITS.cooldown)) e.cooldown = 'alertrules.err.cooldown'
  if (NODE_REQUIRED.includes(d.kind) && !d.nodeId) e.node = 'alertrules.err.node'
  if (d.kind === 'snr_low' && !inRange(parseNumber(d.threshold), RULE_LIMITS.snr)) e.threshold = 'alertrules.err.threshold'
  if (d.kind === 'battery' && !inRange(parseInteger(d.threshold), RULE_LIMITS.battery)) e.threshold = 'alertrules.err.threshold'
  if (d.kind === 'silent' && !inRange(parseNumber(d.threshold), RULE_LIMITS.silentH)) e.threshold = 'alertrules.err.threshold'
  if (d.kind === 'keyword') {
    const words = parseWords(d.wordsText)
    const [lo, hi] = RULE_LIMITS.wordLen
    if (words.length < 1 || words.length > RULE_LIMITS.words || words.some((w) => w.length < lo || w.length > hi)) {
      e.words = 'alertrules.err.words'
    }
  }
  if (d.kind === 'snr_low') {
    if (!inRange(parseInteger(d.windowMin), RULE_LIMITS.windowMin)) e.window = 'alertrules.err.window'
    if (!inRange(parseInteger(d.minSamples), RULE_LIMITS.samples)) e.samples = 'alertrules.err.samples'
  }
  if (d.kind === 'geofence' && polygonIssue(d.polygon) !== null) e.polygon = 'alertrules.err.polygon'
  if (d.kind === 'detection' && d.match.trim().length > RULE_LIMITS.matchMax) e.match = 'alertrules.err.match'
  return e
}

export function ruleIcon(kind: AlertRuleKind): IconName {
  switch (kind) {
    case 'keyword':
      return 'chat'
    case 'snr_low':
      return 'bars'
    case 'geofence':
      return 'pin'
    case 'battery':
      return 'battery'
    case 'silent':
      return 'clock'
    case 'detection':
      return 'eye'
  }
}

/** Una riga che descrive la regola, nella lingua corrente. */
export function ruleSummary(r: AlertRule, nodeName: (id: string) => string): string {
  const who = r.node_id ? nodeName(r.node_id) : t('alertrules.field.anyNode')
  const p = r.params as Record<string, unknown>
  const thr = r.threshold ?? ''
  switch (r.kind) {
    case 'keyword':
      return t('alertrules.summary.keyword', { words: Array.isArray(p.words) ? (p.words as string[]).join(', ') : '', who })
    case 'snr_low':
      return t('alertrules.summary.snr', { thr, who })
    case 'geofence': {
      const trig = p.trigger === 'enter' ? 'Enter' : p.trigger === 'both' ? 'Both' : 'Exit'
      return t('alertrules.summary.geofence', { trigger: t(`alertrules.field.trigger${trig}` as MsgKey), who })
    }
    case 'battery':
      return t('alertrules.summary.battery', { thr, who })
    case 'silent':
      return t('alertrules.summary.silent', { thr, who })
    case 'detection': {
      const match = typeof p.match === 'string' ? p.match : ''
      return match ? t('alertrules.summary.detection', { match, who }) : t('alertrules.summary.detectionAny', { who })
    }
  }
}

/** Canali scelti per una regola parola chiave: 8 per radio ('ch:<radio>:<i>') e uno per canale MQTT. */
export function channelOptions(
  radios: { id: string; name?: string | null }[],
  mqttChannels: string[],
): { value: string; label: string }[] {
  const out: { value: string; label: string }[] = []
  for (const r of radios) {
    for (let i = 0; i < 8; i++) {
      out.push({ value: `ch:${r.id}:${i}`, label: `${r.name || r.id} · ${t('alertrules.field.channelIndex', { n: i })}` })
    }
  }
  for (const c of mqttChannels) out.push({ value: `mqtt:${c}`, label: `MQTT · ${c}` })
  return out
}

// ---- geometria delle zone: coppie [lon, lat] ----

/** Toglie il punto di chiusura, se uguale al primo. */
function openRing(p: Polygon): Polygon {
  return p.length > 1 && p[0][0] === p[p.length - 1][0] && p[0][1] === p[p.length - 1][1] ? p.slice(0, -1) : p
}
const closeOpen = (p: Polygon): Polygon => openRing(p).map(([a, b]) => [a, b] as [number, number])

const cross = (o: [number, number], a: [number, number], b: [number, number]) =>
  (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
const onSeg = (p: [number, number], a: [number, number], b: [number, number]) =>
  Math.min(a[0], b[0]) <= p[0] && p[0] <= Math.max(a[0], b[0]) && Math.min(a[1], b[1]) <= p[1] && p[1] <= Math.max(a[1], b[1])

function segmentsCross(a: [number, number], b: [number, number], c: [number, number], d: [number, number]): boolean {
  const o1 = cross(a, b, c)
  const o2 = cross(a, b, d)
  const o3 = cross(c, d, a)
  const o4 = cross(c, d, b)
  if (((o1 > 0 && o2 < 0) || (o1 < 0 && o2 > 0)) && ((o3 > 0 && o4 < 0) || (o3 < 0 && o4 > 0))) return true
  return (o1 === 0 && onSeg(c, a, b)) || (o2 === 0 && onSeg(d, a, b)) || (o3 === 0 && onSeg(a, c, d)) || (o4 === 0 && onSeg(b, c, d))
}

/** Punto nel poligono (ray casting piano su [lon, lat]); il bordo conta come dentro. */
export function pointInPolygon(lon: number, lat: number, polygon: Polygon): boolean {
  const n = polygon.length
  const pt: [number, number] = [lon, lat]
  for (let i = 0; i < n; i++) {
    const a = polygon[i]
    const b = polygon[(i + 1) % n]
    if (cross(a, b, pt) === 0 && onSeg(pt, a, b)) return true
  }
  let inside = false
  for (let i = 0; i < n; i++) {
    const a = polygon[i]
    const b = polygon[(i + 1) % n]
    if (a[1] > lat !== b[1] > lat && lon < a[0] + ((lat - a[1]) * (b[0] - a[0])) / (b[1] - a[1])) inside = !inside
  }
  return inside
}

export function polygonBounds(p: Polygon): [number, number, number, number] | null {
  if (p.length === 0) return null
  const lons = p.map((x) => x[0])
  const lats = p.map((x) => x[1])
  return [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)]
}

/** Anello chiuso per MapLibre (non modifica l'ingresso). */
export function polygonToGeoJSON(p: Polygon): GeoJSON.Feature<GeoJSON.Polygon> {
  const ring = openRing(p).map(([a, b]) => [a, b])
  if (ring.length > 0) ring.push([...ring[0]])
  return { type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }
}

export function addVertex(p: Polygon, lon: number, lat: number): Polygon {
  if (p.length >= RULE_LIMITS.vertices[1]) return p
  return [...p, [lon, lat]]
}

export function undoVertex(p: Polygon): Polygon {
  return p.slice(0, -1)
}

/** Cerchio come poligono a 32 lati, senza punto di chiusura duplicato. */
export function circleZone(lat: number, lon: number, radiusM: number): Polygon {
  return circlePolygon(lat, lon, radiusM, 32).slice(0, -1)
}

/** Problema della zona (stessi criteri del server), o null se valida. */
export function polygonIssue(polygon: Polygon): 'few' | 'many' | 'range' | 'cross' | 'area' | null {
  const p = openRing(polygon)
  if (p.some(([lon, lat]) => !Number.isFinite(lon) || !Number.isFinite(lat) || Math.abs(lon) > 180 || Math.abs(lat) > 90)) return 'range'
  if (p.length < RULE_LIMITS.vertices[0]) return 'few'
  if (p.length > RULE_LIMITS.vertices[1]) return 'many'
  const n = p.length
  const lons = p.map((x) => x[0])
  if (Math.max(...lons) - Math.min(...lons) > 180) return 'area'
  if (p.some((x, i) => x[0] === p[(i + 1) % n][0] && x[1] === p[(i + 1) % n][1])) return 'area'
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (j === i + 1 || (i === 0 && j === n - 1)) continue
      if (segmentsCross(p[i], p[(i + 1) % n], p[j], p[(j + 1) % n])) return 'cross'
    }
  }
  let area = 0
  for (let i = 0; i < n; i++) {
    const a = p[i]
    const b = p[(i + 1) % n]
    area += a[0] * b[1] - b[0] * a[1]
  }
  return Math.abs(area / 2) < 1e-12 ? 'area' : null
}

/** Punti della zona nella lingua corrente ("3 punti"). */
export const zonePoints = (n: number): string => tn('alertrules.zone.points', n)

// ---- API ----
export const listRules = () => getJSON<AlertRule[]>('/alert-rules')
export const createRule = (b: AlertRuleBody) => send<AlertRule>('POST', '/alert-rules', b)
export const patchRule = (id: number, b: Partial<AlertRuleBody>) => send<AlertRule>('PATCH', `/alert-rules/${id}`, b)
export const deleteRule = (id: number) => send<{ ok: true }>('DELETE', `/alert-rules/${id}`, { confirm: true })
