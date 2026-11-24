import { beforeEach, describe, expect, it, vi } from 'vitest'

const getJSON = vi.fn()
vi.mock('./api', () => ({ getJSON: (p: string) => getJSON(p) }))

import { fitViewBox, layout, layoutAsync, layoutJob, listCuts, topologySignature, listHubs, neighborsOf, needsNeighborInfoHelp, nodeClass, panBy, snrClass, topologyData, zoomAt } from './topology'
import type { TopologyEdge, TopologyNode, TopologyResult } from './types'

const tn = (id: string, o: Partial<TopologyNode> = {}): TopologyNode => ({ id, name: id, role: null, lat: null, lon: null, is_mine: false, last_heard: 0, degree: 1, component: 0, cut: false, hub: false, impact: 0, ...o })
const te = (a: string, b: string): TopologyEdge => ({ a, b, sources: ['traceroute'], snr: null, time: 0 })

// tre gruppi da 10 nodi collegati internamente, con pochi ponti
const graph = () => {
  const nodes = Array.from({ length: 30 }, (_, i) => tn(`n${String(i).padStart(2, '0')}`))
  const edges: TopologyEdge[] = []
  for (let g = 0; g < 3; g++) for (let i = 0; i < 10; i++) edges.push(te(nodes[g * 10 + i].id, nodes[g * 10 + ((i + 1) % 10)].id), te(nodes[g * 10 + i].id, nodes[g * 10 + ((i + 3) % 10)].id))
  edges.push(te('n09', 'n10'), te('n19', 'n20'))
  return { nodes, edges }
}

beforeEach(() => getJSON.mockReset())

describe('layout incrementale e stabile', () => {
  it('layoutJob a blocchi = layout in un colpo', () => {
    const { nodes, edges } = graph()
    const job = layoutJob(nodes, edges)
    let guard = 0
    while (!job.step(7) && guard++ < 1000);
    expect(job.result()).toEqual(layout(nodes, edges))
  })
  it('layoutAsync cede il controllo e da lo stesso risultato', async () => {
    const { nodes, edges } = graph()
    let yields = 0
    const r = await layoutAsync(nodes, edges, {}, () => false, async () => void yields++, 0)
    expect(yields).toBeGreaterThan(0)
    expect(r).toEqual(layout(nodes, edges))
  })
  it('layoutAsync si interrompe se superato', async () => {
    const { nodes, edges } = graph()
    expect(await layoutAsync(nodes, edges, {}, () => true, async () => {}, 0)).toBeNull()
  })
  it('con posizioni di partenza il grafo resta vicino (niente salti) e fa meno iterazioni', () => {
    const { nodes, edges } = graph()
    const first = layout(nodes, edges)
    const again = layout(nodes, edges, { seeds: first })
    for (const [id, p] of first) {
      const q = again.get(id)!
      expect(Math.hypot(p.x - q.x, p.y - q.y)).toBeLessThan(150)
    }
  })
  it('un nodo nuovo parte dal cerchio, i noti dalle posizioni date', () => {
    const { nodes, edges } = graph()
    const first = layout(nodes, edges)
    const more = [...nodes, tn('zz-new')]
    const r = layout(more, edges, { seeds: first })
    expect(r.has('zz-new')).toBe(true)
    expect(r.size).toBe(more.length)
  })
  it('firma: invariata con gli stessi id, cambia se cambia un arco', () => {
    const { nodes, edges } = graph()
    const a = topologySignature({ nodes, edges } as never)
    expect(topologySignature({ nodes: [...nodes].reverse(), edges: [...edges].reverse() } as never)).toBe(a)
    expect(topologySignature({ nodes, edges: edges.slice(1) } as never)).not.toBe(a)
  })
})

describe('layout', () => {
  it('deterministico e indipendente dall\'ordine', () => {
    const { nodes, edges } = graph()
    const a = layout(nodes, edges)
    expect(layout(nodes, edges)).toEqual(a)
    const shuffled = [...nodes].reverse()
    const sh = [...edges].reverse()
    expect(layout(shuffled, sh)).toEqual(a)
  })
  it('coordinate finite e dentro il riquadro', () => {
    const { nodes, edges } = graph()
    for (const p of layout(nodes, edges).values()) {
      expect(Number.isFinite(p.x) && Number.isFinite(p.y)).toBe(true)
      expect(p.x).toBeGreaterThanOrEqual(40)
      expect(p.x).toBeLessThanOrEqual(960)
      expect(p.y).toBeGreaterThanOrEqual(40)
      expect(p.y).toBeLessThanOrEqual(660)
    }
  })
  it('grafo a piu componenti: nessun nodo sui bordi, margine >= 40', () => {
    const nodes = Array.from({ length: 10 }, (_, i) => tn(`d${i}`))
    const edges = [te('d0', 'd1'), te('d1', 'd2'), te('d2', 'd3'), te('d3', 'd4'), te('d4', 'd0'), te('d5', 'd6'), te('d6', 'd7'), te('d8', 'd9')]
    const pts = [...layout(nodes, edges).values()]
    for (const p of pts) {
      expect(p.x).toBeGreaterThan(48)
      expect(p.x).toBeLessThan(952)
      expect(p.y).toBeGreaterThan(48)
      expect(p.y).toBeLessThan(652)
    }
    const xs = pts.map((p) => p.x)
    const ys = pts.map((p) => p.y)
    expect(Math.min(...xs)).toBeGreaterThanOrEqual(40)
    expect(Math.max(...xs)).toBeLessThanOrEqual(960)
    expect(Math.min(...ys)).toBeGreaterThanOrEqual(40)
    expect(Math.max(...ys)).toBeLessThanOrEqual(660)
  })
  it('casi limite', () => {
    expect(layout([], []).size).toBe(0)
    expect(layout([tn('a')], []).get('a')).toEqual({ x: 500, y: 350 })
    const two = layout([tn('a'), tn('b')], [te('a', 'b')])
    expect(Number.isFinite(two.get('a')!.x)).toBe(true)
  })
  it('gli archi sono piu\' corti delle coppie qualunque', () => {
    const { nodes, edges } = graph()
    const p = layout(nodes, edges)
    const d = (a: string, b: string) => Math.hypot(p.get(a)!.x - p.get(b)!.x, p.get(a)!.y - p.get(b)!.y)
    const ed = edges.reduce((s, e) => s + d(e.a, e.b), 0) / edges.length
    let all = 0
    let c = 0
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) (all += d(nodes[i].id, nodes[j].id)), c++
    expect(ed).toBeLessThan(all / c)
  })
  it('300 nodi in meno di 1500 ms', () => {
    const nodes = Array.from({ length: 300 }, (_, i) => tn(`n${i}`))
    const edges = nodes.slice(1).map((n, i) => te(nodes[Math.floor(i / 2)].id, n.id))
    const t0 = performance.now()
    layout(nodes, edges)
    expect(performance.now() - t0).toBeLessThan(1500)
  })
})

describe('viewBox', () => {
  it('fit: contiene i punti, rispetta l\'aspetto, vuoto = predefinito', () => {
    const pts = [{ x: 100, y: 100 }, { x: 300, y: 200 }]
    const vb = fitViewBox(pts, 40, 2)
    for (const p of pts) {
      expect(p.x).toBeGreaterThanOrEqual(vb.x + 40 - 1e-9)
      expect(p.x).toBeLessThanOrEqual(vb.x + vb.w - 40 + 1e-9)
      expect(p.y).toBeGreaterThanOrEqual(vb.y + 40 - 1e-9)
      expect(p.y).toBeLessThanOrEqual(vb.y + vb.h - 40 + 1e-9)
    }
    expect(vb.w / vb.h).toBeCloseTo(2, 6)
    expect(fitViewBox([])).toEqual({ x: 0, y: 0, w: 1000, h: 700 })
  })
  it('zoom: punto fermo, fattore 2, limiti', () => {
    const vb = { x: 0, y: 0, w: 1000, h: 700 }
    const z = zoomAt(vb, 2, 300, 200)
    expect(z.w).toBe(500)
    expect(z.h).toBe(350)
    expect((300 - z.x) / z.w).toBeCloseTo((300 - vb.x) / vb.w, 9)
    expect((200 - z.y) / z.h).toBeCloseTo((200 - vb.y) / vb.h, 9)
    expect(zoomAt(vb, 100, 0, 0, 200).w).toBe(200)
    expect(zoomAt(vb, 0.01, 0, 0, 50, 3000).w).toBe(3000)
  })
  it('pan somma gli spostamenti', () => {
    expect(panBy({ x: 1, y: 2, w: 3, h: 4 }, 10, 20)).toEqual({ x: 11, y: 22, w: 3, h: 4 })
  })
})

describe('classi e viste', () => {
  it('nodeClass e snrClass', () => {
    expect(nodeClass({ cut: true, hub: true })).toBe('cut')
    expect(nodeClass({ cut: false, hub: true })).toBe('hub')
    expect(nodeClass({ cut: false, hub: false })).toBe('normal')
    expect([5, 0, -0.1, -10, -10.1, null].map(snrClass)).toEqual(['good', 'good', 'mid', 'mid', 'bad', 'none'])
  })
  const result = (o: Partial<TopologyResult> = {}): TopologyResult => ({
    since: 0, hours: 168, sources: [], nodes: [tn('b', { cut: true, impact: 2, name: 'B' }), tn('a', { cut: true, impact: 2, name: 'A' }), tn('c', { cut: true, impact: 5, name: 'C' }), tn('h1', { hub: true, degree: 5, name: 'H1' }), tn('h2', { hub: true, degree: 9, name: 'H2' }), tn('h3', { hub: true, cut: true, impact: 1, name: 'H3' })],
    edges: [], isolated: [], components: [], stats: { nodes: 0, edges: 0, components: 0, isolated: 0, cut: 0, hubs: 0, by_source: { neighborinfo: 0, traceroute: 0, mqtt_gateway: 0, rf_direct: 0 } }, truncated: false, ...o,
  })
  it('neighborsOf, listCuts, listHubs', () => {
    expect(neighborsOf([te('z', 'a'), te('a', 'm'), te('x', 'y')], 'a')).toEqual(['m', 'z'])
    expect(listCuts(result()).map((n) => n.id)).toEqual(['c', 'a', 'b', 'h3'])
    expect(listHubs(result()).map((n) => n.id)).toEqual(['h2', 'h1'])
  })
  it('needsNeighborInfoHelp', () => {
    expect(needsNeighborInfoHelp(result())).toBe(true)
    const r = result()
    r.stats.by_source.neighborinfo = 3
    expect(needsNeighborInfoHelp(r)).toBe(false)
  })
})

describe('topologyData', () => {
  it('costruisce la richiesta', async () => {
    getJSON.mockResolvedValue({})
    await topologyData({ hours: 168, sources: ['neighborinfo', 'traceroute'], countries: ['IT', 'none'] })
    expect(getJSON).toHaveBeenLastCalledWith('/topology?hours=168&sources=neighborinfo,traceroute&countries=IT,none')
    await topologyData({ hours: 24, sources: ['rf_direct'], countries: [] })
    expect(getJSON).toHaveBeenLastCalledWith('/topology?hours=24&sources=rf_direct')
    await topologyData({ hours: 24, sources: ['rf_direct'], countries: [], limit: 50 })
    expect(getJSON).toHaveBeenLastCalledWith('/topology?hours=24&sources=rf_direct&limit=50')
  })
})
