<script lang="ts">
  import { onMount } from 'svelte'
  import * as maplibregl from 'maplibre-gl'
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
  import type { Feature, FeatureCollection, Point } from 'geojson'
  import 'maplibre-gl/dist/maplibre-gl.css'
  import { app } from '../lib/stores.svelte'
  import { ageClass } from '../lib/filters'
  import { circlePolygon, precisionRadiusM } from '../lib/geo'
  import type { Node } from '../lib/types'

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
  const STYLE_TIMEOUT_MS = 8000
  const COLORS = { fresh: '#2e9e44', recent: '#e0a800', old: '#8a8a8a' }
  const EMPTY: FeatureCollection = { type: 'FeatureCollection', features: [] }

  let el: HTMLDivElement
  let map: maplibregl.Map | null = null
  let ready = false
  let lastPush = 0
  let timer: ReturnType<typeof setTimeout> | null = null

  const src = (id: string) => map?.getSource(id) as maplibregl.GeoJSONSource | undefined

  function pointFeatures(): Feature[] {
    return nodes
      .filter((n) => n.lat !== null && n.lon !== null)
      .map((n) => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [n.lon!, n.lat!] },
        properties: { id: n.id, age: ageClass(n.last_heard, now) },
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
    map = new maplibregl.Map({ container: el, style: STYLE, center: [12.5, 42.5], zoom: 5, attributionControl: { compact: true } })
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    let loaded = false
    let fellBack = false
    let styleTimer: ReturnType<typeof setTimeout> | null = null

    const setup = (hasGlyphs: boolean) => {
      const m = map!
      m.addSource('nodes', { type: 'geojson', data: EMPTY, cluster: true, clusterMaxZoom: 7, clusterRadius: 40 })
      m.addSource('selected', { type: 'geojson', data: EMPTY })
      m.addSource('precision', { type: 'geojson', data: EMPTY })
      m.addSource('track', { type: 'geojson', data: EMPTY })
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
        id: 'points',
        type: 'circle',
        source: 'nodes',
        filter: ['!', ['has', 'point_count']],
        paint: {
          'circle-color': colorExpr,
          'circle-radius': 6,
          'circle-stroke-width': 1,
          'circle-stroke-color': '#ffffff',
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
      for (const l of ['points', 'clusters']) {
        m.on('mouseenter', l, () => (m.getCanvas().style.cursor = 'pointer'))
        m.on('mouseleave', l, () => (m.getCanvas().style.cursor = ''))
      }
      ready = true
      pushNodes()
      pushSelection()
      pushTrack()
    }

    const fallback = () => {
      if (loaded || fellBack || !map) return
      fellBack = true
      if (styleTimer) clearTimeout(styleTimer)
      map.once('style.load', () => {
        loaded = true
        setup(false)
      })
      map.setStyle(OFFLINE_STYLE)
    }

    map.on('load', () => {
      if (fellBack) return
      loaded = true
      if (styleTimer) clearTimeout(styleTimer)
      setup(true)
    })
    // Offline lo stile non arriva e 'load' non scatta mai: si passa allo stile minimo
    map.on('error', (e) => {
      if ((e as { error?: { url?: string } }).error?.url === STYLE) fallback()
    })
    styleTimer = setTimeout(fallback, STYLE_TIMEOUT_MS)

    return () => {
      if (styleTimer) clearTimeout(styleTimer)
      if (timer) clearTimeout(timer)
      map?.remove()
      map = null
      ready = false
    }
  })

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
