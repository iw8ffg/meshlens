import { describe, expect, it } from 'vitest'

const sources = import.meta.glob('/src/**/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const src = (name: string): string => {
  const k = Object.keys(sources).find((p) => p.endsWith(name))
  if (!k) throw new Error(`manca ${name}`)
  return sources[k]
}

describe('MapView: integrazione degli strati', () => {
  const mv = src('/components/MapView.svelte')
  it('usa gli strati e non rimuove i layer esistenti', () => {
    for (const s of ['addOverlayLayers(', 'applyOverlayVisibility(', 'isInfrastructure', 'loadLayers(', 'saveLayers(', 'onlayer=', 'startTakLive', "'tak-points'"]) {
      expect(mv).toContain(s)
    }
    for (const s of ['addNodeLayers(', 'addLinkLayers(', 'addWaypointLayers(', 'addCoverageLayers(']) expect(mv).toContain(s)
  })
  it('ordine in setup(): nodi, strati, waypoint', () => {
    const a = mv.indexOf('addNodeLayers(m')
    const b = mv.indexOf('addOverlayLayers(m')
    const c = mv.indexOf('addWaypointLayers(m')
    expect(a).toBeGreaterThan(-1)
    expect(a).toBeLessThan(b)
    expect(b).toBeLessThan(c)
  })
  it('la chiave degli strati sta solo in layerstate.ts', () => {
    expect(mv).not.toContain('meshlens.layers')
    expect(mv).not.toContain('saveView(safeStorage(), { layers')
  })
  it('le sorgenti degli strati si scrivono solo in pushOverlays', () => {
    for (const id of ['precision-all', 'heat', 'tak']) {
      const calls = mv.match(new RegExp(`src\\('${id}'\\)\\?\\.setData`, 'g')) ?? []
      expect(calls).toHaveLength(1)
    }
  })
})

describe('Legend e LayerPanel', () => {
  it('Legend monta LayerPanel solo con onlayer', () => {
    const lg = src('/lib/map/Legend.svelte')
    const at = lg.indexOf('<LayerPanel')
    expect(at).toBeGreaterThan(-1)
    expect(lg.lastIndexOf('{#if onlayer', at)).toBeGreaterThan(-1)
  })
  it('LayerPanel: aria-describedby, Switch, nessun colore scritto a mano', () => {
    const lp = src('/lib/map/LayerPanel.svelte')
    expect(lp).toContain('aria-describedby')
    expect(lp).toContain('Switch')
    expect(lp).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })
})
