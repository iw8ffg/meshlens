<script module lang="ts">
  // Vista Topologia della pagina Rete (E8). Compare in NetworkPage solo con ready = true.
  export const ready: boolean = true
</script>

<script lang="ts">
  import { onMount } from 'svelte'
  import { app, openConfig } from '../../lib/stores.svelte'
  import { t, tn } from '../../lib/i18n/index.svelte'
  import type { MsgKey } from '../../lib/i18n/index.svelte'
  import { onWsResync } from '../../lib/wsext'
  import {
    DEFAULT_PERIOD, PERIODS, fitViewBox, layout, listCuts, listHubs, needsNeighborInfoHelp, neighborsOf, nodeClass, panBy,
    snrClass, topologyData, zoomAt,
  } from '../../lib/topology'
  import type { ViewBox } from '../../lib/topology'
  import type { Link, TopologyEdge, TopologyResult } from '../../lib/types'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Empty from '../../lib/ui/Empty.svelte'
  import Segmented from '../../lib/ui/Segmented.svelte'
  import Skeleton from '../../lib/ui/Skeleton.svelte'
  import Switch from '../../lib/ui/Switch.svelte'

  /** Apre i dettagli del nodo (stesso canale di NetworkStats: pickId di NetworkPage). */
  let { onpick }: { onpick?: (id: string) => void } = $props()

  const SOURCES: Link['source'][] = ['neighborinfo', 'traceroute', 'mqtt_gateway', 'rf_direct']
  const PERIOD_KEYS: Record<number, MsgKey> = { 24: 'topology.period.24h', 168: 'topology.period.7d', 720: 'topology.period.30d' }
  const REFRESH_MS = 120_000

  let periodStr = $state(String(DEFAULT_PERIOD))
  const hours = $derived(Number(periodStr))
  let active = $state<Record<Link['source'], boolean>>({ neighborinfo: true, traceroute: true, mqtt_gateway: true, rf_direct: true })
  let data = $state<TopologyResult | null>(null)
  let loading = $state(true)
  let error = $state(false)
  let tick = $state(0)
  let selectedId = $state<string | null>(null)
  let userVb = $state<ViewBox | null>(null)
  let svgW = $state(800)
  let svgEl: SVGSVGElement | undefined = $state()

  const chosen = $derived(SOURCES.filter((s) => active[s]))
  const periodItems = $derived(PERIODS.map((h) => ({ value: String(h), label: t(PERIOD_KEYS[h]) })))

  $effect(() => {
    const h = hours
    const srcs = chosen
    const countries = [...app.filter.countries]
    void tick
    if (srcs.length === 0) {
      data = null
      loading = false
      error = false
      return
    }
    loading = true
    error = false
    let stale = false
    topologyData({ hours: h, sources: srcs, countries })
      .then((r) => {
        if (stale) return
        data = r
        userVb = null
      })
      .catch(() => {
        if (!stale) error = true
      })
      .finally(() => {
        if (!stale) loading = false
      })
    return () => {
      stale = true
    }
  })

  onMount(() => {
    const iv = setInterval(() => tick++, REFRESH_MS)
    const off = onWsResync(() => tick++)
    return () => {
      clearInterval(iv)
      off()
    }
  })

  const pos = $derived(data ? layout(data.nodes, data.edges) : new Map())
  const fitted = $derived(fitViewBox([...pos.values()], 40, 1000 / 700))
  const vb = $derived(userVb ?? fitted)
  /** Unita' del grafo per pixel: dimensioni (cerchi, testo, tratti) costanti sullo schermo a ogni zoom. */
  const k = $derived(vb.w / Math.max(1, svgW))

  const byId = $derived(new Map((data?.nodes ?? []).map((n) => [n.id, n])))
  const selNode = $derived(selectedId ? byId.get(selectedId) : undefined)
  const selIso = $derived(selectedId && !selNode ? data?.isolated.find((i) => i.id === selectedId) : undefined)
  const neighbors = $derived(data && selectedId ? neighborsOf(data.edges, selectedId) : [])
  const neighborSet = $derived(new Set(neighbors))
  const cuts = $derived(data ? listCuts(data) : [])
  const hubs = $derived(data ? listHubs(data) : [])
  const needsHelp = $derived(data ? needsNeighborInfoHelp(data) : false)
  const radios = $derived(app.radios.filter((r) => r.state === 'connected' && r.my_node_id))
  const showAllLabels = $derived((data?.nodes.length ?? 0) <= 60)
  const nameOf = (id: string): string => byId.get(id)?.name ?? data?.isolated.find((i) => i.id === id)?.name ?? id

  const edgeClass = (e: TopologyEdge) => snrClass(e.snr)
  const edgeDash = (e: TopologyEdge): string | undefined => {
    if (e.sources.includes('neighborinfo') || e.sources.includes('rf_direct')) return undefined
    return e.sources.includes('traceroute') ? `${6 * k} ${4 * k}` : `${1.5 * k} ${4 * k}`
  }
  const incident = (e: TopologyEdge) => selectedId !== null && (e.a === selectedId || e.b === selectedId)

  // Trascinamento (pan) e rotellina (zoom): nessun gesto e' obbligatorio, ci sono i pulsanti
  let drag: { x: number; y: number; moved: boolean } | null = null
  function clientToSvg(cx: number, cy: number): { x: number; y: number } {
    const r = svgEl!.getBoundingClientRect()
    return { x: vb.x + ((cx - r.left) / r.width) * vb.w, y: vb.y + ((cy - r.top) / r.height) * vb.h }
  }
  function onpointerdown(e: PointerEvent) {
    drag = { x: e.clientX, y: e.clientY, moved: false }
  }
  function onpointermove(e: PointerEvent) {
    if (!drag || !(e.buttons & 1)) return
    const dx = e.clientX - drag.x
    const dy = e.clientY - drag.y
    if (!drag.moved && Math.hypot(dx, dy) < 4) return
    if (!drag.moved) svgEl?.setPointerCapture(e.pointerId)
    drag.moved = true
    drag.x = e.clientX
    drag.y = e.clientY
    userVb = panBy(vb, -dx * k, -dy * k)
  }
  function onpointerup() {
    // il clic sul nodo arriva subito dopo: `drag` si azzera solo in un colpo di coda
    setTimeout(() => (drag = null), 0)
  }
  const dragged = () => drag?.moved === true
  function zoom(factor: number) {
    userVb = zoomAt(vb, factor, vb.x + vb.w / 2, vb.y + vb.h / 2)
  }
  $effect(() => {
    const el = svgEl
    if (!el) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault() // la rotellina zooma il grafo e non scorre la pagina
      const p = clientToSvg(e.clientX, e.clientY)
      userVb = zoomAt(vb, e.deltaY < 0 ? 1.2 : 1 / 1.2, p.x, p.y)
    }
    el.addEventListener('wheel', wheel, { passive: false })
    return () => el.removeEventListener('wheel', wheel)
  })

  function pickNode(id: string) {
    if (dragged()) return
    selectedId = id
  }
  function onnodekey(e: KeyboardEvent, id: string) {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault()
      selectedId = id
    }
  }
</script>

<div class="topo">
  <div class="bar">
    <Segmented items={periodItems} bind:value={periodStr} label={t('topology.periodAria')} />
    <fieldset class="srcs">
      <legend>{t('topology.sources')}</legend>
      {#each SOURCES as s (s)}
        <div class="src">
          <Switch bind:checked={active[s]} label={t(`topology.source.${s}` as MsgKey)} />
          <svg width="28" height="8" aria-hidden="true">
            <line x1="1" y1="4" x2="27" y2="4" stroke="currentColor" stroke-width="3" stroke-linecap="round"
              stroke-dasharray={s === 'traceroute' ? '6 4' : s === 'mqtt_gateway' ? '1.5 5' : undefined} />
          </svg>
        </div>
      {/each}
    </fieldset>
  </div>

  {#if data}
    <p class="stats ui-muted">
      {tn('topology.stats.nodes', data.stats.nodes)} · {tn('topology.stats.edges', data.stats.edges)} ·
      {tn('topology.stats.components', data.stats.components)} · {tn('topology.stats.cut', data.stats.cut)} ·
      {tn('topology.stats.hubs', data.stats.hubs)} · {tn('topology.stats.isolated', data.stats.isolated)}
    </p>
    {#if data.truncated}
      <Banner kind="info" title={t('topology.truncated', { shown: data.nodes.length, total: data.stats.nodes })} />
    {/if}
  {/if}

  {#if chosen.length === 0}
    <Empty icon="info" title={t('topology.noSources')} />
  {:else if error}
    <Banner kind="danger" title={t('topology.error')}>
      {#snippet action()}<Button onclick={() => tick++}>{t('topology.retry')}</Button>{/snippet}
    </Banner>
  {:else if loading && !data}
    <Skeleton tall />
  {:else if data && data.nodes.length === 0}
    <Empty icon="info" title={t('topology.empty')}>
      <p>{t('topology.empty.hint')}</p>
    </Empty>
  {:else if data}
    <div class="main">
      <div class="graph">
        <div class="tools">
          <Button iconOnly icon="plus" label={t('topology.zoomIn')} onclick={() => zoom(1.4)} />
          <Button iconOnly icon="minus" label={t('topology.zoomOut')} onclick={() => zoom(1 / 1.4)} />
          <Button onclick={() => (userVb = null)}>{t('topology.fit')}</Button>
        </div>
        <svg
          bind:this={svgEl}
          bind:clientWidth={svgW}
          viewBox="{vb.x} {vb.y} {vb.w} {vb.h}"
          role="img"
          aria-label={t('topology.aria', { nodes: data.stats.nodes, edges: data.stats.edges, cuts: data.stats.cut })}
          {onpointerdown}
          {onpointermove}
          {onpointerup}
          onpointercancel={onpointerup}
        >
          {#each data.edges as e (e.a + e.b)}
            {@const a = pos.get(e.a)}
            {@const b = pos.get(e.b)}
            {#if a && b}
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                class="edge {edgeClass(e)}"
                class:dim={selectedId !== null && !incident(e)}
                stroke-width={(incident(e) ? 4 : 2) * k}
                stroke-dasharray={edgeDash(e)}
                stroke-linecap="round"
              />
            {/if}
          {/each}
          {#each data.nodes as n (n.id)}
            {@const p = pos.get(n.id)}
            {#if p}
              {@const cls = nodeClass(n)}
              {@const sel = n.id === selectedId}
              {@const near = neighborSet.has(n.id)}
              <g
                class="node {cls}"
                class:mine={n.is_mine}
                class:sel
                class:dim={selectedId !== null && !sel && !near}
                role="button"
                tabindex="0"
                aria-label="{n.name}{n.cut ? `, ${t('topology.cut')}` : ''}{n.hub ? `, ${t('topology.hub')}` : ''}"
                aria-pressed={sel}
                onclick={() => pickNode(n.id)}
                onkeydown={(e) => onnodekey(e, n.id)}
              >
                <circle cx={p.x} cy={p.y} r={22 * k} class="hit" />
                {#if n.cut}<circle cx={p.x} cy={p.y} r={(n.hub ? 10 : 7) * k + 5 * k} class="ring" stroke-width={2 * k} />{/if}
                <circle cx={p.x} cy={p.y} r={(n.hub ? 10 : 7) * k} class="dot" stroke-width={(n.cut ? 3 : 1.5) * k} />
                {#if showAllLabels || n.cut || n.hub || sel || near}
                  <text x={p.x} y={p.y - 14 * k} text-anchor="middle" font-size={14 * k} stroke-width={3 * k}>{n.name}</text>
                {/if}
              </g>
            {/if}
          {/each}
        </svg>
        <ul class="legend ui-muted">
          <li><span class="sw cut"></span>{t('topology.legend.cut')}</li>
          <li><span class="sw hub"></span>{t('topology.legend.hub')}</li>
          <li><span class="sw mine"></span>{t('topology.legend.mine')}</li>
          <li>{t('topology.legend.snr')}</li>
        </ul>
      </div>

      <div class="side">
        {#if selNode}
          <Card>
            <h3>{selNode.name}</h3>
            {#if selNode.role}<p class="ui-muted">{selNode.role}</p>{/if}
            <p>{t('topology.degree', { n: selNode.degree })}</p>
            {#if selNode.cut}
              <p><b>{t('topology.cut')}</b>: {tn('topology.cut.impact', selNode.impact)}</p>
            {/if}
            {#if selNode.hub}<p><b>{t('topology.hub')}</b></p>{/if}
            {#if neighbors.length > 0}
              <div class="h">{t('topology.neighbors')}</div>
              <ul class="rows">
                {#each neighbors as id (id)}
                  <li><button type="button" class="row" onclick={() => (selectedId = id)}>{nameOf(id)}</button></li>
                {/each}
              </ul>
            {/if}
            {#if onpick}<Button onclick={() => onpick(selNode.id)}>{t('topology.details')}</Button>{/if}
          </Card>
        {:else if selIso}
          <Card>
            <h3>{selIso.name}</h3>
            {#if selIso.role}<p class="ui-muted">{selIso.role}</p>{/if}
            <p class="ui-muted">{t('topology.isolated.hint')}</p>
            {#if onpick}<Button onclick={() => onpick(selIso.id)}>{t('topology.details')}</Button>{/if}
          </Card>
        {:else}
          <p class="ui-muted">{t('topology.pick')}</p>
        {/if}
      </div>
    </div>

    <section class="lists">
      <div>
        <h3>{t('topology.list.cuts')}</h3>
        {#if cuts.length === 0}<p class="ui-muted">{t('topology.list.none')}</p>{:else}
          <ul class="rows">
            {#each cuts as n (n.id)}
              <li><button type="button" class="row" onclick={() => (selectedId = n.id)}><span>{n.name}</span><span class="ui-muted">{tn('topology.cut.impact', n.impact)}</span></button></li>
            {/each}
          </ul>
        {/if}
      </div>
      <div>
        <h3>{t('topology.list.hubs')}</h3>
        {#if hubs.length === 0}<p class="ui-muted">{t('topology.list.none')}</p>{:else}
          <ul class="rows">
            {#each hubs as n (n.id)}
              <li><button type="button" class="row" onclick={() => (selectedId = n.id)}><span>{n.name}</span><span class="ui-muted">{t('topology.degree', { n: n.degree })}</span></button></li>
            {/each}
          </ul>
        {/if}
      </div>
      <div>
        <h3>{t('topology.list.isolated')}</h3>
        <p class="ui-muted">{t('topology.isolated.hint')}</p>
        {#if data.isolated.length === 0}<p class="ui-muted">{t('topology.list.none')}</p>{:else}
          <ul class="rows">
            {#each data.isolated.slice(0, 200) as n (n.id)}
              <li><button type="button" class="row" onclick={() => (selectedId = n.id)}>{n.name}</button></li>
            {/each}
          </ul>
        {/if}
      </div>
    </section>
  {/if}

  <Card>
    <details open={needsHelp}>
      <summary>{t('topology.ni.title')}</summary>
      {#if needsHelp}
        <Banner kind="info" title={t('topology.ni.none')} />
      {/if}
      <p>{t('topology.ni.explain')}</p>
      <p>{t('topology.ni.howto')}</p>
      {#if radios.length === 0}
        <p class="ui-muted">{t('topology.ni.noRadio')}</p>
      {:else}
        <div class="btns">
          {#each radios as r (r.id)}
            <Button onclick={() => openConfig(r.my_node_id!, r.id, 'modules')}>{t('topology.ni.enable', { radio: r.name })}</Button>
          {/each}
        </div>
      {/if}
    </details>
  </Card>
</div>

<style>
  .topo {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    padding: var(--space-3);
    color: var(--ink);
    font-size: 14px;
    line-height: 20px;
  }
  .bar {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    align-items: center;
  }
  .srcs {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-4);
    border: 0;
    margin: 0;
    padding: 0;
  }
  .srcs legend {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip-path: inset(50%);
  }
  .src {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    color: var(--ink-muted);
  }
  .stats {
    margin: 0;
  }
  .main {
    display: grid;
    gap: var(--space-3);
    grid-template-columns: minmax(0, 1fr);
  }
  @media (min-width: 900px) {
    .main {
      grid-template-columns: minmax(0, 1fr) 300px;
    }
  }
  .graph {
    position: relative;
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    background: var(--surface);
    overflow: hidden;
  }
  .tools {
    position: absolute;
    top: var(--space-2);
    right: var(--space-2);
    display: flex;
    gap: var(--space-2);
    z-index: 1;
  }
  svg {
    display: block;
    width: 100%;
    aspect-ratio: 1000 / 700;
    touch-action: none;
    cursor: grab;
  }
  .edge {
    stroke: var(--snr-none);
  }
  .edge.good {
    stroke: var(--snr-good);
  }
  .edge.mid {
    stroke: var(--snr-mid);
  }
  .edge.bad {
    stroke: var(--snr-bad);
  }
  .edge.dim,
  .node.dim {
    opacity: 0.25;
  }
  .node {
    cursor: pointer;
  }
  .node .hit {
    fill: transparent;
  }
  .node .dot {
    fill: var(--surface-raised);
    stroke: var(--ink-muted);
  }
  .node.cut .dot {
    stroke: var(--brand-amber);
  }
  .node .ring {
    fill: none;
    stroke: var(--brand-amber);
  }
  .node.mine .dot {
    fill: var(--accent);
  }
  .node.sel .dot {
    stroke: var(--accent);
  }
  .node:focus-visible {
    outline: none;
  }
  .node:focus-visible .dot {
    stroke: var(--focus-ring);
    stroke-width: 4px;
  }
  .node text {
    fill: var(--ink);
    stroke: var(--surface-raised);
    paint-order: stroke;
    pointer-events: none;
  }
  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    list-style: none;
    margin: 0;
    padding: var(--space-2) var(--space-3);
    font-size: 14px;
  }
  .sw {
    display: inline-block;
    width: 12px;
    height: 12px;
    border-radius: 50%;
    margin-right: var(--space-2);
    vertical-align: -1px;
    border: 2px solid var(--ink-muted);
    background: var(--surface-raised);
  }
  .sw.cut {
    border-color: var(--brand-amber);
    border-width: 3px;
  }
  .sw.hub {
    width: 16px;
    height: 16px;
  }
  .sw.mine {
    background: var(--accent);
  }
  h3 {
    font: 600 14px/20px var(--font-sans);
    margin: 0 0 var(--space-2);
  }
  p {
    margin: 0 0 var(--space-2);
  }
  .h {
    color: var(--ink-muted);
    font-size: 12px;
    font-weight: 600;
    margin: var(--space-2) 0 var(--space-1);
  }
  .lists {
    display: grid;
    gap: var(--space-4);
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  }
  .rows {
    list-style: none;
    margin: 0 0 var(--space-2);
    padding: 0;
  }
  .row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--touch-min);
    padding: 0 var(--space-2);
    border: 0;
    border-bottom: 1px solid var(--line);
    background: none;
    color: inherit;
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  .row:hover {
    background: var(--surface-sunken);
  }
  summary {
    min-height: var(--touch-min);
    display: flex;
    align-items: center;
    font-weight: 600;
    cursor: pointer;
  }
  .btns {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
</style>
