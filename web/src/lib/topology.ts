// Logica del grafo di topologia (E8): richiesta al server, classi dei nodi, viste derivate e
// geometria (layout a forze deterministico, pan e zoom puri). Nessun accesso al DOM.
//
// Layout: Fruchterman-Reingold su un'area width x height (predefinita 1000 x 700).
//  1. PRNG mulberry32 col seme = FNV-1a a 32 bit degli id ordinati uniti da `|`; ordine di
//     elaborazione = id ordinati, quindi il risultato non dipende dall'ordine dell'input.
//  2. Posizione iniziale: nodo i di n su un cerchio di raggio 0,35*min(w,h) all'angolo
//     2*pi*i/n + jitter (+-0,1 rad dal PRNG).
//  3. k = 0,9*sqrt(w*h/n); a ogni iterazione repulsione k^2/d tra tutte le coppie, attrazione
//     d^2/k lungo gli archi, gravita' verso il centro 0,02*d; spostamento limitato alla
//     temperatura T = (w/10)*(1 - it/iterazioni); coordinate confinate nel riquadro con margine 24.
//  4. Iterazioni: n <= 150 -> 300, n <= 400 -> 180, altrimenti 120; n = 0 -> vuoto, n = 1 -> centro;
//     coppie coincidenti (d < 1e-6) si separano con una spinta casuale (mai NaN).
import { getJSON } from './api'
import type { Link, TopologyEdge, TopologyNode, TopologyResult } from './types'
export { snrClass } from './ui/logic'
export type { SnrClass } from './ui/logic'

export const topologyData = (p: { hours: number; sources: Link['source'][]; countries: string[]; limit?: number }) => {
  const q = [`hours=${p.hours}`, `sources=${p.sources.join(',')}`]
  if (p.countries.length > 0) q.push(`countries=${p.countries.join(',')}`)
  if (p.limit !== undefined) q.push(`limit=${p.limit}`)
  return getJSON<TopologyResult>(`/topology?${q.join('&')}`)
}

/** Periodi scelti nella vista (ore): 24 h, 7 giorni (predefinito), 30 giorni. */
export const PERIODS = [24, 168, 720] as const
export const DEFAULT_PERIOD = 168

export type NodeClass = 'cut' | 'hub' | 'normal'
/** La cerniera ha la precedenza sull'hub. */
export const nodeClass = (n: Pick<TopologyNode, 'cut' | 'hub'>): NodeClass => (n.cut ? 'cut' : n.hub ? 'hub' : 'normal')

export interface Pt {
  x: number
  y: number
}

const fnv1a = (s: string): number => {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

const mulberry32 = (seed: number): (() => number) => {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

export function layout(
  nodes: Pick<TopologyNode, 'id' | 'degree'>[],
  edges: Pick<TopologyEdge, 'a' | 'b'>[],
  opts: { width?: number; height?: number; seed?: number; iterations?: number } = {},
): Map<string, Pt> {
  const W = opts.width ?? 1000
  const H = opts.height ?? 700
  const PAD = 24
  const ids = [...new Set(nodes.map((n) => n.id))].sort()
  const n = ids.length
  const out = new Map<string, Pt>()
  if (n === 0) return out
  if (n === 1) {
    out.set(ids[0], { x: W / 2, y: H / 2 })
    return out
  }
  const rnd = mulberry32(opts.seed ?? fnv1a(ids.join('|')))
  const index = new Map(ids.map((id, i) => [id, i]))
  const pairs = new Set<number>()
  for (const e of edges) {
    const i = index.get(e.a)
    const j = index.get(e.b)
    if (i === undefined || j === undefined || i === j) continue
    pairs.add(i < j ? i * n + j : j * n + i)
  }
  const es = [...pairs].sort((a, b) => a - b).map((p) => [Math.floor(p / n), p % n] as const)

  const x = new Float64Array(n)
  const y = new Float64Array(n)
  const r0 = 0.35 * Math.min(W, H)
  for (let i = 0; i < n; i++) {
    const ang = (2 * Math.PI * i) / n + (rnd() - 0.5) * 0.2
    x[i] = W / 2 + r0 * Math.cos(ang)
    y[i] = H / 2 + r0 * Math.sin(ang)
  }
  const iterations = opts.iterations ?? (n <= 150 ? 300 : n <= 400 ? 180 : 120)
  const k = 0.9 * Math.sqrt((W * H) / n)
  const k2 = k * k
  const dx = new Float64Array(n)
  const dy = new Float64Array(n)
  for (let it = 0; it < iterations; it++) {
    dx.fill(0)
    dy.fill(0)
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let vx = x[i] - x[j]
        let vy = y[i] - y[j]
        let d = Math.hypot(vx, vy)
        if (d < 1e-6) {
          vx = rnd() - 0.5 || 0.001
          vy = rnd() - 0.5 || 0.001
          d = Math.hypot(vx, vy)
        }
        const f = k2 / d / d
        dx[i] += vx * f
        dy[i] += vy * f
        dx[j] -= vx * f
        dy[j] -= vy * f
      }
    }
    for (const [i, j] of es) {
      const vx = x[i] - x[j]
      const vy = y[i] - y[j]
      const d = Math.hypot(vx, vy)
      if (d < 1e-6) continue
      const f = d / k // d^2/k diviso d per normalizzare il vettore
      dx[i] -= vx * f
      dy[i] -= vy * f
      dx[j] += vx * f
      dy[j] += vy * f
    }
    const temp = (W / 10) * (1 - it / iterations)
    for (let i = 0; i < n; i++) {
      dx[i] -= 0.02 * (x[i] - W / 2)
      dy[i] -= 0.02 * (y[i] - H / 2)
      const len = Math.hypot(dx[i], dy[i])
      if (len > 1e-9) {
        const lim = Math.min(len, temp)
        x[i] += (dx[i] / len) * lim
        y[i] += (dy[i] / len) * lim
      }
      x[i] = Math.min(W - PAD, Math.max(PAD, x[i]))
      y[i] = Math.min(H - PAD, Math.max(PAD, y[i]))
    }
  }
  for (let i = 0; i < n; i++) out.set(ids[i], { x: x[i], y: y[i] })
  return out
}

export interface ViewBox {
  x: number
  y: number
  w: number
  h: number
}

const DEFAULT_VB: ViewBox = { x: 0, y: 0, w: 1000, h: 700 }

/** ViewBox che contiene i punti con margine `pad`, adattato al rapporto `aspect` (larghezza/altezza). */
export function fitViewBox(points: Pt[], pad = 40, aspect = 1000 / 700): ViewBox {
  if (points.length === 0) return { ...DEFAULT_VB }
  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  for (const p of points) {
    x0 = Math.min(x0, p.x)
    y0 = Math.min(y0, p.y)
    x1 = Math.max(x1, p.x)
    y1 = Math.max(y1, p.y)
  }
  let w = Math.max(x1 - x0 + 2 * pad, 1)
  let h = Math.max(y1 - y0 + 2 * pad, 1)
  const cx = (x0 + x1) / 2
  const cy = (y0 + y1) / 2
  if (w / h < aspect) w = h * aspect
  else h = w / aspect
  return { x: cx - w / 2, y: cy - h / 2, w, h }
}

/** Zoom di `factor` attorno a (cx, cy), che resta fermo; `min`/`max` limitano la larghezza risultante. */
export function zoomAt(vb: ViewBox, factor: number, cx: number, cy: number, min = 50, max = 6000): ViewBox {
  const w = Math.min(max, Math.max(min, vb.w / factor))
  const s = w / vb.w
  return { x: cx - (cx - vb.x) * s, y: cy - (cy - vb.y) * s, w, h: vb.h * s }
}

export const panBy = (vb: ViewBox, dx: number, dy: number): ViewBox => ({ ...vb, x: vb.x + dx, y: vb.y + dy })

/** Vicini di `id` (entrambi i versi), ordinati. */
export function neighborsOf(edges: TopologyEdge[], id: string): string[] {
  const out = new Set<string>()
  for (const e of edges) {
    if (e.a === id) out.add(e.b)
    else if (e.b === id) out.add(e.a)
  }
  return [...out].sort()
}

/** Nodi cerniera: impatto decrescente, poi nome. */
export const listCuts = (r: TopologyResult): TopologyNode[] =>
  r.nodes.filter((n) => n.cut).sort((a, b) => b.impact - a.impact || a.name.localeCompare(b.name))

/** Hub che non sono cerniere: grado decrescente, poi nome. */
export const listHubs = (r: TopologyResult): TopologyNode[] =>
  r.nodes.filter((n) => n.hub && !n.cut).sort((a, b) => b.degree - a.degree || a.name.localeCompare(b.name))

/** Nessun dato Neighbor Info nel periodo: la vista propone di abilitarlo. */
export const needsNeighborInfoHelp = (r: TopologyResult): boolean => r.stats.by_source.neighborinfo === 0
