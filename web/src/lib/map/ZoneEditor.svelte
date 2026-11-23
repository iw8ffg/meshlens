<script lang="ts">
  // Editor di una zona poligonale sulla mappa, per le regole di avviso «geofence» (WP2).
  // Poligono come coppie [lon, lat], chiuso implicitamente, da 3 a 64 punti. Props fissate dal
  // contratto §10.2: `value` (bindable) e `onchange`. Il componente non scrive nulla da solo:
  // emette il poligono valido, oppure null mentre la zona e' incompleta o non valida.
  // Mappa propria (non riusa MapView): stile online ricolorato se risponde entro 8 s, altrimenti
  // sfondo a tinta unita con un avviso. Nessuna chiamata di rete oltre allo stile.
  import { onMount, untrack } from 'svelte'
  import * as maplibregl from 'maplibre-gl'
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
  import 'maplibre-gl/dist/maplibre-gl.css'
  import { app } from '../stores.svelte'
  import { getJSON } from '../api'
  import { getTheme } from '../theme'
  import { offlineStyle } from '../mapstyle'
  import type { StyleInfo } from '../mapstyle'
  import type { AppSettings } from '../settings'
  import { t, tn } from '../i18n/index.svelte'
  import { visibleNodes } from '../filters'
  import { EMPTY } from './NodeLayer'
  import { recolorLiberty } from './basemap'
  import { readDocumentTokens } from './tokens'
  import type { MapTokens } from './tokens'
  import { ZONE_MAX, ZONE_MIN, addVertex, moveVertex, removeVertex, zoneBasemap, zoneBounds, zoneError, zoneGeoJSON } from './zone'
  import type { ZonePoint } from './zone'
  import Banner from '../ui/Banner.svelte'
  import Button from '../ui/Button.svelte'

  let {
    value = $bindable<[number, number][] | null>(null),
    onchange,
  }: { value?: [number, number][] | null; onchange?: (polygon: [number, number][] | null) => void } = $props()

  const STYLE = 'https://tiles.openfreemap.org/styles/liberty'
  const ONLINE_TIMEOUT_MS = 8000
  const MAX_NODE_DOTS = 3000

  let el: HTMLDivElement
  let map: maplibregl.Map | null = null
  let ready = false
  let pts = $state<ZonePoint[]>(value ? value.map((p) => [p[0], p[1]] as ZonePoint) : [])
  let lastEmitted: [number, number][] | null = value
  let noBasemap = $state(false)
  const err = $derived(pts.length === 0 ? null : zoneError(pts))

  const round = (n: number) => Math.round(n * 1e6) / 1e6
  const src = (id: string) => map?.getSource(id) as maplibregl.GeoJSONSource | undefined

  /** Applica la zona: la emette solo se e' valida, altrimenti emette null. */
  function commit(next: ZonePoint[]) {
    pts = next
    const out = next.length >= ZONE_MIN && zoneError(next) === null ? next : null
    lastEmitted = out
    value = out
    onchange?.(out)
  }

  // Cambio dall'esterno (il genitore rimpiazza il poligono): si riallinea la bozza
  $effect(() => {
    const v = value
    if (v === lastEmitted) return
    untrack(() => {
      pts = v ? v.map((p) => [p[0], p[1]] as ZonePoint) : []
      lastEmitted = v
      if (ready) fit()
    })
  })

  const fallbackStyle = (tk: MapTokens): maplibregl.StyleSpecification => ({
    version: 8,
    sources: {},
    layers: [{ id: 'bg', type: 'background', paint: { 'background-color': tk.land } }],
  })

  function setupLayers() {
    const m = map
    if (!m || m.getSource('zone')) return
    const tk = readDocumentTokens()
    m.addSource('zone-nodes', { type: 'geojson', data: EMPTY })
    m.addSource('zone', { type: 'geojson', data: EMPTY })
    m.addLayer({ id: 'zone-nodes', type: 'circle', source: 'zone-nodes', paint: { 'circle-radius': 3, 'circle-color': tk.inkMuted, 'circle-opacity': 0.7 } })
    m.addLayer({ id: 'zone-fill', type: 'fill', source: 'zone', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': tk.amber, 'fill-opacity': 0.2 } })
    m.addLayer({ id: 'zone-line', type: 'line', source: 'zone', filter: ['!=', ['geometry-type'], 'Point'], paint: { 'line-color': tk.amber, 'line-width': 2.5 } })
    m.addLayer({
      id: 'zone-pts',
      type: 'circle',
      source: 'zone',
      filter: ['==', ['geometry-type'], 'Point'],
      paint: { 'circle-radius': 10, 'circle-color': tk.amber, 'circle-stroke-color': tk.outline, 'circle-stroke-width': 2 },
    })
    ready = true
    push()
    pushNodes()
  }

  function push() {
    if (!ready) return
    src('zone')?.setData(zoneGeoJSON(pts))
  }
  function pushNodes() {
    const feats = visibleNodes(app.nodes.values())
      .filter((n) => n.lat !== null && n.lon !== null)
      .slice(0, MAX_NODE_DOTS)
      .map((n) => ({ type: 'Feature' as const, geometry: { type: 'Point' as const, coordinates: [n.lon!, n.lat!] }, properties: {} }))
    src('zone-nodes')?.setData({ type: 'FeatureCollection', features: feats })
  }

  function fit() {
    if (!map) return
    const b = zoneBounds(pts)
    if (b) {
      map.fitBounds(b, { padding: 40, maxZoom: 14, duration: 0 })
      return
    }
    const pos = visibleNodes(app.nodes.values()).filter((n) => n.lat !== null && n.lon !== null)
    if (pos.length === 0) return
    const bb = new maplibregl.LngLatBounds([pos[0].lon!, pos[0].lat!], [pos[0].lon!, pos[0].lat!])
    for (const n of pos) bb.extend([n.lon!, n.lat!])
    map.fitBounds(bb, { padding: 40, maxZoom: 12, duration: 0 })
  }

  /** Aggiunge un vertice al centro della mappa (muovendo la mappa con la tastiera si sceglie il punto). */
  function addAtCenter() {
    if (!map) return
    const c = map.getCenter()
    commit(addVertex(pts, [round(c.lng), round(c.lat)]))
  }

  $effect(() => {
    void pts
    push()
  })
  $effect(() => {
    void app.nodes
    untrack(pushNodes)
  })

  onMount(() => {
    maplibregl.setWorkerUrl(workerUrl)
    let disposed = false
    const ctl = new AbortController()
    const tk = readDocumentTokens()
    const themeCtl = getTheme()
    let theme = themeCtl.theme()
    let styleJson: maplibregl.StyleSpecification | null = null
    let info: StyleInfo = { has_offline: false, maxzoom: 14, bounds: null }
    let kind: 'online' | 'offline' | 'fallback' = 'fallback'
    map = new maplibregl.Map({ container: el, style: fallbackStyle(tk), center: [12.5, 42.5], zoom: 5, attributionControl: { compact: true }, fadeDuration: 0 })
    const m = map
    m.on('style.load', setupLayers)
    m.on('load', fit)

    const styleOf = (k: typeof kind): maplibregl.StyleSpecification => {
      const tokens = readDocumentTokens()
      if (k === 'online' && styleJson) return recolorLiberty(styleJson, tokens)
      if (k === 'offline') return offlineStyle(info, theme, tokens)
      return fallbackStyle(tokens)
    }
    const apply = (k: typeof kind) => {
      kind = k
      ready = false
      m.setStyle(styleOf(k), { diff: false }) // style.load ricrea i livelli della zona
    }

    // Stesso criterio di MapView: map_mode "offline" non usa mai la rete; online ricolorato se
    // risponde in tempo, altrimenti offline (se ci sono mappe) o sfondo a tinta unita
    const loadBasemap = async () => {
      const [st, inf] = await Promise.all([
        getJSON<AppSettings>('/settings').catch(() => null),
        getJSON<StyleInfo>('/maps/style-info').catch(() => null),
      ])
      if (disposed) return
      if (inf && typeof inf.has_offline === 'boolean') info = { has_offline: inf.has_offline, maxzoom: inf.maxzoom ?? 14, bounds: inf.bounds ?? null }
      const mode = st?.map_mode === 'online' || st?.map_mode === 'offline' || st?.map_mode === 'auto' ? st.map_mode : 'auto'
      const first = zoneBasemap(mode, info.has_offline, navigator.onLine)
      if (first !== 'online') {
        if (first === 'fallback') noBasemap = true
        apply(first)
        return
      }
      const to = setTimeout(() => ctl.abort(), ONLINE_TIMEOUT_MS)
      try {
        const r = await fetch(STYLE, { signal: ctl.signal, cache: 'no-cache' })
        if (!r.ok) throw new Error(String(r.status))
        styleJson = (await r.json()) as maplibregl.StyleSpecification
        if (!disposed) apply('online')
      } catch {
        if (disposed) return
        if (mode !== 'online' && info.has_offline) apply('offline')
        else noBasemap = true
      } finally {
        clearTimeout(to)
      }
    }
    void loadBasemap()
    // cambio di tema: lo stile e i colori dei livelli si rileggono dai token
    const offTheme = themeCtl.subscribe((th) => {
      if (th === theme) return
      theme = th
      apply(kind)
    })

    // vertici: clic aggiunge, trascinamento sposta
    let dragIdx: number | null = null
    let justDragged = false
    const start = (e: maplibregl.MapLayerMouseEvent | maplibregl.MapLayerTouchEvent) => {
      const idx = e.features?.[0]?.properties?.idx
      if (typeof idx !== 'number') return
      e.preventDefault()
      dragIdx = idx
      m.dragPan.disable()
      m.getCanvas().style.cursor = 'grabbing'
    }
    const move = (e: maplibregl.MapMouseEvent | maplibregl.MapTouchEvent) => {
      if (dragIdx === null) return
      pts = moveVertex(pts, dragIdx, [round(e.lngLat.lng), round(e.lngLat.lat)])
    }
    const end = () => {
      if (dragIdx === null) return
      dragIdx = null
      m.dragPan.enable()
      m.getCanvas().style.cursor = ''
      justDragged = true
      setTimeout(() => (justDragged = false), 0)
      commit(pts)
    }
    m.on('mousedown', 'zone-pts', start)
    m.on('touchstart', 'zone-pts', start)
    m.on('mousemove', move)
    m.on('touchmove', move)
    m.on('mouseup', end)
    m.on('touchend', end)
    m.on('mouseenter', 'zone-pts', () => (m.getCanvas().style.cursor = 'grab'))
    m.on('mouseleave', 'zone-pts', () => {
      if (dragIdx === null) m.getCanvas().style.cursor = ''
    })
    m.on('click', (e: maplibregl.MapMouseEvent) => {
      if (justDragged || !ready) return
      if (m.queryRenderedFeatures(e.point, { layers: ['zone-pts'] }).length > 0) return
      commit(addVertex(pts, [round(e.lngLat.lng), round(e.lngLat.lat)]))
    })

    return () => {
      disposed = true
      offTheme()
      ctl.abort()
      m.remove()
      map = null
      ready = false
    }
  })
</script>

<div class="zone">
  <p class="hint ui-muted">{t('layers.zone.hint')}</p>
  {#if noBasemap}
    <Banner kind="info" title={t('layers.zone.noBasemap')} />
  {/if}
  <div class="map" bind:this={el} role="group" aria-label={t('layers.zone.aria')}></div>
  <div class="bar">
    <span class="count">{tn('layers.zone.points', pts.length)}</span>
    <Button onclick={() => commit(pts.slice(0, -1))} disabled={pts.length === 0}>{t('layers.zone.undo')}</Button>
    <Button onclick={() => commit([])} disabled={pts.length === 0}>{t('layers.zone.clear')}</Button>
    <Button onclick={fit}>{t('layers.zone.fit')}</Button>
    <Button onclick={addAtCenter} disabled={pts.length >= ZONE_MAX}>{t('layers.zone.addCenter')}</Button>
  </div>
  {#if pts.length > 0}
    <!-- alternativa da tastiera alla mappa: elenco dei vertici, ognuno rimovibile -->
    <ol class="verts" aria-label={t('layers.zone.list')}>
      {#each pts as p, i (i)}
        <li>
          <span class="ui-mono">{p[1].toFixed(5)}, {p[0].toFixed(5)}</span>
          <Button kind="ghost" iconOnly icon="trash" label={t('layers.zone.remove', { n: i + 1 })} onclick={() => commit(removeVertex(pts, i))} />
        </li>
      {/each}
    </ol>
  {/if}
  {#if err}
    <p class="err" role="status">{t(`layers.zone.err.${err}` as 'layers.zone.err.tooFew')}</p>
  {/if}
</div>

<style>
  .zone {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    font-size: 14px;
    line-height: 20px;
  }
  .hint,
  .err {
    margin: 0;
  }
  .err {
    color: var(--danger);
  }
  .map {
    height: 320px;
    border: 1px solid var(--line);
    border-radius: var(--radius-md);
    overflow: hidden;
  }
  :global(.vp-phone) .map {
    height: 280px;
  }
  .bar {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
  }
  .verts {
    margin: 0;
    padding: 0 0 0 var(--space-5, 20px);
    max-height: 168px;
    overflow: auto;
  }
  .verts li {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
  }
  .count {
    margin-right: auto;
    color: var(--ink-muted);
  }
</style>
