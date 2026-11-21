<script lang="ts">
  import { mount, onMount, unmount, untrack } from 'svelte'
  import type { ComponentProps } from 'svelte'
  import * as maplibregl from 'maplibre-gl'
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
  import type { Point } from 'geojson'
  import 'maplibre-gl/dist/maplibre-gl.css'
  import { app, coverage, maps, openChat } from '../lib/stores.svelte'
  import { navigate } from '../lib/shell/navigate'
  import { haversineM, myOrigin } from '../lib/distance'
  import { copyText } from '../lib/clipboard'
  import { geopos } from '../lib/geopos.svelte'
  import { bboxFromBounds } from '../lib/maps'
  import { formatMeters } from '../lib/geo'
  import { coverageSession, getJSON, links as fetchLinks, patchCoverage } from '../lib/api'
  import { coverageGeoJSON } from '../lib/coverage'
  import { formatDate, num, signed, timeAgo } from '../lib/format'
  import { hopsLabel } from '../lib/nodes'
  import { linksToGeoJSON } from '../lib/links'
  import { canSwitch, chooseMode, offlineStyle, SWITCH_MIN_MS } from '../lib/mapstyle'
  import type { EffectiveMode, MapMode, StyleInfo } from '../lib/mapstyle'
  import { getTheme } from '../lib/theme'
  import type { Theme } from '../lib/theme'
  import type { AppSettings } from '../lib/settings'
  import type { Link, Node } from '../lib/types'
  import { recolorLiberty } from '../lib/map/basemap'
  import { readDocumentTokens } from '../lib/map/tokens'
  import type { MapTokens } from '../lib/map/tokens'
  import { registerSprites } from '../lib/map/sprites'
  import { addNodeLayers, EMPTY, isFavorite, isMine, nodeFeatures, precisionData, ringKind, selectionData } from '../lib/map/NodeLayer'
  import { addLinkLayers } from '../lib/map/LinkLayer'
  import { addTrackLayer, trackData } from '../lib/map/TrackLayer'
  import { addCoverageLayers } from '../lib/map/CoverageLayer'
  import Legend from '../lib/map/Legend.svelte'
  import MapControls from '../lib/map/MapControls.svelte'
  import NodePopup from '../lib/map/NodePopup.svelte'
  import Icon from '../lib/ui/Icon.svelte'
  import Button from '../lib/ui/Button.svelte'
  import ActiveFilters from './ActiveFilters.svelte'

  let {
    nodes,
    total,
    now,
    track,
    focus,
    onpick,
  }: {
    nodes: Node[]
    /** Numero di nodi in `app.nodes`, prima dei filtri. */
    total: number
    now: number
    track: [number, number][] | null
    focus: { lat: number; lon: number; seq: number } | null
    /** Apre i dettagli di un nodo (pickId di App). */
    onpick: (id: string) => void
  } = $props()

  const STYLE = 'https://tiles.openfreemap.org/styles/liberty'
  // Stile minimo usato quando lo stile online non si carica (offline): niente glyphs
  const fallbackStyle = (t: MapTokens): maplibregl.StyleSpecification => ({
    version: 8,
    sources: {},
    layers: [{ id: 'bg', type: 'background', paint: { 'background-color': t.land } }],
  })

  let el: HTMLDivElement
  let map: maplibregl.Map | null = null
  let ready = false
  let lastPush = 0
  let timer: ReturnType<typeof setTimeout> | null = null
  let linkList: Link[] = []
  let popup: maplibregl.Popup | null = null
  const SOURCE_LABEL: Record<string, string> = { neighborinfo: 'NeighborInfo', traceroute: 'traceroute', rf_direct: 'ricezione diretta', mqtt_gateway: 'gateway MQTT (ricezione diretta)' }

  const src = (id: string) => map?.getSource(id) as maplibregl.GeoJSONSource | undefined

  function pushNodes() {
    timer = null
    lastPush = Date.now()
    src('nodes')?.setData({ type: 'FeatureCollection', features: nodeFeatures(nodes, now) })
  }

  // Aggiorna la sorgente al massimo una volta al secondo
  function scheduleNodes() {
    if (!ready || timer) return
    const wait = Math.max(0, 1000 - (Date.now() - lastPush))
    timer = setTimeout(pushNodes, wait)
  }

  function pushSelection() {
    const n = app.selectedId ? app.nodes.get(app.selectedId) : undefined
    src('selected')?.setData(selectionData(n, now))
    src('precision')?.setData(precisionData(n))
  }

  let notice = $state('')
  let offlineBadge = $state(false)
  // Connessione anticipata al server delle tessere online: solo se la modalita' puo' usare la rete
  function addPreconnect() {
    if (document.head.querySelector('link[data-meshlens-preconnect]')) return
    const l = document.createElement('link')
    l.rel = 'preconnect'
    l.href = new URL(STYLE).origin
    l.crossOrigin = 'anonymous'
    l.dataset.meshlensPreconnect = '1'
    document.head.append(l)
  }
  // Impostato da onMount: rilegge modalita' e stile-info e aggiorna la mappa viva
  let reloadCfg: (() => void) | null = null
  let seenVersion = maps.version
  const NOTICE = 'Mappa non disponibile offline: scaricala da Impostazioni → Mappe offline'
  const NOTICE_ONLINE = 'Mappa online non raggiungibile'
  const BACKOFF_START_MS = 30_000
  const BACKOFF_MAX_MS = 600_000
  const ONLINE_TIMEOUT_MS = 8000

  onMount(() => {
    maplibregl.setWorkerUrl(workerUrl)
    const themeCtl = getTheme()
    let disposed = false
    let bound = false
    let mode: MapMode = 'auto'
    let info: StyleInfo = { has_offline: false, maxzoom: 14, bounds: null }
    let current: EffectiveMode | null = null
    let theme: Theme = themeCtl.theme()
    let appliedTheme: Theme = theme // tema dello stile attualmente sulla mappa
    let lastSwitch = 0 // 0: l'avvio non conta come cambio
    let boot = true // il primo passaggio dallo stile provvisorio a quello online non conta come cambio
    let onlineOk = false // stile online precaricato con successo (usato solo con mappe offline presenti)
    let onlineFailed = false // stile online non raggiungibile (usato senza mappe offline)
    let styleJson: maplibregl.StyleSpecification | null = null // stile OpenFreeMap grezzo, ricolorato per tema
    let stylePromise: Promise<void> | null = null
    let verifying: AbortController | null = null
    let retryTimer: ReturnType<typeof setTimeout> | null = null
    let verifyTimer: ReturnType<typeof setTimeout> | null = null
    let backoff = BACKOFF_START_MS

    const setup = (hasGlyphs: boolean) => {
      const m = map!
      if (m.getSource('nodes')) return // gia' montato
      const tk = readDocumentTokens()
      registerSprites(m, tk)
      // ordine dal basso: collegamenti e traccia, nodi, prova di copertura
      addLinkLayers(m, tk)
      addTrackLayer(m, tk)
      addNodeLayers(m, tk, hasGlyphs)
      addCoverageLayers(m, tk)
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
        for (const l of ['points', 'points-mine', 'points-fav']) {
          m.on('click', l, (e: maplibregl.MapLayerMouseEvent) => {
            if (picking) return
            const id = e.features?.[0]?.properties?.id
            if (typeof id !== 'string') return
            app.selectedId = id
            showNodePopup(e.lngLat, id)
          })
        }
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
        for (const l of ['links', 'links-trace', 'links-gateway']) {
          m.on('click', l, (e: maplibregl.MapLayerMouseEvent) => {
            if (picking) return
            if (m.queryRenderedFeatures(e.point, { layers: ['points', 'points-mine', 'points-fav', 'clusters'] }).length > 0) return
            const p = e.features?.[0]?.properties
            if (p) showLinkPopup(e.lngLat, p)
          })
        }
        for (const l of ['points', 'points-mine', 'points-fav', 'clusters', 'links', 'links-trace', 'links-gateway']) {
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

    const styleFor = (m: EffectiveMode): maplibregl.StyleSpecification => {
      const tk = readDocumentTokens()
      if (m === 'online' && styleJson) return recolorLiberty(styleJson, tk)
      if (m === 'offline') return offlineStyle(info, theme, tk)
      return fallbackStyle(tk)
    }

    const noticeFor = (t: EffectiveMode): string => {
      if (t !== 'fallback') return ''
      if (mode === 'online') return NOTICE_ONLINE
      return mode === 'offline' || !navigator.onLine ? NOTICE : ''
    }

    const fetchStyle = async (signal: AbortSignal): Promise<void> => {
      // no-cache: si rivalida sempre col server (304 se invariato), cosi' una copia in cache
      // non fa credere online la mappa quando la rete e' giu'
      const res = await fetch(STYLE, { signal, cache: 'no-cache' })
      if (!res.ok) throw new Error(String(res.status))
      styleJson = (await res.json()) as maplibregl.StyleSpecification
    }

    // Scarica lo stile online (serve per ricolorarlo); se fallisce, l'online e' dato per non raggiungibile
    const loadStyle = (): Promise<void> => {
      if (stylePromise) return stylePromise
      if (styleJson || disposed) return Promise.resolve()
      const ctl = new AbortController()
      const to = setTimeout(() => ctl.abort(), ONLINE_TIMEOUT_MS)
      stylePromise = fetchStyle(ctl.signal)
        .catch(() => {
          onlineFailed = true
        })
        .finally(() => {
          clearTimeout(to)
          stylePromise = null
        })
      return stylePromise
    }

    const target = (): EffectiveMode => {
      // modalita' forzate: senza risorse si ricade sullo stile di base (livelli MeshLens visibili)
      if (mode === 'offline' && !info.has_offline) return 'fallback'
      if (mode === 'online' && onlineFailed) return 'fallback'
      // con mappe offline l'online si usa solo dopo averlo verificato; senza, si prova subito
      const failed = mode === 'auto' && info.has_offline ? !onlineOk : onlineFailed
      return chooseMode(mode, navigator.onLine, info.has_offline, failed)
    }

    // force: azione dell'utente (modalita', mappa scaricata o eliminata, tema): niente attesa e, se
    // gia' offline, lo stile viene ricreato per rileggere tessere e sorgente
    const evaluate = (force = false) => {
      if (disposed || !map) return
      const t = target()
      notice = noticeFor(t)
      const themeChanged = appliedTheme !== theme
      if (t === current && !themeChanged && !(force && t === 'offline')) return
      if (t === 'online' && !styleJson) {
        // serve lo stile grezzo: lo si scarica e si rivaluta (al piu' una volta: l'esito cambia target() o styleJson)
        void loadStyle().then(() => evaluate(force))
        return
      }
      if (!force && !themeChanged && current !== null && !canSwitch(lastSwitch, Date.now())) {
        if (!retryTimer) {
          retryTimer = setTimeout(() => {
            retryTimer = null
            evaluate()
          }, Math.max(0, SWITCH_MIN_MS - (Date.now() - lastSwitch)) + 50)
        }
        return
      }
      if (current !== null && (t !== current || !themeChanged) && !boot) lastSwitch = Date.now()
      boot = false
      current = t
      appliedTheme = theme
      offlineBadge = t === 'offline'
      ready = false
      map.setStyle(styleFor(t), { diff: false }) // style.load ricrea sprite e livelli MeshLens
      notice = noticeFor(t)
    }

    // Precarica lo stile online: si passa a online solo se si carica davvero entro 8 s
    const verifyOnline = async () => {
      if (disposed || verifying || onlineOk || mode !== 'auto' || !info.has_offline || !navigator.onLine) return
      const ctl = new AbortController()
      verifying = ctl
      const to = setTimeout(() => ctl.abort(), ONLINE_TIMEOUT_MS)
      try {
        await fetchStyle(ctl.signal)
        onlineOk = true
        backoff = BACKOFF_START_MS
      } catch {
        onlineOk = false
        // ritenta con attesa crescente finche' il browser e' online e si mostra l'offline
        if (!disposed && !verifyTimer) {
          verifyTimer = setTimeout(() => {
            verifyTimer = null
            void verifyOnline()
          }, backoff)
          backoff = Math.min(backoff * 2, BACKOFF_MAX_MS)
        }
      } finally {
        clearTimeout(to)
        if (verifying === ctl) verifying = null
      }
      evaluate()
    }

    const onOnline = () => {
      onlineFailed = false
      backoff = BACKOFF_START_MS
      if (verifyTimer) clearTimeout(verifyTimer)
      verifyTimer = null
      void verifyOnline()
      evaluate()
    }
    const onOffline = () => {
      onlineOk = false
      evaluate()
    }

    const readCfg = async (): Promise<boolean> => {
      const [st, inf] = await Promise.all([
        getJSON<AppSettings>('/settings').catch(() => null),
        getJSON<StyleInfo>('/maps/style-info').catch(() => null), // server senza mappe offline (404): niente offline
      ])
      if (disposed) return false
      if (st?.map_mode === 'online' || st?.map_mode === 'offline' || st?.map_mode === 'auto') mode = st.map_mode
      if (inf && typeof inf.has_offline === 'boolean') info = { has_offline: inf.has_offline, maxzoom: inf.maxzoom ?? 14, bounds: inf.bounds ?? null }
      if (mode !== 'offline') addPreconnect()
      return true
    }

    const reload = async () => {
      const hadOffline = info.has_offline
      if (!(await readCfg()) || !map) return
      // se si stava gia' mostrando l'online, non si passa all'offline solo perche' ora ci sono mappe
      if (!hadOffline && info.has_offline && current === 'online') onlineOk = true
      evaluate(true)
      void verifyOnline()
    }
    reloadCfg = () => void reload()

    const publishBounds = () => {
      if (!map) return
      const b = map.getBounds()
      maps.bounds = bboxFromBounds(b)
    }
    let boundsTimer: ReturnType<typeof setTimeout> | null = null
    const onMoveEnd = () => {
      if (boundsTimer) return
      boundsTimer = setTimeout(() => {
        boundsTimer = null
        if (!disposed) publishBounds()
      }, 250)
    }

    // Cambio di tema: una sola ricreazione dello stile (nessun setStyle in cascata)
    const offTheme = themeCtl.subscribe((t) => {
      const changed = t !== appliedTheme
      theme = t
      evaluate(changed)
    })

    const start = async () => {
      if (!(await readCfg())) return
      theme = themeCtl.theme()
      appliedTheme = theme
      // la mappa nasce subito: se lo stile online non e' ancora scaricato parte con quello offline (se c'e') o di base
      const wanted = target()
      const needsStyle = wanted === 'online' && !styleJson
      current = needsStyle ? (info.has_offline ? 'offline' : 'fallback') : wanted
      boot = needsStyle
      notice = noticeFor(needsStyle ? wanted : current)
      offlineBadge = current === 'offline'
      map = new maplibregl.Map({ container: el, style: styleFor(current), center: [12.5, 42.5], zoom: 5, attributionControl: { compact: true }, fadeDuration: 0 })
      map.on('style.load', () => setup(current !== 'fallback'))
      map.on('moveend', onMoveEnd)
      publishBounds()
      window.addEventListener('online', onOnline)
      window.addEventListener('offline', onOffline)
      void verifyOnline()
      if (needsStyle) void loadStyle().then(() => evaluate(true))
    }
    void start()

    return () => {
      disposed = true
      offTheme()
      window.removeEventListener('online', onOnline)
      window.removeEventListener('offline', onOffline)
      verifying?.abort()
      reloadCfg = null
      if (boundsTimer) clearTimeout(boundsTimer)
      if (retryTimer) clearTimeout(retryTimer)
      if (verifyTimer) clearTimeout(verifyTimer)
      if (timer) clearTimeout(timer)
      cancelPick()
      popup?.remove()
      map?.remove()
      map = null
      ready = false
    }
  })

  function nodeName(id: string): string {
    const n = app.nodes.get(id)
    return n?.short_name || n?.long_name || id
  }

  // Popup in HTML con i token: il contenuto e' un componente Svelte montato nel popup di MapLibre
  type PopupProps = ComponentProps<typeof NodePopup>
  function openPopup(at: maplibregl.LngLat, props: PopupProps) {
    if (!map) return
    popup?.remove()
    const host = document.createElement('div')
    const comp = mount(NodePopup, { target: host, props })
    const p = new maplibregl.Popup({ closeButton: true, className: 'ml-popup', maxWidth: '280px' }).setLngLat(at).setDOMContent(host).addTo(map)
    p.on('close', () => {
      void unmount(comp)
      if (popup === p) popup = null
    })
    popup = p
  }

  const snrText = (v: unknown) => (typeof v === 'number' ? `${signed(v, 1)} dB` : 'sconosciuto')

  function showNodePopup(at: maplibregl.LngLat, id: string) {
    const n = app.nodes.get(id)
    if (!n) return
    const long = n.long_name && n.long_name !== (n.short_name || '') ? n.long_name : undefined
    const rows = [
      { label: 'Ultimo contatto', value: timeAgo(n.last_heard, now) },
      { label: 'SNR', value: snrText(n.last_snr) },
      { label: 'Salti', value: hopsLabel(n.hops, n.hops_min) },
    ]
    const pos = n.lat !== null && n.lon !== null ? { lat: n.lat, lon: n.lon } : null
    const origin = myOrigin(app.nodes, app.radios, geopos.pos)
    const isOrigin = origin !== null && origin.label !== 'dalla tua posizione' && (n.is_local_radio === true || app.radios.some((r) => r.state === 'connected' && r.my_node_id === id))
    if (origin && pos && !isOrigin) rows.push({ label: 'Distanza', value: `${formatMeters(haversineM(origin, pos))} ${origin.label}` })
    const radio = app.radios.find((r) => r.state === 'connected')
    const actions: NonNullable<PopupProps['actions']> = []
    if (radio) {
      actions.push({
        label: 'Messaggio diretto',
        icon: 'send',
        onclick: () => {
          openChat(`dm:${radio.id}:${id}`)
          navigate('chat')
          popup?.remove()
        },
      })
    }
    actions.push({
      label: 'Dettagli',
      icon: 'info',
      onclick: () => {
        onpick(id)
        popup?.remove()
      },
    })
    actions.push({ label: 'Copia id', icon: 'copy', onclick: () => copyText(id) })
    if (pos) actions.push({ label: 'Copia coordinate', icon: 'pin', onclick: () => copyText(`${pos.lat.toFixed(5)}, ${pos.lon.toFixed(5)}`) })
    openPopup(at, {
      title: nodeName(id),
      subtitle: long ?? id,
      source: ringKind(n),
      mine: isMine(n),
      favorite: isFavorite(n),
      rows,
      actions,
    })
  }

  function showLinkPopup(at: maplibregl.LngLat, p: Record<string, unknown>) {
    const age = Number(p.age_h)
    const eta = age < 1 ? 'meno di 1 h fa' : `${num(Math.round(age))} h fa`
    const a = app.nodes.get(String(p.from_id))
    const b = app.nodes.get(String(p.to_id))
    const rows = [
      { label: 'SNR', value: snrText(p.snr) },
      { label: 'Fonte', value: SOURCE_LABEL[String(p.source)] ?? String(p.source) },
      { label: 'Visto', value: eta },
    ]
    if (a && b && a.lat !== null && a.lon !== null && b.lat !== null && b.lon !== null) {
      rows.push({ label: 'Lunghezza', value: formatMeters(haversineM({ lat: a.lat, lon: a.lon }, { lat: b.lat, lon: b.lon })) })
    }
    openPopup(at, { title: `${nodeName(String(p.from_id))} ↔ ${nodeName(String(p.to_id))}`, rows })
  }

  function showCoveragePopup(at: maplibregl.LngLat, p: Record<string, unknown>, missing: boolean) {
    openPopup(at, {
      title: `${typeof p.seq === 'number' ? `Pacchetto ${p.seq}` : 'Pacchetto'}`,
      subtitle: formatDate(Number(p.time)),
      rows: missing
        ? [{ label: 'Esito', value: 'non ricevuto' }]
        : [
            { label: 'SNR', value: snrText(p.snr) },
            { label: 'RSSI', value: typeof p.rssi === 'number' ? `${signed(p.rssi)} dBm` : 'sconosciuto' },
            { label: 'Salti', value: typeof p.hops === 'number' ? num(p.hops) : 'sconosciuto' },
            { label: 'Distanza base', value: typeof p.distance_m === 'number' ? formatMeters(p.distance_m) : 'sconosciuta' },
          ],
    })
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
    src('track')?.setData(trackData(track))
    if (track && track.length > 1) {
      const b = new maplibregl.LngLatBounds(track[0], track[0])
      for (const p of track) b.extend(p)
      map?.fitBounds(b, { padding: 60, maxZoom: 15 })
    }
  }

  function fitAll() {
    const pts = nodes.filter((n) => n.lat !== null && n.lon !== null)
    if (!map || pts.length === 0) return
    const b = new maplibregl.LngLatBounds([pts[0].lon!, pts[0].lat!], [pts[0].lon!, pts[0].lat!])
    for (const n of pts) b.extend([n.lon!, n.lat!])
    map.fitBounds(b, { padding: 60, maxZoom: 12, duration: 0 })
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
  // Modalita' mappa, mappe scaricate o eliminate: si applica alla mappa viva senza rimontarla
  $effect(() => {
    const v = maps.version
    untrack(() => {
      if (v === seenVersion) return
      seenVersion = v
      reloadCfg?.()
    })
  })
  $effect(() => {
    if (focus && map) map.easeTo({ center: [focus.lon, focus.lat], zoom: Math.max(map.getZoom(), 10) })
  })

</script>

<div class="map" bind:this={el}></div>
<MapControls onzoomin={() => map?.zoomIn({ duration: 0 })} onzoomout={() => map?.zoomOut({ duration: 0 })} onfit={fitAll} />
<Legend />
{#if offlineBadge}
  <div class="badge" role="status"><Icon name="cloudoff" size={16} />Mappa offline</div>
{/if}
{#if nodes.length === 0 && total > 0}
  <div class="nonodes" role="status">
    <span>Nessun nodo con i filtri attivi</span>
    <ActiveFilters compact />
  </div>
{/if}
{#if notice}<div class="notice" role="status">{notice}</div>{/if}
{#if coverage.detail}
  <div class="covbar">
    <div class="row">
      <b>{coverage.detail.name}</b>
      <Button onclick={closeTest}>Chiudi prova</Button>
    </div>
    {#if coverage.detail.base_lat === null}
      <p>Posizione della base sconosciuta: tocca la mappa per impostarla</p>
    {/if}
    {#if picking}
      <p>Tocca la mappa nel punto in cui si trova la base.</p>
      <Button kind="ghost" onclick={cancelPick}>Annulla</Button>
    {:else}
      <Button onclick={startPick}>Imposta posizione base</Button>
    {/if}
    {#if pickError}<p class="err">{pickError}</p>{/if}
  </div>
{/if}

<style>
  .map {
    position: absolute;
    inset: 0;
    background: var(--map-land);
  }
  .covbar {
    position: absolute;
    top: var(--space-3);
    left: var(--space-3);
    z-index: var(--z-map-ui);
    max-width: 280px;
    padding: var(--space-3);
    border-radius: var(--radius-lg);
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-2);
    font-size: 14px;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  :global(.vp-phone) .covbar {
    top: calc(var(--touch-min) + var(--space-3) * 2);
  }
  .covbar p {
    margin: 0;
  }
  .covbar .row {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    justify-content: space-between;
  }
  .covbar .err {
    color: var(--danger);
  }
  .notice,
  .badge {
    position: absolute;
    z-index: var(--z-map-ui);
    padding: var(--space-2) var(--space-3);
    border-radius: var(--radius-pill);
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-1);
    font-size: 13px;
    line-height: 18px;
  }
  .notice {
    bottom: var(--space-8);
    left: 50%;
    transform: translateX(-50%);
    max-width: calc(100% - var(--space-8));
    text-align: center;
  }
  .nonodes {
    position: absolute;
    z-index: var(--z-map-ui);
    bottom: calc(var(--space-8) + var(--space-12));
    left: 50%;
    transform: translateX(-50%);
    max-width: calc(100% - var(--space-8));
    padding: var(--space-3);
    border-radius: var(--radius-lg);
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-2);
    font-size: 14px;
    line-height: 20px;
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
    text-align: center;
  }
  .badge {
    top: var(--space-3);
    left: 50%;
    transform: translateX(-50%);
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  :global(.vp-phone) .notice,
  :global(.vp-phone) .badge {
    font-size: 14px;
    line-height: 20px;
  }
  /* Popup e attribuzione di MapLibre in tema */
  :global(.ml-popup .maplibregl-popup-content) {
    background: var(--surface-raised);
    color: var(--ink);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-3);
    padding: var(--space-3);
  }
  :global(.ml-popup.maplibregl-popup-anchor-bottom .maplibregl-popup-tip),
  :global(.ml-popup.maplibregl-popup-anchor-bottom-left .maplibregl-popup-tip),
  :global(.ml-popup.maplibregl-popup-anchor-bottom-right .maplibregl-popup-tip) {
    border-top-color: var(--surface-raised);
  }
  :global(.ml-popup.maplibregl-popup-anchor-top .maplibregl-popup-tip),
  :global(.ml-popup.maplibregl-popup-anchor-top-left .maplibregl-popup-tip),
  :global(.ml-popup.maplibregl-popup-anchor-top-right .maplibregl-popup-tip) {
    border-bottom-color: var(--surface-raised);
  }
  :global(.ml-popup.maplibregl-popup-anchor-left .maplibregl-popup-tip) {
    border-right-color: var(--surface-raised);
  }
  :global(.ml-popup.maplibregl-popup-anchor-right .maplibregl-popup-tip) {
    border-left-color: var(--surface-raised);
  }
  :global(.ml-popup .maplibregl-popup-close-button) {
    color: var(--ink-muted);
    font-size: 20px;
    min-width: var(--control-h-desktop);
    min-height: var(--control-h-desktop);
    border-radius: var(--radius-md);
  }
  :global(.vp-phone .ml-popup .maplibregl-popup-close-button) {
    min-width: var(--touch-min);
    min-height: var(--touch-min);
  }
  :global(.maplibregl-ctrl-attrib) {
    background: color-mix(in srgb, var(--surface) 85%, transparent);
    color: var(--ink-muted);
  }
  :global(.maplibregl-ctrl-attrib a) {
    color: var(--accent-ink);
  }
  :global(.maplibregl-ctrl-attrib-button) {
    filter: none;
  }
</style>
