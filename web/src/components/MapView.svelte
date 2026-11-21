<script lang="ts">
  import { onMount, untrack } from 'svelte'
  import * as maplibregl from 'maplibre-gl'
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
  import type { Feature, FeatureCollection, Point } from 'geojson'
  import 'maplibre-gl/dist/maplibre-gl.css'
  import { app, coverage } from '../lib/stores.svelte'
  import { ageClass } from '../lib/filters'
  import { circlePolygon, formatMeters, precisionRadiusM } from '../lib/geo'
  import { coverageSession, getJSON, links as fetchLinks, patchCoverage } from '../lib/api'
  import { coverageGeoJSON } from '../lib/coverage'
  import { formatDate } from '../lib/format'
  import { linksToGeoJSON } from '../lib/links'
  import { canSwitch, chooseMode, offlineStyle, SWITCH_MIN_MS } from '../lib/mapstyle'
  import type { EffectiveMode, MapMode, StyleInfo } from '../lib/mapstyle'
  import type { AppSettings } from '../lib/settings'
  import type { Link, Node } from '../lib/types'

  let {
    nodes,
    now,
    track,
    focus,
  }: {
    nodes: Node[]
    now: number
    track: [number, number][] | null
    focus: { lat: number; lon: number; seq: number } | null
  } = $props()

  const STYLE = 'https://tiles.openfreemap.org/styles/liberty'
  // Stile minimo usato quando lo stile online non si carica (offline): niente glyphs
  const OFFLINE_STYLE: maplibregl.StyleSpecification = {
    version: 8,
    sources: {},
    layers: [{ id: 'bg', type: 'background', paint: { 'background-color': '#dde3ea' } }],
  }
  const COLORS = { fresh: '#2e9e44', recent: '#e0a800', old: '#8a8a8a' }
  const RF_BORDER = '#1e3a8a'
  const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

  let el: HTMLDivElement
  let map: maplibregl.Map | null = null
  let ready = false
  let lastPush = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let linkList: Link[] = []
  const SOURCE_LABEL: Record<string, string> = { neighborinfo: 'NeighborInfo', traceroute: 'traceroute', rf_direct: 'ricezione diretta' }

  const src = (id: string) => map?.getSource(id) as maplibregl.GeoJSONSource | undefined

  // Fonte per il bordo: solo RF, RF+MQTT (bordo doppio) oppure solo MQTT
  function origin(n: Node): 'rf' | 'both' | 'mqtt' {
    const rf = n.sources.includes('rf')
    const mq = n.sources.some((s) => s !== 'rf')
    return rf && mq ? 'both' : rf ? 'rf' : 'mqtt'
  }

  function pointFeatures(): Feature[] {
    return nodes
      .filter((n) => n.lat !== null && n.lon !== null)
      .map((n) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [n.lon!, n.lat!] },
        properties: { id: n.id, age: ageClass(n.last_heard, now), origin: origin(n) },
      }))
  }

  function pushNodes() {
    timer = null
    lastPush = Date.now()
    src('nodes')?.setData({ type: 'FeatureCollection', features: pointFeatures() })
  }

  // Aggiorna la sorgente al massimo una volta al secondo
  function scheduleNodes() {
    if (!ready || timer) return
    const wait = Math.max(0, 1000 - (Date.now() - lastPush))
    timer = setTimeout(pushNodes, wait)
  }

  function pushSelection() {
    const n = app.selectedId ? app.nodes.get(app.selectedId) : undefined
    const has = n && n.lat !== null && n.lon !== null
    src('selected')?.setData(
      has
        ? {
            type: 'FeatureCollection',
            features: [
              {
                type: 'Feature',
                geometry: { type: 'Point', coordinates: [n.lon!, n.lat!] },
                properties: { age: ageClass(n.last_heard, now) },
              },
            ],
          }
        : EMPTY,
    )
    const r = has ? precisionRadiusM(n.precision_bits) : null
    src('precision')?.setData(
      r !== null
        ? {
            type: 'FeatureCollection',
            features: [
              {
                type: 'Feature',
                geometry: { type: 'Polygon', coordinates: [circlePolygon(n!.lat!, n!.lon!, r)] },
                properties: {},
              },
            ],
          }
        : EMPTY,
    )
  }

  let notice = $state('')
  const NOTICE = 'Mappa non disponibile offline: scaricala da Impostazioni → Mappe offline'
  const ONLINE_TIMEOUT_MS = 8000

  onMount(() => {
    maplibregl.setWorkerUrl(workerUrl)
    let disposed = false
    let bound = false
    let mode: MapMode = 'auto'
    let info: StyleInfo = { has_offline: false, maxzoom: 14, bounds: null }
    let current: EffectiveMode | null = null
    let lastSwitch = 0 // 0: l'avvio non conta come cambio
    let onlineOk = false // stile online precaricato con successo (usato solo con mappe offline presenti)
    let onlineFailed = false // stile online non raggiungibile (usato senza mappe offline)
    let styleJson: maplibregl.StyleSpecification | null = null
    let verifying: AbortController | null = null
    let retryTimer: ReturnType<typeof setTimeout> | null = null

    const setup = (hasGlyphs: boolean) => {
      const m = map!
      if (m.getSource('nodes')) return // gia' montato
      m.addSource('nodes', { type: 'geojson', data: EMPTY, cluster: true, clusterMaxZoom: 7, clusterRadius: 40 })
      m.addSource('selected', { type: 'geojson', data: EMPTY })
      m.addSource('precision', { type: 'geojson', data: EMPTY })
      m.addSource('track', { type: 'geojson', data: EMPTY })
      m.addSource('links', { type: 'geojson', data: EMPTY })
      for (const id of ['cov-track', 'cov-missing', 'cov-points', 'cov-base']) m.addSource(id, { type: 'geojson', data: EMPTY })
      m.addLayer({
        id: 'precision-fill',
        type: 'fill',
        source: 'precision',
        paint: { 'fill-color': '#2563eb', 'fill-opacity': 0.15 },
      })
      m.addLayer({
        id: 'precision-line',
        type: 'line',
        source: 'precision',
        paint: { 'line-color': '#2563eb', 'line-width': 1.5, 'line-dasharray': [2, 2] },
      })
      m.addLayer({
        id: 'track',
        type: 'line',
        source: 'track',
        paint: { 'line-color': '#2563eb', 'line-width': 3 },
      })
      const linkOpacity: maplibregl.ExpressionSpecification = ['interpolate', ['linear'], ['get', 'age_h'], 0, 1, 24, 0.35]
      m.addLayer({
        id: 'links',
        type: 'line',
        source: 'links',
        filter: ['!=', ['get', 'source'], 'traceroute'],
        paint: { 'line-color': ['get', 'color'], 'line-width': 2.5, 'line-opacity': linkOpacity },
      })
      m.addLayer({
        id: 'links-trace',
        type: 'line',
        source: 'links',
        filter: ['==', ['get', 'source'], 'traceroute'],
        paint: { 'line-color': ['get', 'color'], 'line-width': 2.5, 'line-opacity': linkOpacity, 'line-dasharray': [3, 2] },
      })
      m.addLayer({
        id: 'clusters',
        type: 'circle',
        source: 'nodes',
        filter: ['has', 'point_count'],
        paint: {
          'circle-color': '#3b82f6',
          'circle-opacity': 0.8,
          'circle-radius': ['step', ['get', 'point_count'], 14, 20, 18, 100, 24],
        },
      })
      if (hasGlyphs) {
        m.addLayer({
          id: 'cluster-count',
          type: 'symbol',
          source: 'nodes',
          filter: ['has', 'point_count'],
          layout: {
            'text-field': ['get', 'point_count_abbreviated'],
            'text-font': ['Noto Sans Regular'],
            'text-size': 12,
          },
          paint: { 'text-color': '#ffffff' },
        })
      }
      const colorExpr: maplibregl.ExpressionSpecification = [
        'match',
        ['get', 'age'],
        'fresh',
        COLORS.fresh,
        'recent',
        COLORS.recent,
        COLORS.old,
      ]
      m.addLayer({
        id: 'points-ring',
        type: 'circle',
        source: 'nodes',
        filter: ['all', ['!', ['has', 'point_count']], ['==', ['get', 'origin'], 'both']],
        paint: {
          'circle-color': 'rgba(0,0,0,0)',
          'circle-radius': 9.5,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': RF_BORDER,
        },
      })
      m.addLayer({
        id: 'points',
        type: 'circle',
        source: 'nodes',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': colorExpr,
          'circle-radius': 6,
          'circle-stroke-width': ['match', ['get', 'origin'], 'mqtt', 1, 2],
          'circle-stroke-color': ['match', ['get', 'origin'], 'mqtt', '#ffffff', RF_BORDER],
        },
      })
      m.addLayer({
        id: 'selected',
        type: 'circle',
        source: 'selected',
        paint: {
          'circle-color': colorExpr,
          'circle-radius': 11,
          'circle-stroke-width': 3,
          'circle-stroke-color': '#2563eb',
        },
      })
      m.addLayer({
        id: 'cov-track',
        type: 'line',
        source: 'cov-track',
        paint: { 'line-color': '#2563eb', 'line-width': 1.5 },
      })
      m.addLayer({
        id: 'cov-missing',
        type: 'circle',
        source: 'cov-missing',
        paint: {
          'circle-color': 'rgba(0,0,0,0)',
          'circle-radius': 4,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#8a8a8a',
        },
      })
      m.addLayer({
        id: 'cov-points',
        type: 'circle',
        source: 'cov-points',
        paint: {
          'circle-color': ['get', 'color'],
          'circle-radius': 6,
          'circle-stroke-width': 1.5,
          'circle-stroke-color': '#ffffff',
        },
      })
      m.addLayer({
        id: 'cov-base',
        type: 'circle',
        source: 'cov-base',
        paint: {
          'circle-color': '#111827',
          'circle-radius': 9,
          'circle-stroke-width': 3,
          'circle-stroke-color': '#facc15',
        },
      })
      if (!bound) {
        bound = true
        for (const l of ['cov-points', 'cov-missing']) {
          m.on('click', l, (e: maplibregl.MapLayerMouseEvent) => {
            if (picking) return
            const p = e.features?.[0]?.properties
            if (p) showCoveragePopup(e.lngLat, p, l === 'cov-missing')
          })
          m.on('mouseenter', l, () => {
            if (!picking) m.getCanvas().style.cursor = 'pointer'
          })
          m.on('mouseleave', l, () => {
            if (!picking) m.getCanvas().style.cursor = ''
          })
        }
        m.on('click', 'points', (e: maplibregl.MapLayerMouseEvent) => {
          if (picking) return
          const id = e.features?.[0]?.properties?.id
          if (typeof id === 'string') app.selectedId = id
        })
        m.on('click', 'clusters', async (e: maplibregl.MapLayerMouseEvent) => {
          const f = e.features?.[0]
          if (!f) return
          try {
            const zoom = await src('nodes')!.getClusterExpansionZoom(f.properties.cluster_id)
            m.easeTo({ center: (f.geometry as Point).coordinates as [number, number], zoom })
          } catch {
            // cluster scomparso nel frattempo: niente da fare
          }
        })
        for (const l of ['links', 'links-trace']) {
          m.on('click', l, (e: maplibregl.MapLayerMouseEvent) => {
            if (picking) return
            if (m.queryRenderedFeatures(e.point, { layers: ['points', 'clusters'] }).length > 0) return
            const p = e.features?.[0]?.properties
            if (p) showLinkPopup(e.lngLat, p)
          })
        }
        for (const l of ['points', 'clusters', 'links', 'links-trace']) {
          m.on('mouseenter', l, () => (m.getCanvas().style.cursor = 'pointer'))
          m.on('mouseleave', l, () => (m.getCanvas().style.cursor = ''))
        }
      }
      ready = true
      pushNodes()
      pushSelection()
      pushTrack()
      pushLinks()
      pushCoverage()
    }

    const styleFor = (m: EffectiveMode): string | maplibregl.StyleSpecification =>
      m === 'online' ? (styleJson ?? STYLE) : m === 'offline' ? offlineStyle(info) : OFFLINE_STYLE

    const target = (): EffectiveMode => {
      // con mappe offline l'online si usa solo dopo averlo verificato; senza, si prova subito
      const failed = mode === 'auto' && info.has_offline ? !onlineOk : onlineFailed
      return chooseMode(mode, navigator.onLine, info.has_offline, failed)
    }

    const evaluate = () => {
      if (disposed || !map) return
      const t = target()
      notice = t === 'fallback' && !navigator.onLine ? NOTICE : ''
      if (t === current) return
      if (current !== null && !canSwitch(lastSwitch, Date.now())) {
        if (!retryTimer) {
          retryTimer = setTimeout(() => {
            retryTimer = null
            evaluate()
          }, Math.max(0, SWITCH_MIN_MS - (Date.now() - lastSwitch)) + 50)
        }
        return
      }
      if (current !== null) lastSwitch = Date.now()
      current = t
      ready = false
      map.setStyle(styleFor(t), { diff: false }) // style.load ricrea i livelli MeshLens
      notice = t === 'fallback' && !navigator.onLine ? NOTICE : ''
    }

    // Precarica lo stile online: si passa a online solo se si carica davvero entro 8 s
    const verifyOnline = async () => {
      if (disposed || verifying || onlineOk || mode !== 'auto' || !info.has_offline || !navigator.onLine) return
      const ctl = new AbortController()
      verifying = ctl
      const to = setTimeout(() => ctl.abort(), ONLINE_TIMEOUT_MS)
      try {
        const res = await fetch(STYLE, { signal: ctl.signal, cache: 'no-store' })
        if (!res.ok) throw new Error(String(res.status))
        styleJson = (await res.json()) as maplibregl.StyleSpecification
        onlineOk = true
      } catch {
        onlineOk = false
      } finally {
        clearTimeout(to)
        if (verifying === ctl) verifying = null
      }
      evaluate()
    }

    const onOnline = () => {
      onlineFailed = false
      void verifyOnline()
      evaluate()
    }
    const onOffline = () => {
      onlineOk = false
      evaluate()
    }

    const start = async () => {
      const [st, inf] = await Promise.all([
        getJSON<AppSettings>('/settings').catch(() => null),
        getJSON<StyleInfo>('/maps/style-info').catch(() => null), // server senza mappe offline (404): niente offline
      ])
      if (disposed) return
      if (st?.map_mode === 'online' || st?.map_mode === 'offline' || st?.map_mode === 'auto') mode = st.map_mode
      if (inf && typeof inf.has_offline === 'boolean') info = { has_offline: inf.has_offline, maxzoom: inf.maxzoom ?? 14, bounds: inf.bounds ?? null }
      current = target()
      notice = current === 'fallback' && !navigator.onLine ? NOTICE : ''
      map = new maplibregl.Map({ container: el, style: styleFor(current), center: [12.5, 42.5], zoom: 5, attributionControl: { compact: true }, fadeDuration: 0 })
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
      map.on('style.load', () => setup(current !== 'fallback'))
      map.on('error', (e) => {
        // errore di rete/HTTP sul JSON dello stile online; i 404 di tile e glyph hanno altri URL
        if ((e as { error?: { url?: string } }).error?.url === STYLE) {
          onlineFailed = true
          evaluate()
        }
      })
      window.addEventListener('online', onOnline)
      window.addEventListener('offline', onOffline)
      void verifyOnline()
    }
    void start()

    return () => {
      disposed = true
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      verifying?.abort()
      if (retryTimer) clearTimeout(retryTimer)
      if (timer) clearTimeout(timer)
      cancelPick()
      map?.remove()
      map = null
      ready = false
    }
  })

  function nodeName(id: string): string {
    const n = app.nodes.get(id)
    return n?.short_name || n?.long_name || id
  }

  function showLinkPopup(at: maplibregl.LngLat, p: Record<string, unknown>) {
    if (!map) return
    const snr = typeof p.snr === 'number' ? `${String(Math.round(p.snr * 10) / 10).replace('.', ',')} dB` : 'sconosciuto'
    const age = Number(p.age_h)
    const eta = age < 1 ? 'meno di 1 h fa' : `${Math.round(age)} h fa`
    const box = document.createElement('div')
    const title = document.createElement('b')
    title.textContent = `${nodeName(String(p.from_id))} ↔ ${nodeName(String(p.to_id))}`
    box.append(title)
    for (const line of [`SNR: ${snr}`, `Fonte: ${SOURCE_LABEL[String(p.source)] ?? String(p.source)}`, `Visto: ${eta}`]) {
      box.append(document.createElement('br'), line)
    }
    new maplibregl.Popup({ closeButton: true }).setLngLat(at).setDOMContent(box).addTo(map)
  }

  const fmtSnr = (v: unknown) => (typeof v === 'number' ? `${String(Math.round(v * 10) / 10).replace('.', ',')} dB` : 'sconosciuto')

  function showCoveragePopup(at: maplibregl.LngLat, p: Record<string, unknown>, missing: boolean) {
    if (!map) return
    const lines: string[] = missing
      ? ['Pacchetto non ricevuto']
      : [
          `SNR: ${fmtSnr(p.snr)}`,
          `RSSI: ${typeof p.rssi === 'number' ? `${p.rssi} dBm` : 'sconosciuto'}`,
          `Salti: ${typeof p.hops === 'number' ? p.hops : 'sconosciuto'}`,
          `Distanza dalla base: ${typeof p.distance_m === 'number' ? formatMeters(p.distance_m) : 'sconosciuta'}`,
        ]
    const box = document.createElement('div')
    const title = document.createElement('b')
    title.textContent = `${typeof p.seq === 'number' ? `Pacchetto ${p.seq}` : 'Pacchetto'} · ${formatDate(Number(p.time))}`
    box.append(title)
    for (const line of lines) box.append(document.createElement('br'), line)
    new maplibregl.Popup({ closeButton: true }).setLngLat(at).setDOMContent(box).addTo(map)
  }

  // Prova aperta: risultati sulla mappa; all'apertura la vista si adatta ai punti
  let fittedId: number | null = null
  function pushCoverage() {
    if (!ready) return
    const d = coverage.detail
    const g = d ? coverageGeoJSON(d) : null
    src('cov-track')?.setData(g?.track ?? EMPTY)
    src('cov-missing')?.setData(g?.missing ?? EMPTY)
    src('cov-points')?.setData(g?.points ?? EMPTY)
    src('cov-base')?.setData(g?.base ?? EMPTY)
    if (!d || !g) {
      fittedId = null
      return
    }
    if (fittedId === d.id) return
    const coords = [...g.points.features, ...g.missing.features, ...g.base.features].map((f) => f.geometry.coordinates as [number, number])
    for (const f of g.track.features) coords.push(...(f.geometry.coordinates as [number, number][]))
    if (coords.length === 0) return // dettaglio ancora senza punti: riprova al prossimo aggiornamento
    fittedId = d.id
    const b = new maplibregl.LngLatBounds(coords[0], coords[0])
    for (const c of coords) b.extend(c)
    map?.fitBounds(b, { padding: 60, maxZoom: 16, duration: 0 })
  }

  // Scelta della posizione della base: un solo tocco sulla mappa
  let picking = $state(false)
  let pickError = $state('')
  let pickHandler: ((e: maplibregl.MapMouseEvent) => void) | null = null

  function cancelPick() {
    if (pickHandler) map?.off('click', pickHandler)
    pickHandler = null
    picking = false
    if (map) map.getCanvas().style.cursor = ''
  }

  function startPick() {
    if (!map || picking) return
    pickError = ''
    picking = true
    map.getCanvas().style.cursor = 'crosshair'
    pickHandler = async (e) => {
      const id = coverage.openId
      cancelPick()
      if (id === null) return
      const msg = (err: unknown) => (err instanceof Error ? err.message : 'Errore')
      try {
        const s = await patchCoverage(id, { base_lat: e.lngLat.lat, base_lon: e.lngLat.lng })
        const i = coverage.sessions.findIndex((x) => x.id === id)
        if (i >= 0) coverage.sessions[i] = s
      } catch (err) {
        pickError = msg(err)
        return
      }
      try {
        const d = await coverageSession(id)
        if (coverage.openId === id) coverage.detail = d
      } catch {
        pickError = 'Posizione salvata, ricarico non riuscito'
      }
    }
    map.on('click', pickHandler)
  }

  function closeTest() {
    cancelPick()
    pickError = ''
    coverage.openId = null
    coverage.detail = null
  }

  function pushLinks() {
    if (!ready) return
    src('links')?.setData(app.filter.links ? linksToGeoJSON(linkList, new Map(nodes.map((n) => [n.id, n]))) : EMPTY)
  }

  async function loadLinks() {
    try {
      linkList = await fetchLinks(24)
    } catch {
      return // al prossimo giro
    }
    pushLinks()
  }

  function pushTrack() {
    if (!ready) return
    src('track')?.setData(
      track && track.length > 1
        ? { type: 'Feature', geometry: { type: 'LineString', coordinates: track }, properties: {} }
        : EMPTY,
    )
    if (track && track.length > 1) {
      const b = new maplibregl.LngLatBounds(track[0], track[0])
      for (const p of track) b.extend(p)
      map?.fitBounds(b, { padding: 60, maxZoom: 15 })
    }
  }

  $effect(() => {
    void nodes
    void now
    scheduleNodes()
  })
  $effect(() => {
    void app.selectedId
    void app.nodes.get(app.selectedId ?? '')
    if (ready) pushSelection()
  })
  // Collegamenti: caricati solo con l'interruttore acceso, aggiornati ogni 60 s
  $effect(() => {
    if (!app.filter.links) {
      pushLinks()
      return
    }
    void loadLinks()
    const t = setInterval(loadLinks, 60_000)
    return () => clearInterval(t)
  })
  $effect(() => {
    void nodes // le posizioni dei nodi cambiano le estremita' delle linee
    pushLinks()
  })
  $effect(() => {
    void track
    pushTrack()
  })
  $effect(() => {
    void coverage.detail // i punti in diretta arrivano come nuovo oggetto dettaglio
    untrack(pushCoverage)
  })
  $effect(() => {
    if (!coverage.detail) {
      untrack(() => {
        cancelPick()
        pickError = ''
      })
    }
  })
  $effect(() => {
    if (focus && map) map.easeTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), 10) })
  })
</script>

<div class="map" bind:this={el}></div>
{#if notice}<div class="notice">{notice}</div>{/if}
{#if coverage.detail}
  <div class="covbar">
    <div class="row">
      <b>{coverage.detail.name}</b>
      <button onclick={closeTest}>Chiudi prova</button>
    </div>
    {#if coverage.detail.base_lat === null}
      <p>Posizione della base sconosciuta: tocca la mappa per impostarla</p>
    {/if}
    {#if picking}
      <p>Tocca la mappa nel punto in cui si trova la base.</p>
      <button class="ghost" onclick={cancelPick}>Annulla</button>
    {:else}
      <button onclick={startPick}>Imposta posizione base</button>
    {/if}
    {#if pickError}<p class="err">{pickError}</p>{/if}
  </div>
{/if}

<style>
  .covbar {
    position: absolute;
    top: 8px;
    left: 8px;
    z-index: 5;
    max-width: 260px;
    padding: 8px;
    border-radius: 6px;
    background: rgba(17, 24, 39, 0.92);
    color: #f3f4f6;
    font-size: 0.85em;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .covbar p {
    margin: 0;
  }
  .covbar .row {
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
  }
  .covbar .err {
    color: #f87171;
  }
  .covbar button {
    padding: 6px 8px;
    border: 0;
    border-radius: 6px;
    background: #2563eb;
    color: #fff;
    font: inherit;
    cursor: pointer;
  }
  .covbar .ghost {
    background: #374151;
  }
  .notice {
    position: absolute;
    bottom: 28px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 5;
    padding: 6px 10px;
    border-radius: 6px;
    background: rgba(17, 24, 39, 0.92);
    color: #f3f4f6;
    font-size: 0.85em;
  }
  .map {
    position: absolute;
    inset: 0;
  }
</style>
