<script module lang="ts">
  // Vista Topologia della pagina Rete (E8). Compare in NetworkPage solo con ready = true.
  export const ready: boolean = true
</script>

<script lang="ts">
  import { onMount, untrack } from 'svelte'
  import { app, openConfig } from '../../lib/stores.svelte'
  import { t, tn } from '../../lib/i18n/index.svelte'
  import type { MsgKey } from '../../lib/i18n/index.svelte'
  import { visibleNodes } from '../../lib/filters'
  import { safeStorage } from '../../lib/storage'
  import { onWsResync } from '../../lib/wsext'
  import {
    DEFAULT_PERIOD, PERIODS, fitViewBox, geoLayout, labelText, layoutAsync, listCuts, listHubs, mainComponentIds, needsNeighborInfoHelp,
    neighborsOf, nodeClass, nodesWithinHops, panBy, pickLabels, snrClass, subgraph, topologyData, topologySignature, zoomAt,
  } from '../../lib/topology'
  import type { LabelItem, Pt, ViewBox } from '../../lib/topology'
  import type { Link, TopologyEdge, TopologyNode, TopologyResult } from '../../lib/types'
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
  const LS_LAYOUT = 'meshlens.topology.layout'
  const LS_MAIN = 'meshlens.topology.main'
  type LayoutMode = 'links' | 'geo'

  const readPref = (key: string): string | null => {
    try {
      return safeStorage().getItem(key)
    } catch {
      return null
    }
  }
  const writePref = (key: string, value: string) => {
    try {
      safeStorage().setItem(key, value)
    } catch {
      // quota o accesso negato: la scelta vale solo per questa sessione
    }
  }

  let periodStr = $state(String(DEFAULT_PERIOD))
  const hours = $derived(Number(periodStr))
  let active = $state<Record<Link['source'], boolean>>({ neighborinfo: true, traceroute: true, mqtt_gateway: true, rf_direct: true })
  let layoutMode = $state<LayoutMode>(readPref(LS_LAYOUT) === 'geo' ? 'geo' : 'links')
  let mainOnly = $state(readPref(LS_MAIN) === '1')
  let data = $state<TopologyResult | null>(null)
  let loading = $state(true)
  let error = $state(false)
  let tick = $state(0)
  let selectedId = $state<string | null>(null)
  let hoverId = $state<string | null>(null)
  let focusId = $state<string | null>(null)
  let hopsStr = $state('2')
  let pickQuery = $state('')
  let userVb = $state<ViewBox | null>(null)
  let svgW = $state(800)
  let svgH = $state(560)
  let winH = $state(900)
  let svgEl: SVGSVGElement | undefined = $state()
  let lastParamKey = ''

  const chosen = $derived(SOURCES.filter((s) => active[s]))
  const periodItems = $derived(PERIODS.map((h) => ({ value: String(h), label: t(PERIOD_KEYS[h]) })))
  const layoutItems = $derived([
    { value: 'links' as LayoutMode, label: t('topology.layout.links') },
    { value: 'geo' as LayoutMode, label: t('topology.layout.geo') },
  ])
  const hopsItems = $derived(['1', '2', '3'].map((h) => ({ value: h, label: t(`topology.focus.hops.${h}` as MsgKey) })))
  const hops = $derived(Number(hopsStr))

  $effect(() => {
    const h = hours
    const srcs = chosen
    const main = mainOnly
    const countries = [...app.filter.countries]
    const paramKey = `${h}|${srcs.join(',')}|${countries.join(',')}|${main}`
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
    topologyData({ hours: h, sources: srcs, countries, main })
      .then((r) => {
        if (stale) return
        // pan/zoom dell'utente azzerati solo se cambiano i parametri, non a un semplice refresh
        if (paramKey !== lastParamKey) userVb = null
        lastParamKey = paramKey
        data = r
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

  // ---- grafo mostrato: gruppo principale e messa a fuoco ----
  const focusMissing = $derived(focusId !== null && data !== null && !data.nodes.some((n) => n.id === focusId))
  const shown = $derived.by((): { nodes: TopologyNode[]; edges: TopologyEdge[] } => {
    if (!data) return { nodes: [], edges: [] }
    let g = { nodes: data.nodes, edges: data.edges }
    if (mainOnly) g = subgraph(g.nodes, g.edges, mainComponentIds(g.nodes, g.edges))
    if (focusId !== null && g.nodes.some((n) => n.id === focusId)) g = subgraph(g.nodes, g.edges, nodesWithinHops(g.edges, focusId, hops))
    return g
  })
  const shownSig = $derived(topologySignature(shown))
  const adjacency = $derived.by(() => {
    const m = new Map<string, string[]>()
    for (const e of shown.edges) {
      ;(m.get(e.a) ?? m.set(e.a, []).get(e.a)!).push(e.b)
      ;(m.get(e.b) ?? m.set(e.b, []).get(e.b)!).push(e.a)
    }
    return m
  })

  // ---- posizioni ----
  // Geografica: calcolo immediato. Per collegamenti: layout a blocchi (rAF) senza bloccare il thread;
  // riparte solo se nodi/archi mostrati sono cambiati e usa come seme le posizioni precedenti.
  const geoPos = $derived(layoutMode === 'geo' ? geoLayout(shown.nodes, shown.edges, 1600, 30) : null)
  let forcePos = $state<Map<string, Pt>>(new Map())
  let layoutSig = ''
  $effect(() => {
    const sg = shownSig
    const g = shown
    const skip = geoPos !== null
    if (!data) {
      forcePos = new Map()
      layoutSig = ''
      return
    }
    if (skip || sg === layoutSig) return
    let stale = false
    const seeds = untrack(() => forcePos)
    layoutAsync(g.nodes, g.edges, { seeds }, () => stale).then((r) => {
      if (stale || !r) return
      layoutSig = sg
      forcePos = r
    })
    return () => {
      stale = true
    }
  })
  const pos = $derived(geoPos ?? forcePos)
  const geoMissing = $derived(layoutMode === 'geo' && geoPos === null && shown.nodes.length > 0)

  const canvasH = $derived(Math.round(Math.min(Math.max(500, winH * 0.75), Math.max(500, 380 + shown.nodes.length * 1.4))))
  const aspect = $derived(svgW / Math.max(1, svgH))
  const fitted = $derived.by(() => {
    const pts: Pt[] = []
    for (const n of shown.nodes) {
      const p = pos.get(n.id)
      if (p) pts.push(p)
    }
    const raw = fitViewBox(pts, 0, aspect)
    return fitViewBox(pts, 24 + 0.03 * Math.max(raw.w, raw.h), aspect)
  })
  const vb = $derived(userVb ?? fitted)
  /** Unita' del grafo per pixel: dimensioni (cerchi, testo, tratti) costanti sullo schermo a ogni zoom. */
  const k = $derived(vb.w / Math.max(1, svgW))
  const zoomLevel = $derived(fitted.w / vb.w)

  const byId = $derived(new Map((data?.nodes ?? []).map((n) => [n.id, n])))
  const selNode = $derived(selectedId ? byId.get(selectedId) : undefined)
  const selIso = $derived(selectedId && !selNode ? data?.isolated.find((i) => i.id === selectedId) : undefined)
  const neighbors = $derived(data && selectedId ? neighborsOf(data.edges, selectedId) : [])
  const neighborSet = $derived(new Set(neighbors))
  const cuts = $derived(data ? listCuts(data) : [])
  const hubs = $derived(data ? listHubs(data) : [])
  const needsHelp = $derived(data ? needsNeighborInfoHelp(data) : false)
  const radios = $derived(app.radios.filter((r) => r.state === 'connected' && r.my_node_id))
  const nameOf = (id: string): string => byId.get(id)?.name ?? data?.isolated.find((i) => i.id === id)?.name ?? id
  const allShown = $derived([...shown.nodes].sort((a, b) => a.name.localeCompare(b.name)))
  const truncTotal = $derived(data ? (mainOnly ? (data.components[0]?.size ?? data.stats.nodes) : data.stats.nodes) : 0)

  // ---- etichette: solo dove servono, senza sovrapposizioni (calcolo in pixel dello schermo, al massimo a ogni frame) ----
  const nearLabels = $derived.by(() => {
    const s = new Set<string>()
    for (const id of [hoverId, selectedId]) if (id !== null) for (const v of adjacency.get(id) ?? []) s.add(v)
    return s
  })
  const mainLabels = $derived(new Set([hoverId, selectedId].filter((x): x is string => x !== null)))
  let labelVb = $state<ViewBox>({ x: 0, y: 0, w: 1, h: 1 })
  let labelRaf = 0
  $effect(() => {
    void vb
    if (labelRaf) return
    labelRaf = requestAnimationFrame(() => {
      labelRaf = 0
      labelVb = vb // sempre l'ultimo valore: piu' cambi nello stesso frame contano come uno
    })
  })
  $effect(() => () => labelRaf && cancelAnimationFrame(labelRaf))
  let measureCtx: CanvasRenderingContext2D | null | undefined
  const measure = (text: string): number => {
    if (measureCtx === undefined) {
      measureCtx = typeof document === 'undefined' ? null : document.createElement('canvas').getContext('2d')
      if (measureCtx) measureCtx.font = `13px ${svgEl ? getComputedStyle(svgEl).fontFamily : 'sans-serif'}`
    }
    return measureCtx ? measureCtx.measureText(text).width : text.length * 7.5
  }
  const nodeR = (n: TopologyNode): number => (n.hub ? 8 : n.cut ? 6 : 4.5) + (n.cut ? 4 : 0)
  const labels = $derived.by(() => {
    const v = labelVb.w > 1 ? labelVb : vb
    const lk = v.w / Math.max(1, svgW)
    const margin = 60 * lk
    const items: LabelItem[] = []
    for (const n of shown.nodes) {
      const p = pos.get(n.id)
      if (!p || p.x < v.x - margin || p.x > v.x + v.w + margin || p.y < v.y - margin || p.y > v.y + v.h + margin) continue
      items.push({ id: n.id, name: n.name, x: p.x, y: p.y, cut: n.cut, hub: n.hub, impact: n.impact, degree: n.degree, r: nodeR(n) })
    }
    const showAll = shown.nodes.length <= 40 || fitted.w / v.w >= 2.5
    return pickLabels(items, { k: lk, forced: mainLabels, near: nearLabels, showAll, measure })
  })
  const dimOthers = $derived(selectedId !== null || hoverId !== null)
  const lit = $derived(selectedId !== null ? neighborSet : hoverId !== null ? new Set(adjacency.get(hoverId) ?? []) : new Set<string>())
  const litId = $derived(selectedId ?? hoverId)

  const edgeClass = (e: TopologyEdge) => snrClass(e.snr)
  const edgeDash = (e: TopologyEdge): string | undefined => {
    if (e.sources.includes('neighborinfo') || e.sources.includes('rf_direct')) return undefined
    return e.sources.includes('traceroute') ? `${6 * k} ${4 * k}` : `${1.5 * k} ${4 * k}`
  }
  const incident = (e: TopologyEdge) => litId !== null && (e.a === litId || e.b === litId)

  // ---- messa a fuoco ----
  const candidates = $derived.by(() => {
    if (!data) return []
    const vis = new Set(visibleNodes(app.nodes.values()).map((n) => n.id))
    return data.nodes.filter((n) => vis.has(n.id) || !app.nodes.has(n.id))
  })
  const matches = $derived.by(() => {
    const q = pickQuery.trim().toLowerCase()
    if (q.length === 0) return []
    return candidates
      .filter((n) => n.name.toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
      .sort((a, b) => b.degree - a.degree || a.name.localeCompare(b.name))
      .slice(0, 8)
  })
  function focusOn(id: string) {
    focusId = id
    selectedId = id
    pickQuery = ''
    userVb = null
  }
  function clearFocus() {
    focusId = null
    userVb = null
  }
  const focusName = $derived(focusId ? nameOf(focusId) : '')

  function setLayout(m: LayoutMode) {
    layoutMode = m
    writePref(LS_LAYOUT, m)
    userVb = null
  }
  function setMain(on: boolean) {
    writePref(LS_MAIN, on ? '1' : '0')
    userVb = null
  }

  // ---- pan (trascinamento), pizzico e rotellina: nessun gesto e' obbligatorio, ci sono i pulsanti ----
  const ptrs = new Map<number, { x: number; y: number }>()
  let drag: { moved: boolean } | null = null
  let pinch: { dist: number } | null = null
  const zoomLimits = () => [fitted.w / 80, fitted.w * 4] as const
  function clientToSvg(cx: number, cy: number): { x: number; y: number } {
    const r = svgEl!.getBoundingClientRect()
    return { x: vb.x + ((cx - r.left) / r.width) * vb.w, y: vb.y + ((cy - r.top) / r.height) * vb.h }
  }
  function onpointerdown(e: PointerEvent) {
    ptrs.set(e.pointerId, { x: e.clientX, y: e.clientY })
    if (ptrs.size === 1) drag = { moved: false }
    else if (ptrs.size === 2) {
      const [a, b] = [...ptrs.values()]
      pinch = { dist: Math.hypot(a.x - b.x, a.y - b.y) }
      drag = { moved: true } // il pizzico non e' un clic
    }
  }
  function onpointermove(e: PointerEvent) {
    const prev = ptrs.get(e.pointerId)
    if (!prev) return
    const cur = { x: e.clientX, y: e.clientY }
    ptrs.set(e.pointerId, cur)
    if (ptrs.size === 2 && pinch) {
      const [a, b] = [...ptrs.values()]
      const dist = Math.hypot(a.x - b.x, a.y - b.y)
      if (pinch.dist > 0 && dist > 0) {
        const c = clientToSvg((a.x + b.x) / 2, (a.y + b.y) / 2)
        const [mn, mx] = zoomLimits()
        userVb = zoomAt(vb, dist / pinch.dist, c.x, c.y, mn, mx)
      }
      pinch.dist = dist
      return
    }
    if (!drag || !(e.buttons & 1) || ptrs.size !== 1) return
    const dx = cur.x - prev.x
    const dy = cur.y - prev.y
    if (!drag.moved && Math.hypot(dx, dy) < 3) {
      ptrs.set(e.pointerId, prev) // somma gli spostamenti finche' non superano la soglia
      return
    }
    if (!drag.moved) svgEl?.setPointerCapture(e.pointerId)
    drag.moved = true
    userVb = panBy(vb, -dx * k, -dy * k)
  }
  function onpointerup(e: PointerEvent) {
    ptrs.delete(e.pointerId)
    if (ptrs.size < 2) pinch = null
    // il clic sul nodo arriva subito dopo: `drag` si azzera solo in un colpo di coda
    if (ptrs.size === 0) setTimeout(() => (drag = null), 0)
  }
  const dragged = () => drag?.moved === true
  function zoom(factor: number) {
    const [mn, mx] = zoomLimits()
    userVb = zoomAt(vb, factor, vb.x + vb.w / 2, vb.y + vb.h / 2, mn, mx)
  }
  $effect(() => {
    const el = svgEl
    if (!el) return
    const wheel = (e: WheelEvent) => {
      e.preventDefault() // la rotellina zooma il grafo e non scorre la pagina
      const p = clientToSvg(e.clientX, e.clientY)
      const [mn, mx] = zoomLimits()
      userVb = zoomAt(vb, e.deltaY < 0 ? 1.2 : 1 / 1.2, p.x, p.y, mn, mx)
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

<svelte:window bind:innerHeight={winH} />

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
  <div class="bar">
    <div class="lay">
      <span class="lbl" id="topo-layout-lbl">{t('topology.layout.label')}</span>
      <Segmented items={layoutItems} value={layoutMode} label={t('topology.layout.label')} onchange={setLayout} />
    </div>
    <div title={t('topology.main.hint')}>
      <Switch bind:checked={mainOnly} label={t('topology.main.label')} onchange={setMain} />
    </div>
  </div>

  {#if data}
    <p class="stats ui-muted">
      {tn('topology.stats.nodes', data.stats.nodes)} · {tn('topology.stats.edges', data.stats.edges)} ·
      {tn('topology.stats.components', data.stats.components)} · {tn('topology.stats.cut', data.stats.cut)} ·
      {tn('topology.stats.hubs', data.stats.hubs)} · {tn('topology.stats.isolated', data.stats.isolated)}
    </p>
    {#if data.truncated}
      <Banner kind="info" title={t('topology.truncated', { shown: data.nodes.length, total: truncTotal })} />
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
    <section class="focus" aria-label={t('topology.focus.title')}>
      {#if focusId !== null && !focusMissing}
        <div class="focus-on">
          <span>{t('topology.focus.active', { name: focusName, shown: shown.nodes.length, n: hops })}</span>
          <Segmented items={hopsItems} bind:value={hopsStr} label={t('topology.focus.hopsAria')} />
          <Button onclick={clearFocus}>{t('topology.focus.clear')}</Button>
        </div>
      {:else}
        <div class="focus-pick">
          <label class="lbl" for="topo-focus-q">{t('topology.focus.title')}</label>
          <input id="topo-focus-q" class="ui-input" type="search" autocomplete="off" placeholder={t('topology.focus.search')}
            bind:value={pickQuery} />
          <Segmented items={hopsItems} bind:value={hopsStr} label={t('topology.focus.hopsAria')} />
        </div>
        {#if focusMissing}<p class="ui-muted">{t('topology.focus.gone')}</p>{/if}
        {#if pickQuery.trim().length > 0}
          {#if matches.length === 0}
            <p class="ui-muted">{t('topology.focus.none')}</p>
          {:else}
            <ul class="rows sugg">
              {#each matches as n (n.id)}
                <li><button type="button" class="row" onclick={() => focusOn(n.id)}><span>{n.name}</span><span class="ui-muted">{n.id}</span></button></li>
              {/each}
            </ul>
          {/if}
        {/if}
      {/if}
    </section>

    {#if geoMissing}
      <p class="ui-muted">{t('topology.layout.geoNone')}</p>
    {:else if layoutMode === 'geo'}
      <p class="ui-muted">{t('topology.layout.geoNote')}</p>
    {/if}

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
          bind:clientHeight={svgH}
          style="height: {canvasH}px"
          viewBox="{vb.x} {vb.y} {vb.w} {vb.h}"
          role="img"
          aria-label={t('topology.aria', { nodes: shown.nodes.length, edges: shown.edges.length, cuts: shown.nodes.filter((n) => n.cut).length })}
          {onpointerdown}
          {onpointermove}
          {onpointerup}
          onpointercancel={onpointerup}
        >
          {#each shown.edges as e (e.a + e.b)}
            {@const a = pos.get(e.a)}
            {@const b = pos.get(e.b)}
            {#if a && b}
              <line
                x1={a.x} y1={a.y} x2={b.x} y2={b.y}
                class="edge {edgeClass(e)}"
                class:dim={dimOthers && !incident(e)}
                stroke-width={(incident(e) ? 3 : 1.4) * k}
                stroke-dasharray={edgeDash(e)}
                stroke-linecap="round"
              />
            {/if}
          {/each}
          {#each shown.nodes as n (n.id)}
            {@const p = pos.get(n.id)}
            {#if p}
              {@const cls = nodeClass(n)}
              {@const sel = n.id === selectedId}
              {@const near = lit.has(n.id)}
              {@const r = n.hub ? 8 : n.cut ? 6 : 4.5}
              <g
                class="node {cls}"
                class:mine={n.is_mine}
                class:sel
                class:dim={dimOthers && n.id !== litId && !near}
                role="button"
                tabindex={n.cut || n.hub || sel ? 0 : -1}
                aria-label="{n.name}{n.cut ? `, ${t('topology.cut')}` : ''}{n.hub ? `, ${t('topology.hub')}` : ''}"
                aria-pressed={sel}
                onclick={() => pickNode(n.id)}
                onkeydown={(e) => onnodekey(e, n.id)}
                onpointerenter={(e) => e.pointerType === 'mouse' && (hoverId = n.id)}
                onpointerleave={() => (hoverId = null)}
                onfocus={() => (hoverId = n.id)}
                onblur={() => (hoverId = null)}
              >
                <circle cx={p.x} cy={p.y} r={Math.max(r + 4, 10) * k} class="hit" />
                {#if n.cut}<circle cx={p.x} cy={p.y} r={(r + 4) * k} class="ring" stroke-width={1.6 * k} />{/if}
                <circle cx={p.x} cy={p.y} r={r * k} class="dot" stroke-width={(n.cut ? 2.4 : 1.4) * k} />
              </g>
            {/if}
          {/each}
          {#each shown.nodes as n (n.id)}
            {@const p = pos.get(n.id)}
            {#if p && labels.has(n.id)}
              {@const pl = labels.get(n.id)!}
              <text class="lbl-t" x={pl.x} y={pl.y} text-anchor={pl.anchor} font-size={13 * k} stroke-width={3 * k}>{labelText(n.name)}</text>
            {/if}
          {/each}
        </svg>
        <ul class="legend ui-muted">
          <li><span class="sw cut"></span>{t('topology.legend.cut')}</li>
          <li><span class="sw hub"></span>{t('topology.legend.hub')}</li>
          <li><span class="sw mine"></span>{t('topology.legend.mine')}</li>
          <li>{t('topology.legend.snr')}</li>
        </ul>
        <p class="ui-muted hint">{t('topology.labels.hint')} {t('topology.hint.interact')}</p>
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
            <div class="btns">
              {#if focusId !== selNode.id}
                <Button onclick={() => focusOn(selNode.id)}>{t('topology.focus.apply')}</Button>
              {:else}
                <Button onclick={clearFocus}>{t('topology.focus.clear')}</Button>
              {/if}
              {#if onpick}<Button onclick={() => onpick(selNode.id)}>{t('topology.details')}</Button>{/if}
            </div>
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

    <Card>
      <details>
        <summary>{t('topology.list.all', { n: allShown.length })}</summary>
        <ul class="rows">
          {#each allShown as n (n.id)}
            <li><button type="button" class="row" onclick={() => (selectedId = n.id)}><span>{n.name}</span><span class="ui-muted">{t('topology.degree', { n: n.degree })}</span></button></li>
          {/each}
        </ul>
      </details>
    </Card>
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
    display: flex;
    justify-content: flex-end;
    gap: var(--space-2);
    padding: var(--space-2);
    border-bottom: 1px solid var(--line);
  }
  .graph > svg {
    display: block;
    width: 100%;
    min-height: 500px;
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
  .lbl-t {
    fill: var(--ink);
    stroke: var(--surface-raised);
    paint-order: stroke;
    pointer-events: none;
  }
  .lay {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
  }
  .lbl {
    color: var(--ink-muted);
    font-size: 12px;
    font-weight: 600;
  }
  .focus {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .focus-pick,
  .focus-on {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
  }
  .focus-pick .ui-input {
    flex: 1 1 220px;
    width: auto;
    max-width: 360px;
  }
  .sugg {
    max-width: 480px;
  }
  .hint {
    margin: 0;
    padding: 0 var(--space-3) var(--space-2);
    font-size: 12px;
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
