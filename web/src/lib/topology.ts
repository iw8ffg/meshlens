// Logica del grafo di topologia (E8): richiesta al server, classi dei nodi, viste derivate e
// geometria (layout a forze deterministico, pan e zoom puri). Nessun accesso al DOM.
//
// Layout (1.6.1): spazio illimitato, nessun bordo.
//  1. PRNG mulberry32 col seme = FNV-1a a 32 bit degli id ordinati uniti da `|`; ordine di
//     elaborazione = id ordinati, quindi il risultato non dipende dall'ordine dell'input.
//  2. Ogni componente connessa si dispone da sola (Fruchterman-Reingold con lunghezza ideale L = 60):
//     partenza a spirale in ordine di visita in ampiezza dal nodo di grado maggiore, repulsione
//     k^2/d calcolata con un albero quadtree Barnes-Hut (theta = 0,9; esatta fino a 64 nodi), attrazione
//     d^2/k lungo gli archi, gravita' debole verso il centro della componente, spostamento limitato
//     dalla temperatura (raffreddamento quadratico). Iterazioni: <= 30 nodi 120, <= 150 250, <= 400 200, oltre 150.
//  3. Impacchettamento: la componente maggiore a sinistra, le altre per dimensione decrescente in colonne
//     ordinate a destra (altezza della colonna = max(altezza della principale, ~ radice dell'area restante)).
//  4. Con posizioni di partenza (`seeds`) i nodi noti partono da li' e basta un assestamento breve.
//  La vista poi calcola il viewBox con `fitViewBox` sui punti ottenuti.
import { getJSON } from './api'
import type { Link, TopologyEdge, TopologyNode, TopologyResult } from './types'
export { snrClass } from './ui/logic'
export type { SnrClass } from './ui/logic'

export const topologyData = (p: { hours: number; sources: Link['source'][]; countries: string[]; limit?: number; main?: boolean }) => {
  const q = [`hours=${p.hours}`, `sources=${p.sources.join(',')}`]
  if (p.countries.length > 0) q.push(`countries=${p.countries.join(',')}`)
  if (p.limit !== undefined) q.push(`limit=${p.limit}`)
  if (p.main) q.push('main=1')
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

export interface LayoutOpts {
  /** Solo per il punto di un nodo singolo (centro width x height); il layout non ha confini. */
  width?: number
  height?: number
  seed?: number
  iterations?: number
  /** Posizioni precedenti: i nodi noti partono da li' (layout stabile tra un refresh e l'altro). */
  seeds?: ReadonlyMap<string, Pt>
}

export interface LayoutJob {
  /** Esegue al massimo `n` iterazioni; true se il layout e' completo. */
  step(n: number): boolean
  readonly done: boolean
  result(): Map<string, Pt>
}

/** Lunghezza ideale di un arco, in unita' del grafo. */
const EDGE_LEN = 60
const THETA2 = 0.9 * 0.9
const EXACT_MAX = 64
const MAX_DEPTH = 28

const iterationsFor = (m: number): number => (m <= 30 ? 120 : m <= 150 ? 250 : m <= 400 ? 200 : 150)

/** Stato di layout di una componente connessa, in coordinate locali. */
class CompLayout {
  readonly m: number
  readonly x: Float64Array
  readonly y: Float64Array
  private readonly dx: Float64Array
  private readonly dy: Float64Array
  private readonly ea: Int32Array
  private readonly eb: Int32Array
  readonly iterations: number
  private readonly tScale: number
  private readonly temp0: number
  private readonly rnd: () => number
  private it = 0
  // quadtree Barnes-Hut (array paralleli, azzerati a ogni iterazione)
  private tMass: number[] = []
  private tSx: number[] = []
  private tSy: number[] = []
  private tBx: number[] = []
  private tBy: number[] = []
  private tSize: number[] = []
  private tBody: number[] = []
  private tCh: number[] = []
  private stack: number[] = []

  constructor(
    m: number,
    localEdges: [number, number][],
    deg: Int32Array,
    adj: number[][],
    initial: (Pt | undefined)[],
    rnd: () => number,
    forced?: number,
  ) {
    this.m = m
    this.rnd = rnd
    this.x = new Float64Array(m)
    this.y = new Float64Array(m)
    this.dx = new Float64Array(m)
    this.dy = new Float64Array(m)
    this.ea = Int32Array.from(localEdges.map((e) => e[0]))
    this.eb = Int32Array.from(localEdges.map((e) => e[1]))
    // visita in ampiezza dal nodo di grado maggiore: i vicini finiscono vicini sulla spirale
    let root = 0
    for (let i = 1; i < m; i++) if (deg[i] > deg[root]) root = i
    const order: number[] = []
    const seen = new Uint8Array(m)
    seen[root] = 1
    order.push(root)
    for (let h = 0; h < order.length; h++) for (const v of adj[order[h]]) if (!seen[v]) ((seen[v] = 1), order.push(v))
    for (let i = 0; i < m; i++) if (!seen[i]) order.push(i) // non dovrebbe capitare (componente connessa)
    // centro dei nodi con posizione di partenza
    let sx = 0
    let sy = 0
    let seeded = 0
    for (let i = 0; i < m; i++) {
      const p = initial[i]
      if (p) (sx += p.x, sy += p.y, seeded++)
    }
    const ox = seeded ? sx / seeded : 0
    const oy = seeded ? sy / seeded : 0
    const GOLD = 2.399963229728653
    order.forEach((i, t) => {
      const p = initial[i]
      if (p) {
        this.x[i] = p.x - ox
        this.y[i] = p.y - oy
      } else {
        const r = EDGE_LEN * 0.9 * Math.sqrt(t + 0.5)
        const ang = t * GOLD + (rnd() - 0.5) * 0.3
        this.x[i] = r * Math.cos(ang)
        this.y[i] = r * Math.sin(ang)
      }
    })
    const warm = seeded >= m / 2
    this.iterations = forced ?? (warm ? Math.max(25, Math.round(iterationsFor(m) / 4)) : iterationsFor(m))
    this.tScale = warm ? 0.25 : 1
    this.temp0 = EDGE_LEN * (0.5 + 0.2 * Math.sqrt(m)) * this.tScale
  }

  get done(): boolean {
    return this.it >= this.iterations
  }

  private repelExact(): void {
    const { m, x, y, dx, dy } = this
    const k2 = EDGE_LEN * EDGE_LEN
    for (let i = 0; i < m; i++) {
      for (let j = i + 1; j < m; j++) {
        let vx = x[i] - x[j]
        let vy = y[i] - y[j]
        let d2 = vx * vx + vy * vy
        if (d2 < 1e-12) {
          vx = this.rnd() - 0.5 || 0.001
          vy = this.rnd() - 0.5 || 0.001
          d2 = vx * vx + vy * vy
        }
        const f = k2 / d2
        dx[i] += vx * f
        dy[i] += vy * f
        dx[j] -= vx * f
        dy[j] -= vy * f
      }
    }
  }

  private newCell(bx: number, by: number, size: number): number {
    const id = this.tMass.length
    this.tMass.push(0)
    this.tSx.push(0)
    this.tSy.push(0)
    this.tBx.push(bx)
    this.tBy.push(by)
    this.tSize.push(size)
    this.tBody.push(-1)
    this.tCh.push(-1, -1, -1, -1)
    return id
  }

  private quadrant(c: number, px: number, py: number): number {
    const h = this.tSize[c] / 2
    return (px >= this.tBx[c] + h ? 1 : 0) + (py >= this.tBy[c] + h ? 2 : 0)
  }

  private child(c: number, q: number): number {
    let ch = this.tCh[c * 4 + q]
    if (ch < 0) {
      const h = this.tSize[c] / 2
      ch = this.newCell(this.tBx[c] + (q & 1 ? h : 0), this.tBy[c] + (q & 2 ? h : 0), h)
      this.tCh[c * 4 + q] = ch
    }
    return ch
  }

  private buildTree(): void {
    const { m, x, y } = this
    this.tMass.length = this.tSx.length = this.tSy.length = this.tBx.length = this.tBy.length = this.tSize.length = this.tBody.length = this.tCh.length = 0
    let x0 = Infinity
    let y0 = Infinity
    let x1 = -Infinity
    let y1 = -Infinity
    for (let i = 0; i < m; i++) {
      if (x[i] < x0) x0 = x[i]
      if (x[i] > x1) x1 = x[i]
      if (y[i] < y0) y0 = y[i]
      if (y[i] > y1) y1 = y[i]
    }
    const size = Math.max(x1 - x0, y1 - y0, 1e-6) * 1.0001
    this.newCell(x0, y0, size)
    for (let i = 0; i < m; i++) {
      let c = 0
      let depth = 0
      for (;;) {
        if (this.tMass[c] === 0) {
          this.tBody[c] = i
          this.tMass[c] = 1
          this.tSx[c] = x[i]
          this.tSy[c] = y[i]
          break
        }
        if (this.tBody[c] >= 0) {
          if (depth >= MAX_DEPTH) {
            this.tMass[c]++
            this.tSx[c] += x[i]
            this.tSy[c] += y[i]
            break
          }
          const j = this.tBody[c]
          this.tBody[c] = -1
          const cj = this.child(c, this.quadrant(c, x[j], y[j]))
          this.tBody[cj] = j
          this.tMass[cj] = 1
          this.tSx[cj] = x[j]
          this.tSy[cj] = y[j]
        }
        this.tMass[c]++
        this.tSx[c] += x[i]
        this.tSy[c] += y[i]
        c = this.child(c, this.quadrant(c, x[i], y[i]))
        depth++
      }
    }
  }

  private repelTree(): void {
    this.buildTree()
    const { m, x, y, dx, dy, stack } = this
    const k2 = EDGE_LEN * EDGE_LEN
    for (let i = 0; i < m; i++) {
      stack.length = 0
      stack.push(0)
      let fx = 0
      let fy = 0
      while (stack.length) {
        const c = stack.pop()!
        const mass = this.tMass[c]
        if (mass === 0) continue
        const leaf = this.tBody[c] >= 0
        if (leaf && this.tBody[c] === i && mass === 1) continue
        const vx0 = x[i] - this.tSx[c] / mass
        const vy0 = y[i] - this.tSy[c] / mass
        const d2 = vx0 * vx0 + vy0 * vy0
        if (leaf || (this.tSize[c] * this.tSize[c]) / (d2 || 1e-12) < THETA2) {
          if (leaf && this.tBody[c] === i) continue // punti sovrapposti uniti in profondita' massima
          let vx = vx0
          let vy = vy0
          let dd = d2
          if (dd < 1e-12) {
            vx = this.rnd() - 0.5 || 0.001
            vy = this.rnd() - 0.5 || 0.001
            dd = vx * vx + vy * vy
          }
          const f = (mass * k2) / dd
          fx += vx * f
          fy += vy * f
        } else {
          const b = c * 4
          for (let q = 0; q < 4; q++) if (this.tCh[b + q] >= 0) stack.push(this.tCh[b + q])
        }
      }
      dx[i] += fx
      dy[i] += fy
    }
  }

  iterate(): void {
    const { m, x, y, dx, dy, ea, eb } = this
    dx.fill(0)
    dy.fill(0)
    if (m <= EXACT_MAX) this.repelExact()
    else this.repelTree()
    for (let e = 0; e < ea.length; e++) {
      const i = ea[e]
      const j = eb[e]
      const vx = x[i] - x[j]
      const vy = y[i] - y[j]
      const d = Math.hypot(vx, vy)
      if (d < 1e-6) continue
      const f = d / EDGE_LEN // d^2/k diviso d per normalizzare il vettore
      dx[i] -= vx * f
      dy[i] -= vy * f
      dx[j] += vx * f
      dy[j] += vy * f
    }
    const cool = 1 - this.it / this.iterations
    const temp = this.temp0 * cool * cool
    for (let i = 0; i < m; i++) {
      dx[i] -= 0.02 * x[i] // gravita' debole: tiene unita' la componente
      dy[i] -= 0.02 * y[i]
      const len = Math.hypot(dx[i], dy[i])
      if (len > 1e-9) {
        const lim = Math.min(len, temp)
        x[i] += (dx[i] / len) * lim
        y[i] += (dy[i] / len) * lim
      }
    }
    this.it++
  }
}

/** Layout incrementale: stessa matematica di `layout`, ma eseguibile a blocchi di iterazioni. */
export function layoutJob(nodes: Pick<TopologyNode, 'id' | 'degree'>[], edges: Pick<TopologyEdge, 'a' | 'b'>[], opts: LayoutOpts = {}): LayoutJob {
  const ids = [...new Set(nodes.map((n) => n.id))].sort()
  const n = ids.length
  const out = new Map<string, Pt>()
  if (n === 0) return { step: () => true, done: true, result: () => out }
  if (n === 1) {
    const s1 = opts.seeds?.get(ids[0])
    out.set(ids[0], s1 ? { ...s1 } : { x: (opts.width ?? 1000) / 2, y: (opts.height ?? 700) / 2 })
    return { step: () => true, done: true, result: () => out }
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
  const adjAll: number[][] = Array.from({ length: n }, () => [])
  for (const [i, j] of es) (adjAll[i].push(j), adjAll[j].push(i))

  // componenti connesse (union-find)
  const parent = Array.from({ length: n }, (_, i) => i)
  const find = (a: number): number => {
    while (parent[a] !== a) a = parent[a] = parent[parent[a]]
    return a
  }
  for (const [i, j] of es) parent[find(i)] = find(j)
  const members = new Map<number, number[]>()
  for (let i = 0; i < n; i++) {
    const r = find(i)
    const mm = members.get(r)
    if (mm) mm.push(i)
    else members.set(r, [i])
  }
  const comps = [...members.values()].sort((a, b) => b.length - a.length || a[0] - b[0])
  const local = new Int32Array(n)
  comps.forEach((mm) => mm.forEach((g, li) => (local[g] = li)))

  const px = new Float64Array(n) // coordinate finali (dopo l'impacchettamento)
  const py = new Float64Array(n)
  const layouts: (CompLayout | null)[] = comps.map(() => null)
  let ci = 0
  let packed = false

  const begin = (c: number): CompLayout => {
    const mm = comps[c]
    const m = mm.length
    const le: [number, number][] = []
    const adj: number[][] = Array.from({ length: m }, () => [])
    const deg = new Int32Array(m)
    for (let li = 0; li < m; li++) {
      for (const g of adjAll[mm[li]]) {
        const lj = local[g]
        adj[li].push(lj)
        if (li < lj) le.push([li, lj])
      }
      deg[li] = adj[li].length
    }
    const initial = mm.map((g) => opts.seeds?.get(ids[g]))
    return new CompLayout(m, le, deg, adj, initial, rnd, opts.iterations)
  }

  const pack = () => {
    const GAP = 70
    const boxes = comps.map((mm, c) => {
      const L = layouts[c]!
      let x0 = Infinity
      let y0 = Infinity
      let x1 = -Infinity
      let y1 = -Infinity
      for (let i = 0; i < mm.length; i++) {
        x0 = Math.min(x0, L.x[i])
        x1 = Math.max(x1, L.x[i])
        y0 = Math.min(y0, L.y[i])
        y1 = Math.max(y1, L.y[i])
      }
      return { x0, y0, w: x1 - x0, h: y1 - y0 }
    })
    const put = (c: number, ox: number, oy: number) => {
      const L = layouts[c]!
      const b = boxes[c]
      comps[c].forEach((g, li) => {
        px[g] = L.x[li] - b.x0 + ox
        py[g] = L.y[li] - b.y0 + oy
      })
    }
    put(0, 0, 0)
    if (comps.length === 1) return
    let area = 0
    let maxH = 0
    for (let c = 1; c < comps.length; c++) {
      area += (boxes[c].w + GAP) * (boxes[c].h + GAP)
      maxH = Math.max(maxH, boxes[c].h)
    }
    const limit = Math.max(boxes[0].h, maxH, 1.3 * Math.sqrt(area))
    let colX = boxes[0].w + GAP * 1.5
    let colW = 0
    let cy = 0
    for (let c = 1; c < comps.length; c++) {
      const b = boxes[c]
      if (cy > 0 && cy + b.h > limit) {
        colX += colW + GAP
        colW = 0
        cy = 0
      }
      put(c, colX, cy)
      colW = Math.max(colW, b.w)
      cy += b.h + GAP
    }
  }

  const isDone = () => ci >= comps.length
  const job: LayoutJob = {
    step(count) {
      for (let c = 0; c < count && !isDone(); c++) {
        const L = (layouts[ci] ??= begin(ci))
        if (!L.done) L.iterate()
        if (L.done) ci++
      }
      return isDone()
    },
    get done() {
      return isDone()
    },
    result() {
      if (!packed && isDone()) {
        pack()
        packed = true
      }
      for (let i = 0; i < n; i++) out.set(ids[i], { x: px[i], y: py[i] })
      return out
    },
  }
  return job
}

export function layout(nodes: Pick<TopologyNode, 'id' | 'degree'>[], edges: Pick<TopologyEdge, 'a' | 'b'>[], opts: LayoutOpts = {}): Map<string, Pt> {
  const job = layoutJob(nodes, edges, opts)
  job.step(Infinity)
  return job.result()
}

/** Layout senza bloccare il thread: blocchi di iterazioni da ~`budgetMs` ciascuno, con `yieldFn` (rAF) in mezzo. */
export async function layoutAsync(
  nodes: Pick<TopologyNode, 'id' | 'degree'>[],
  edges: Pick<TopologyEdge, 'a' | 'b'>[],
  opts: LayoutOpts = {},
  isStale: () => boolean = () => false,
  yieldFn: () => Promise<void> = () => new Promise((r) => requestAnimationFrame(() => r())),
  budgetMs = 8,
): Promise<Map<string, Pt> | null> {
  const job = layoutJob(nodes, edges, opts)
  while (!job.done) {
    const t0 = performance.now()
    do job.step(1)
    while (!job.done && performance.now() - t0 < budgetMs)
    if (job.done) break
    await yieldFn()
    if (isStale()) return null
  }
  return job.result()
}

/** Firma di nodi e archi (id): se invariata dopo un refresh non serve ricalcolare nulla. */
export function topologySignature(d: Pick<TopologyResult, 'nodes' | 'edges'>): string {
  const ns = d.nodes.map((n) => `${n.id}:${n.cut ? 1 : 0}${n.hub ? 1 : 0}`).sort().join(',')
  const es = d.edges.map((e) => `${e.a}>${e.b}:${e.snr ?? ''}:${[...e.sources].sort().join('+')}`).sort().join(',')
  return `${ns}|${es}`
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

// ---- gruppo principale, messa a fuoco ----

/** Id dei nodi della componente connessa piu' grande (a parita' vince quella col primo id in ordine). */
export function mainComponentIds(nodes: Pick<TopologyNode, 'id'>[], edges: Pick<TopologyEdge, 'a' | 'b'>[]): Set<string> {
  const ids = [...new Set(nodes.map((n) => n.id))].sort()
  const parent = new Map(ids.map((id) => [id, id]))
  const find = (a: string): string => {
    let r = a
    while (parent.get(r) !== r) r = parent.get(r)!
    while (parent.get(a) !== r) {
      const nx = parent.get(a)!
      parent.set(a, r)
      a = nx
    }
    return r
  }
  for (const e of edges) {
    if (!parent.has(e.a) || !parent.has(e.b)) continue
    const ra = find(e.a)
    const rb = find(e.b)
    if (ra !== rb) parent.set(ra < rb ? rb : ra, ra < rb ? ra : rb)
  }
  const groups = new Map<string, string[]>()
  for (const id of ids) {
    const r = find(id)
    const g = groups.get(r)
    if (g) g.push(id)
    else groups.set(r, [id])
  }
  let best: string[] = []
  for (const g of groups.values()) if (g.length > best.length) best = g
  return new Set(best)
}

/** Nodi raggiungibili da `id` in al massimo `hops` salti (include `id`; vuoto se `id` non ha archi e non e' noto). */
export function nodesWithinHops(edges: Pick<TopologyEdge, 'a' | 'b'>[], id: string, hops: number): Set<string> {
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    if (e.a === e.b) continue
    ;(adj.get(e.a) ?? adj.set(e.a, []).get(e.a)!).push(e.b)
    ;(adj.get(e.b) ?? adj.set(e.b, []).get(e.b)!).push(e.a)
  }
  const seen = new Set([id])
  let frontier = [id]
  for (let h = 0; h < hops && frontier.length > 0; h++) {
    const next: string[] = []
    for (const u of frontier) for (const v of adj.get(u) ?? []) if (!seen.has(v)) (seen.add(v), next.push(v))
    frontier = next
  }
  return seen
}

/** Sottografo: nodi in `keep` e archi con entrambi gli estremi in `keep`. */
export function subgraph<N extends { id: string }, E extends { a: string; b: string }>(nodes: N[], edges: E[], keep: ReadonlySet<string>): { nodes: N[]; edges: E[] } {
  return { nodes: nodes.filter((n) => keep.has(n.id)), edges: edges.filter((e) => keep.has(e.a) && keep.has(e.b)) }
}

// ---- etichette ----

export interface LabelItem {
  id: string
  name: string
  x: number
  y: number
  cut: boolean
  hub: boolean
  impact: number
  degree: number
}
export interface LabelOpts {
  /** Unita' del grafo per pixel (dimensione sullo schermo costante). */
  k: number
  /** Etichette sempre visibili (nodo sotto il puntatore, selezionato e vicini). */
  forced?: ReadonlySet<string>
  /** Con zoom avanzato: tutte le etichette che non si sovrappongono. */
  showAll?: boolean
  charPx?: number
  heightPx?: number
}

export const LABEL_MAX = 22
/** Testo mostrato: nomi lunghi accorciati. */
export const labelText = (name: string): string => (name.length > LABEL_MAX ? `${name.slice(0, LABEL_MAX - 1)}…` : name)

/**
 * Etichette da disegnare: prima le obbligatorie, poi cerniere (impatto), hub (grado) e, se `showAll`,
 * tutte le altre (grado); le non obbligatorie si saltano se il loro riquadro (sopra il nodo) si sovrappone
 * a uno gia' scelto. Scelta greedy, deterministica.
 */
export function pickLabels(items: LabelItem[], o: LabelOpts): Set<string> {
  const charW = (o.charPx ?? 7) * o.k
  const hgt = (o.heightPx ?? 16) * o.k
  const rank = (it: LabelItem): number => (o.forced?.has(it.id) ? 0 : it.cut ? 1 : it.hub ? 2 : 3)
  const cand = items
    .filter((it) => rank(it) < 3 || o.showAll)
    .sort((a, b) => rank(a) - rank(b) || (rank(a) === 1 ? b.impact - a.impact : 0) || b.degree - a.degree || (a.id < b.id ? -1 : 1))
  const cell = Math.max(1e-6, 170 * o.k)
  const grid = new Map<string, { x0: number; x1: number; y0: number; y1: number }[]>()
  const out = new Set<string>()
  for (const it of cand) {
    const w = labelText(it.name).length * charW + 6 * o.k
    const x0 = it.x - w / 2
    const x1 = it.x + w / 2
    const y1 = it.y - 6 * o.k
    const y0 = y1 - hgt
    const keys: string[] = []
    for (let cx = Math.floor(x0 / cell); cx <= Math.floor(x1 / cell); cx++) for (let cy = Math.floor(y0 / cell); cy <= Math.floor(y1 / cell); cy++) keys.push(`${cx},${cy}`)
    const forced = rank(it) === 0
    if (!forced) {
      let hit = false
      for (const key of keys) {
        for (const b of grid.get(key) ?? []) {
          if (x0 < b.x1 && x1 > b.x0 && y0 < b.y1 && y1 > b.y0) {
            hit = true
            break
          }
        }
        if (hit) break
      }
      if (hit) continue
    }
    out.add(it.id)
    const box = { x0, x1, y0, y1 }
    for (const key of keys) (grid.get(key) ?? grid.set(key, []).get(key)!).push(box)
  }
  return out
}

// ---- disposizione geografica ----

export const hasPosition = (n: { lat: number | null; lon: number | null }): boolean =>
  n.lat !== null && n.lon !== null && Number.isFinite(n.lat) && Number.isFinite(n.lon) && Math.abs(n.lat) <= 90 && Math.abs(n.lon) <= 180 && !(n.lat === 0 && n.lon === 0)

/** Proiezione Web Mercator in radianti: x cresce a est, y cresce verso sud (verso il basso sullo schermo). */
export function mercator(lat: number, lon: number): Pt {
  const la = (Math.max(-85.0511, Math.min(85.0511, lat)) * Math.PI) / 180
  return { x: (lon * Math.PI) / 180, y: -Math.log(Math.tan(Math.PI / 4 + la / 2)) }
}

/**
 * Posizioni geografiche. Nodi con coordinate: Web Mercator, scalata perche' il lato maggiore misuri `size`.
 * Senza coordinate: baricentro dei vicini gia' collocati (a ondate, con un piccolo scostamento), altrimenti una
 * colonna a destra. Nodi quasi sovrapposti si spargono a spirale. Null se nessun nodo ha una posizione.
 */
export function geoLayout(
  nodes: Pick<TopologyNode, 'id' | 'lat' | 'lon'>[],
  edges: Pick<TopologyEdge, 'a' | 'b'>[],
  size = 1600,
): Map<string, Pt> | null {
  const list = [...new Map(nodes.map((n) => [n.id, n])).values()].sort((a, b) => (a.id < b.id ? -1 : 1))
  const withPos = list.filter(hasPosition)
  if (withPos.length === 0) return null
  const raw = new Map(withPos.map((n) => [n.id, mercator(n.lat!, n.lon!)]))
  let x0 = Infinity
  let y0 = Infinity
  let x1 = -Infinity
  let y1 = -Infinity
  for (const p of raw.values()) {
    x0 = Math.min(x0, p.x)
    y0 = Math.min(y0, p.y)
    x1 = Math.max(x1, p.x)
    y1 = Math.max(y1, p.y)
  }
  const span = Math.max(x1 - x0, y1 - y0)
  const s = span > 1e-7 ? size / span : 1
  const placed = new Map<string, Pt>()
  for (const [id, p] of raw) placed.set(id, { x: (p.x - x0) * s, y: (p.y - y0) * s })
  const w = (x1 - x0) * s

  // vicini senza posizione: baricentro dei vicini collocati, a ondate per restare deterministici
  const adj = new Map<string, string[]>()
  for (const e of edges) {
    if (e.a === e.b) continue
    ;(adj.get(e.a) ?? adj.set(e.a, []).get(e.a)!).push(e.b)
    ;(adj.get(e.b) ?? adj.set(e.b, []).get(e.b)!).push(e.a)
  }
  const rest = list.filter((n) => !placed.has(n.id))
  let pending = rest.map((n) => n.id)
  for (let round = 0; round < 30 && pending.length > 0; round++) {
    const next: string[] = []
    const add: [string, Pt][] = []
    for (const id of pending) {
      const ps = (adj.get(id) ?? []).map((v) => placed.get(v)).filter((p): p is Pt => !!p)
      if (ps.length === 0) {
        next.push(id)
        continue
      }
      const ang = (fnv1a(id) % 3600) * (Math.PI / 1800)
      add.push([id, { x: ps.reduce((a, p) => a + p.x, 0) / ps.length + 16 * Math.cos(ang), y: ps.reduce((a, p) => a + p.y, 0) / ps.length + 16 * Math.sin(ang) }])
    }
    if (add.length === 0) break
    for (const [id, p] of add) placed.set(id, p)
    pending = next
  }
  // il resto: colonne a destra del riquadro
  const ROWS = 25
  pending.forEach((id, i) => placed.set(id, { x: w + 160 + Math.floor(i / ROWS) * 90, y: (i % ROWS) * 34 }))

  // sparge i punti troppo vicini (stessa cella da 14 unita') con una spirale deterministica
  const CELL = 14
  const taken = new Set<string>()
  const key = (p: Pt) => `${Math.floor(p.x / CELL)},${Math.floor(p.y / CELL)}`
  const out = new Map<string, Pt>()
  for (const n of list) {
    const p = placed.get(n.id)!
    let q = p
    for (let j = 1; taken.has(key(q)) && j < 80; j++) {
      const r = CELL * 0.9 * Math.sqrt(j)
      q = { x: p.x + r * Math.cos(j * 2.399963), y: p.y + r * Math.sin(j * 2.399963) }
    }
    taken.add(key(q))
    out.set(n.id, q)
  }
  return out
}
