<script lang="ts">
  import { onMount } from 'svelte'
  import * as maplibregl from 'maplibre-gl'
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
  import type { Feature, FeatureCollection, Point } from 'geojson'
  import 'maplibre-gl/dist/maplibre-gl.css'
  import { app } from '../lib/stores.svelte'
  import { ageClass } from '../lib/filters'
  import { circlePolygon, precisionRadiusM } from '../lib/geo'
  import { links as fetchLinks } from '../lib/api'
  import { linksToGeoJSON } from '../lib/links'
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

  onMount(() => {
    maplibregl.setWorkerUrl(workerUrl)
    map = new maplibregl.Map({ container: el, style: navigator.onLine === false ? OFFLINE_STYLE : STYLE, center: [12.5, 42.5], zoom: 5, attributionControl: { compact: true } })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    let inFallback = navigator.onLine === false
    let bound = false

    const setup = (hasGlyphs: boolean) => {
      const m = map!
      if (m.getSource('nodes')) return // gia' montato
      m.addSource('nodes', { type: 'geojson', data: EMPTY, cluster: true, clusterMaxZoom: 7, clusterRadius: 40 })
      m.addSource('selected', { type: 'geojson', data: EMPTY })
      m.addSource('precision', { type: 'geojson', data: EMPTY })
      m.addSource('track', { type: 'geojson', data: EMPTY })
      m.addSource('links', { type: 'geojson', data: EMPTY })
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
      if (!bound) {
        bound = true
      m.on('click', 'points', (e: maplibregl.MapLayerMouseEvent) => {
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
    }

    // Solo se lo stile non e' davvero raggiungibile: niente timeout, il primo caricamento puo' essere lento
    const fallback = () => {
      if (inFallback || ready || !map) return
      inFallback = true
      map.once('style.load', () => setup(false))
      map.setStyle(OFFLINE_STYLE)
    }

    const recover = () => {
      if (!inFallback || !map) return
      inFallback = false
      ready = false
      map.once('style.load', () => setup(true))
      map.setStyle(STYLE)
    }

    map.on('load', () => setup(!inFallback))
    map.on('error', (e) => {
      // errore di rete/HTTP sul JSON dello stile; i 404 di tile e glyph hanno altri URL
      if ((e as { error?: { url?: string } }).error?.url === STYLE) fallback()
    })
    window.addEventListener('online', recover)

    return () => {
      window.removeEventListener('online', recover)
      if (timer) clearTimeout(timer)
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

  function pushLinks() {
    if (!ready) return
    src('links')?.setData(app.filter.links ? linksToGeoJSON(linkList, app.nodes) : EMPTY)
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
    if (focus && map) map.easeTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), 10) })
  })
</script>

<div class="map" bind:this={el}></div>

<style>
  .map {
    position: absolute;
    inset: 0;
  }
</style>
