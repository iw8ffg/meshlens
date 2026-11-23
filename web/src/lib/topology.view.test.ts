import { describe, expect, it } from 'vitest'
import { topology as it_ } from './i18n/it/topology'
import { topology as en } from './i18n/en/topology'

const sources = import.meta.glob('/src/**/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>
const src = (name: string): string => {
  const k = Object.keys(sources).find((p) => p.endsWith(name))
  if (!k) throw new Error(`manca ${name}`)
  return sources[k]
}

describe('TopologyView', () => {
  const v = src('/network/TopologyView.svelte')
  it('e\' pronta e usa le funzioni del client', () => {
    for (const s of ['export const ready: boolean = true', 'openConfig(', "'modules'", 'topologyData(', 'fitViewBox', 'listCuts', 'listHubs', 'role="img"', 'needsNeighborInfoHelp']) {
      expect(v).toContain(s)
    }
  })
  it('timer e rotellina', () => {
    const set = (v.match(/setInterval\(/g) ?? []).length
    const clear = (v.match(/clearInterval\(/g) ?? []).length
    expect(set).toBe(clear)
    expect(v).not.toMatch(/onwheel/)
    expect(v).toContain('preventDefault')
    expect(v).toContain("'wheel'")
  })
  it('nessun colore scritto a mano', () => {
    expect(v).not.toMatch(/#[0-9a-fA-F]{3,8}\b/)
  })
})

describe('NetworkPage', () => {
  const p = src('/components/NetworkPage.svelte')
  it('monta la vista topologia con la chiave dell\'etichetta del contratto', () => {
    expect(p).toContain('TopologyView')
    expect(p).toContain('ready as topologyReady')
    expect(p).toContain("view === 'topology'")
    expect(p).toContain('topology.view')
    expect(p).toContain('<HealthView')
    expect(p).toContain('onpick')
  })
})

describe('spiegazione di Neighbor Info', () => {
  it('cita intervallo e canale primario in entrambe le lingue', () => {
    expect(it_['topology.ni.explain']).toContain('4 ore')
    expect(it_['topology.ni.explain']).toContain('canale primario')
    expect(en['topology.ni.explain']).toContain('4 hours')
    expect(en['topology.ni.explain']).toContain('primary channel')
  })
})
