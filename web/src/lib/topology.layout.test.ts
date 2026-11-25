import { describe, expect, it, vi } from 'vitest'

vi.mock('./api', () => ({ getJSON: vi.fn() }))

import {
  fitViewBox, geoLayout, hasPosition, labelText, layout, layoutJob, mainComponentIds, mercator, nodesWithinHops, pickLabels, subgraph, topologyData,
} from './topology'
import type { LabelItem } from './topology'
import type { TopologyEdge, TopologyNode } from './types'

const tn = (id: string, o: Partial<TopologyNode> = {}): TopologyNode => ({ id, name: id, role: null, lat: null, lon: null, is_mine: false, last_heard: 0, degree: 1, component: 0, cut: false, hub: false, impact: 0, ...o })
const te = (a: string, b: string): TopologyEdge => ({ a, b, sources: ['traceroute'], snr: null, time: 0 })

/** Generatore pseudo-casuale locale ai test. */
const prng = (seed: number) => () => {
  seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0
  return seed / 4294967296
}

/** ~500 nodi e ~1000 archi: 5 gruppi regionali densi uniti da pochi nodi cerniera e qualche componente piccola. */
function bigGraph(nNodes = 500, nEdges = 1000) {
  const rnd = prng(7)
  const nodes = Array.from({ length: nNodes }, (_, i) => tn(`n${String(i).padStart(4, '0')}`))
  const set = new Set<string>()
  const edges: TopologyEdge[] = []
  const add = (a: number, b: number) => {
    if (a === b) return
    const k = a < b ? `${a}-${b}` : `${b}-${a}`
    if (set.has(k)) return
    set.add(k)
    edges.push(te(nodes[a].id, nodes[b].id))
  }
  const big = Math.floor(nNodes * 0.85)
  const groups = 5
  const per = Math.floor(big / groups)
  for (let g = 0; g < groups; g++) {
    const base = g * per
    for (let i = 1; i < per; i++) add(base + i, base + Math.floor(rnd() * i)) // albero
  }
  for (let g = 0; g + 1 < groups; g++) add(g * per + 1, (g + 1) * per + 2) // ponti
  while (edges.length < nEdges - 30) {
    const g = Math.floor(rnd() * groups)
    add(g * per + Math.floor(rnd() * per), g * per + Math.floor(rnd() * per))
  }
  // componenti piccole sul resto
  for (let i = big; i + 1 < nNodes; i += 3) {
    add(i, i + 1)
    if (i + 2 < nNodes) add(i + 1, i + 2)
  }
  return { nodes, edges }
}

describe('layout senza bordi (500 nodi, ~1000 archi)', () => {
  const { nodes, edges } = bigGraph()
  const t0 = performance.now()
  const pos = layout(nodes, edges)
  const elapsed = performance.now() - t0

  it('grafo di prova ben formato', () => {
    expect(nodes.length).toBe(500)
    expect(edges.length).toBeGreaterThan(900)
  })
  it('tutti i nodi dentro il viewBox adattato', () => {
    const pts = [...pos.values()]
    expect(pts.length).toBe(500)
    const vb = fitViewBox(pts, 40, 1.6)
    for (const p of pts) {
      expect(Number.isFinite(p.x) && Number.isFinite(p.y)).toBe(true)
      expect(p.x).toBeGreaterThanOrEqual(vb.x)
      expect(p.x).toBeLessThanOrEqual(vb.x + vb.w)
      expect(p.y).toBeGreaterThanOrEqual(vb.y)
      expect(p.y).toBeLessThanOrEqual(vb.y + vb.h)
    }
  })
  it('niente nodi in fila su un bordo: <5% con la stessa x o y (a 1 px)', () => {
    const pts = [...pos.values()]
    const share = (sel: (p: { x: number; y: number }) => number) => {
      const cnt = new Map<number, number>()
      for (const p of pts) cnt.set(Math.round(sel(p)), (cnt.get(Math.round(sel(p))) ?? 0) + 1)
      let worst = 0
      for (const c of cnt.values()) worst = Math.max(worst, c)
      return worst / pts.length
    }
    expect(share((p) => p.x)).toBeLessThan(0.05)
    expect(share((p) => p.y)).toBeLessThan(0.05)
  })
  it('nodi distinti non coincidono e le componenti non si sovrappongono', () => {
    const pts = [...pos.values()]
    const seen = new Set(pts.map((p) => `${Math.round(p.x * 10)},${Math.round(p.y * 10)}`))
    expect(seen.size).toBe(pts.length)
  })
  it('deterministico e indipendente dall\'ordine', () => {
    const again = layout([...nodes].reverse(), [...edges].reverse())
    expect(again).toEqual(pos)
  })
  it('tempo complessivo ragionevole', () => {
    expect(elapsed).toBeLessThan(6000)
  })
  it('ogni blocco di iterazioni resta breve (<= ~8 ms in media)', () => {
    const job = layoutJob(nodes, edges)
    let worst = 0
    let total = 0
    let steps = 0
    while (!job.done) {
      const s = performance.now()
      job.step(1)
      const d = performance.now() - s
      worst = Math.max(worst, d)
      total += d
      steps++
    }
    expect(total / steps).toBeLessThan(8)
    expect(worst).toBeLessThan(120) // soglia larga: protegge solo da blocchi enormi, la CI puo' essere lenta
  })
  it('le componenti sono affiancate: la principale e le piccole non si sovrappongono', () => {
    const main = mainComponentIds(nodes, edges)
    const box = (ids: string[]) => {
      const xs = ids.map((i) => pos.get(i)!.x)
      const ys = ids.map((i) => pos.get(i)!.y)
      return { x0: Math.min(...xs), x1: Math.max(...xs), y0: Math.min(...ys), y1: Math.max(...ys) }
    }
    const a = box([...main])
    const others = nodes.filter((n) => !main.has(n.id)).map((n) => n.id)
    const b = box(others)
    expect(a.x1 < b.x0 || b.x1 < a.x0 || a.y1 < b.y0 || b.y1 < a.y0).toBe(true)
  })
})

describe('fitViewBox con rapporto variabile', () => {
  it('rispetta il rapporto del contenitore', () => {
    const vb = fitViewBox([{ x: -5000, y: 20 }, { x: 8000, y: 900 }], 40, 2.4)
    expect(vb.w / vb.h).toBeCloseTo(2.4, 6)
    expect(vb.w).toBeGreaterThan(13000)
  })
})

describe('gruppo principale', () => {
  it('trova la componente piu\' grande, con parita\' la prima per id', () => {
    const nodes = ['a', 'b', 'c', 'd', 'e', 'f', 'g'].map((i) => tn(i))
    const edges = [te('a', 'b'), te('b', 'c'), te('d', 'e'), te('e', 'f'), te('f', 'g')]
    expect([...mainComponentIds(nodes, edges)].sort()).toEqual(['d', 'e', 'f', 'g'])
    const tie = [te('a', 'b'), te('c', 'd')]
    expect([...mainComponentIds(nodes.slice(0, 4), tie)].sort()).toEqual(['a', 'b'])
    expect(mainComponentIds([], []).size).toBe(0)
  })
  it('sottografo con solo il gruppo principale', () => {
    const nodes = ['a', 'b', 'c', 'd', 'e'].map((i) => tn(i))
    const edges = [te('a', 'b'), te('b', 'c'), te('d', 'e')]
    const g = subgraph(nodes, edges, mainComponentIds(nodes, edges))
    expect(g.nodes.map((n) => n.id)).toEqual(['a', 'b', 'c'])
    expect(g.edges.length).toBe(2)
  })
  it('la richiesta al server chiede main=1', async () => {
    const api = await import('./api')
    ;(api.getJSON as ReturnType<typeof vi.fn>).mockResolvedValue({})
    await topologyData({ hours: 168, sources: ['traceroute'], countries: [], main: true })
    expect(api.getJSON).toHaveBeenLastCalledWith('/topology?hours=168&sources=traceroute&main=1')
  })
})

describe('messa a fuoco (salti)', () => {
  // catena a-b-c-d-e e ramo c-x
  const edges = [te('a', 'b'), te('b', 'c'), te('c', 'd'), te('d', 'e'), te('c', 'x')]
  it('1, 2 e 3 salti', () => {
    expect([...nodesWithinHops(edges, 'c', 1)].sort()).toEqual(['b', 'c', 'd', 'x'])
    expect([...nodesWithinHops(edges, 'c', 2)].sort()).toEqual(['a', 'b', 'c', 'd', 'e', 'x'])
    expect([...nodesWithinHops(edges, 'a', 3)].sort()).toEqual(['a', 'b', 'c', 'd', 'x'])
    expect([...nodesWithinHops(edges, 'a', 1)].sort()).toEqual(['a', 'b'])
  })
  it('nodo senza archi o 0 salti: solo se stesso', () => {
    expect([...nodesWithinHops(edges, 'zz', 3)]).toEqual(['zz'])
    expect([...nodesWithinHops(edges, 'c', 0)]).toEqual(['c'])
  })
  it('sottografo del fuoco tiene solo gli archi interni', () => {
    const nodes = ['a', 'b', 'c', 'd', 'e', 'x'].map((i) => tn(i))
    const g = subgraph(nodes, edges, nodesWithinHops(edges, 'c', 1))
    expect(g.nodes.map((n) => n.id).sort()).toEqual(['b', 'c', 'd', 'x'])
    expect(g.edges.length).toBe(3)
  })
})

describe('etichette', () => {
  const item = (id: string, x: number, y: number, o: Partial<LabelItem> = {}): LabelItem => ({ id, name: id.padEnd(8, 'x'), x, y, cut: false, hub: false, impact: 0, degree: 1, ...o })
  it('mostra solo cerniere e hub, i normali no', () => {
    const items = [item('c', 0, 0, { cut: true, impact: 3 }), item('h', 1000, 0, { hub: true, degree: 6 }), item('n', 2000, 0)]
    expect([...pickLabels(items, { k: 1 })].sort()).toEqual(['c', 'h'])
  })
  it('il nodo sotto il puntatore e i vicini compaiono sempre', () => {
    const items = [item('n', 0, 0), item('m', 3000, 0), item('c', 6000, 0, { cut: true, impact: 1 })]
    const r = pickLabels(items, { k: 1, forced: new Set(['n', 'm']) })
    expect(r.has('n') && r.has('m') && r.has('c')).toBe(true)
  })
  it('scarta quelle che si sovrappongono, con precedenza all\'impatto maggiore', () => {
    const items = [item('a', 0, 0, { cut: true, impact: 2 }), item('b', 5, 0, { cut: true, impact: 9 }), item('c', 2000, 0, { cut: true, impact: 1 })]
    const r = pickLabels(items, { k: 1 })
    expect(r.has('b')).toBe(true)
    expect(r.has('a')).toBe(false)
    expect(r.has('c')).toBe(true)
  })
  it('le obbligatorie restano anche se si sovrappongono e fanno spazio alle altre', () => {
    const items = [item('f1', 0, 0), item('f2', 5, 0), item('h', 8, 0, { hub: true, degree: 9 })]
    const r = pickLabels(items, { k: 1, forced: new Set(['f1', 'f2']) })
    expect([...r].sort()).toEqual(['f1', 'f2'])
  })
  it('con zoom avanzato (showAll) compaiono anche i nodi normali che non collidono', () => {
    const items = [item('c', 0, 0, { cut: true, impact: 1 }), item('n1', 1000, 0), item('n2', 1004, 0), item('n3', 0, 1000)]
    const r = pickLabels(items, { k: 1, showAll: true })
    expect(r.has('c') && r.has('n1') && r.has('n3')).toBe(true)
    expect(r.has('n2')).toBe(false)
  })
  it('lo zoom cambia lo spazio: stesso grafo, con k piccolo (ingrandito) le etichette non si toccano piu\'', () => {
    const items = [item('a', 0, 0, { hub: true, degree: 5 }), item('b', 60, 0, { hub: true, degree: 4 })]
    expect(pickLabels(items, { k: 1 }).size).toBe(1)
    expect(pickLabels(items, { k: 0.2 }).size).toBe(2)
  })
  it('labelText accorcia i nomi lunghi', () => {
    expect(labelText('Breve')).toBe('Breve')
    expect(labelText('x'.repeat(40)).length).toBe(22)
  })
  it('molti nodi: veloce e senza sovrapposizioni tra le scelte', () => {
    const rnd = prng(3)
    const items = Array.from({ length: 400 }, (_, i) => item(`n${i}`, rnd() * 3000, rnd() * 2000, { hub: i % 4 === 0, degree: 1 + (i % 9) }))
    const t0 = performance.now()
    const r = pickLabels(items, { k: 2, showAll: true })
    expect(performance.now() - t0).toBeLessThan(200)
    expect(r.size).toBeGreaterThan(20)
    const picked = items.filter((i) => r.has(i.id))
    for (let i = 0; i < picked.length; i++)
      for (let j = i + 1; j < picked.length; j++) {
        const a = picked[i]
        const b = picked[j]
        const w = (it: LabelItem) => labelText(it.name).length * 7 * 2 + 12
        const overlapX = Math.abs(a.x - b.x) < (w(a) + w(b)) / 2
        const overlapY = Math.abs(a.y - b.y) < 32
        expect(overlapX && overlapY).toBe(false)
      }
  })
})

describe('disposizione geografica', () => {
  const MI = { lat: 45.46, lon: 9.19 }
  const RM = { lat: 41.9, lon: 12.5 }
  const NA = { lat: 40.85, lon: 14.27 }
  it('hasPosition ignora null, 0/0 e valori assurdi', () => {
    expect(hasPosition(MI)).toBe(true)
    expect(hasPosition({ lat: null, lon: 9 })).toBe(false)
    expect(hasPosition({ lat: 0, lon: 0 })).toBe(false)
    expect(hasPosition({ lat: 95, lon: 9 })).toBe(false)
  })
  it('Mercator: nord in alto (y minore), est a destra (x maggiore), monotona', () => {
    const a = mercator(MI.lat, MI.lon)
    const b = mercator(RM.lat, RM.lon)
    expect(b.y).toBeGreaterThan(a.y)
    expect(b.x).toBeGreaterThan(a.x)
    expect(mercator(0, 0).y).toBeCloseTo(0, 9)
    expect(Number.isFinite(mercator(90, 0).y)).toBe(true)
    // la scala verticale cresce con la latitudine (a 60 gradi circa il doppio dell'equatore)
    const d0 = mercator(1, 0).y - mercator(0, 0).y
    const d60 = mercator(61, 0).y - mercator(60, 0).y
    expect(Math.abs(d60 / d0)).toBeGreaterThan(1.8)
  })
  it('collocati hanno la loro posizione relativa, nessuna collisione', () => {
    const nodes = [tn('mi', MI), tn('rm', RM), tn('na', NA)]
    const p = geoLayout(nodes, [])!
    expect(p.get('mi')!.y).toBeLessThan(p.get('rm')!.y)
    expect(p.get('rm')!.y).toBeLessThan(p.get('na')!.y)
    expect(p.get('mi')!.x).toBeLessThan(p.get('rm')!.x)
    const xs = [...p.values()].map((q) => q.x)
    expect(Math.max(...xs) - Math.min(...xs)).toBeLessThanOrEqual(1700)
  })
  it('un nodo senza posizione sta vicino al baricentro dei vicini collocati', () => {
    const nodes = [tn('mi', MI), tn('rm', RM), tn('x')]
    const p = geoLayout(nodes, [te('x', 'mi'), te('x', 'rm')])!
    const mid = { x: (p.get('mi')!.x + p.get('rm')!.x) / 2, y: (p.get('mi')!.y + p.get('rm')!.y) / 2 }
    expect(Math.hypot(p.get('x')!.x - mid.x, p.get('x')!.y - mid.y)).toBeLessThan(80)
  })
  it('catena di nodi senza posizione si propaga; i nodi irraggiungibili vanno in colonna a destra', () => {
    const nodes = [tn('mi', MI), tn('rm', RM), tn('a'), tn('b'), tn('lonely'), tn('lonely2')]
    const p = geoLayout(nodes, [te('a', 'mi'), te('b', 'a'), te('lonely', 'lonely2')])!
    expect(Math.hypot(p.get('b')!.x - p.get('mi')!.x, p.get('b')!.y - p.get('mi')!.y)).toBeLessThan(200)
    const maxPositioned = Math.max(p.get('mi')!.x, p.get('rm')!.x)
    expect(p.get('lonely')!.x).toBeGreaterThan(maxPositioned)
    expect(p.get('lonely2')!.x).toBeGreaterThan(maxPositioned)
  })
  it('nodi nello stesso punto vengono sparsi', () => {
    const nodes = Array.from({ length: 12 }, (_, i) => tn(`s${i}`, MI)).concat(tn('far', NA))
    const p = geoLayout(nodes, [])!
    const cells = new Set([...p.values()].map((q) => `${Math.round(q.x)},${Math.round(q.y)}`))
    expect(cells.size).toBe(13)
  })
  it('senza nessuna posizione: null; deterministico', () => {
    expect(geoLayout([tn('a'), tn('b')], [te('a', 'b')])).toBeNull()
    const nodes = [tn('mi', MI), tn('rm', RM), tn('x'), tn('y')]
    const edges = [te('x', 'mi'), te('y', 'x')]
    expect(geoLayout(nodes, edges)).toEqual(geoLayout([...nodes].reverse(), [...edges].reverse()))
  })
})
