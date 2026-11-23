import { describe, expect, it } from 'vitest'

// Segnaposto della 1.6 (contratto §10.2): WP0 li crea vuoti e li monta; i pacchetti di lavoro li
// riempiono mantenendo nome del file e props. Il test controlla solo che esistano e che restino
// montati dove previsto, non che restino vuoti.
const sources = import.meta.glob('/src/**/*.svelte', { query: '?raw', import: 'default', eager: true }) as Record<string, string>

const PLACEHOLDERS = [
  '/src/components/Onboarding.svelte',
  '/src/components/GlobalSearch.svelte',
  '/src/components/WhatsNew.svelte',
  '/src/lib/ui/EmptyAction.svelte',
  '/src/components/settings/QuickReplies.svelte',
  '/src/components/settings/AlertRules.svelte',
  '/src/components/settings/Automations.svelte',
  '/src/components/settings/IgnoredNodes.svelte',
  '/src/components/settings/GuestAccess.svelte',
  '/src/components/node/NodeFlags.svelte',
  '/src/components/node/SensorSection.svelte',
  '/src/components/node/TraceSchedule.svelte',
  '/src/components/node/TakInfo.svelte',
  '/src/components/network/HealthView.svelte',
  '/src/components/network/TopologyView.svelte',
  '/src/lib/map/ZoneEditor.svelte',
]

const src = (path: string): string => {
  const s = sources[path]
  if (s === undefined) throw new Error(`manca ${path}`)
  return s
}

describe('segnaposto della 1.6', () => {
  it('ogni segnaposto esiste', () => {
    for (const p of PLACEHOLDERS) expect(Object.hasOwn(sources, p), p).toBe(true)
  })

  it('le viste di rete espongono `ready` dal blocco module', () => {
    for (const p of ['/src/components/network/HealthView.svelte', '/src/components/network/TopologyView.svelte']) {
      expect(src(p)).toMatch(/<script module[^>]*>[\s\S]*export const ready\b/)
    }
  })

  it('App monta avvio, ricerca e novità e inoltra i resync', () => {
    const app = src('/src/App.svelte')
    for (const tag of ['<Onboarding', '<GlobalSearch', '<WhatsNew']) expect(app).toContain(tag)
    expect(app).toContain('notifyWsResync()')
  })

  it('Impostazioni monta le cinque sezioni nuove', () => {
    const s = src('/src/components/Settings.svelte')
    for (const tag of ['<QuickReplies', '<AlertRules', '<Automations', '<IgnoredNodes', '<GuestAccess']) expect(s, tag).toContain(tag)
  })

  it('la scheda del nodo monta le quattro sezioni con {node}', () => {
    const s = src('/src/components/NodeDetail.svelte')
    for (const tag of ['<NodeFlags {node}', '<SensorSection {node}', '<TraceSchedule {node}', '<TakInfo {node}']) expect(s, tag).toContain(tag)
  })

  it('gli stati vuoti hanno EmptyAction', () => {
    expect(src('/src/components/NodeList.svelte')).toContain('<EmptyAction kind="nodes"')
    expect(src('/src/components/Network.svelte')).toContain('<EmptyAction kind="network"')
    expect(src('/src/components/Radios.svelte')).toContain('<EmptyAction kind="radios"')
  })

  it('la pagina Rete usa le viste solo se pronte', () => {
    const s = src('/src/components/NetworkPage.svelte')
    expect(s).toContain('healthReady')
    expect(s).toContain('topologyReady')
    expect(s).toContain('<HealthView')
    expect(s).toContain('<TopologyView')
  })
})
