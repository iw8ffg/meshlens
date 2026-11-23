import { describe, expect, it } from 'vitest'

// Nodi ignorati (contratto §4.6): le viste che leggono tutti i nodi passano da visibleNodes
// (o da matchNode/networkNodes/searchNodes/linksToGeoJSON, che lo usano). Controllo sul sorgente.
const sources = import.meta.glob('/src/**/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

describe('viste senza nodi ignorati', () => {
  it('App passa a NetworkPage solo i nodi visibili', () => {
    expect(sources['/src/App.svelte']).toContain('<NetworkPage nodes={visibleNodes(app.nodes.values())}')
  })
  it('CoverageSetup e Prediction filtrano i nodi ignorati', () => {
    expect(sources['/src/components/CoverageSetup.svelte']).toContain('visibleNodes(app.nodes.values())')
    expect(sources['/src/components/Prediction.svelte']).toContain('visibleNodes(app.nodes.values())')
  })
})
