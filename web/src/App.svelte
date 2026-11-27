<script lang="ts">
import { safeStorage } from './lib/storage'
  import { onMount, untrack } from 'svelte'
  import Login from './components/Login.svelte'
  import MapView from './components/MapView.svelte'
  import NodeList from './components/NodeList.svelte'
  import NodeSortBar from './components/NodeSortBar.svelte'
  import NodeDetail from './components/NodeDetail.svelte'
  import Filters from './components/Filters.svelte'
  import ActiveFilters from './components/ActiveFilters.svelte'
  import Chat from './components/Chat.svelte'
  import Radios from './components/Radios.svelte'
  import Settings from './components/Settings.svelte'
  import NetworkPage from './components/NetworkPage.svelte'
  import Coverage from './components/Coverage.svelte'
  import ConfigPanel from './components/ConfigPanel.svelte'
  import Onboarding from './components/Onboarding.svelte'
  import GlobalSearch from './components/GlobalSearch.svelte'
  import WhatsNew from './components/WhatsNew.svelte'
  import TopBar from './lib/shell/TopBar.svelte'
  import Panel from './lib/shell/Panel.svelte'
  import BottomNav from './lib/shell/BottomNav.svelte'
  import ConnectionBar from './lib/shell/ConnectionBar.svelte'
  import UpdatedBanner from './lib/shell/UpdatedBanner.svelte'
  import { checkServerVersion } from './lib/appversion.svelte'
  import Icon from './lib/ui/Icon.svelte'
  import Sheet from './lib/ui/Sheet.svelte'
  import Empty from './lib/ui/Empty.svelte'
  import Button from './lib/ui/Button.svelte'
  import Toast from './lib/ui/Toast.svelte'
  import { setNavigator } from './lib/shell/navigate'
  import { viewport } from './lib/viewport.svelte'
  import { MORE_TABS, effectiveTab, isMoreTab, isPageTab, loadChatExpanded, saveChatExpanded, sheetVisible, type Tab } from './lib/shell/nav'
  import type { SheetSnap } from './lib/ui/sheetSnap'
  import { matchNode, visibleNodes } from './lib/filters'
  import { myOrigin } from './lib/distance'
  import { geopos } from './lib/geopos.svelte'
  import type { NodeSortKey } from './lib/nodesort'
  import { formatHash, parseHash, type Route } from './lib/route'
  import { loadView, saveView } from './lib/viewstate'
  import { applyPredictionJob } from './lib/prediction.svelte'
  import { applySfJob, setSfRouters } from './lib/storeforward.svelte'
  import { ApiError, getJSON, alerts as fetchAlerts, alertsHidden as fetchAlertsHidden, conversations, waypoints as fetchWaypoints, coverageSessions, coverageSession, updateStatus, AUTH_REQUIRED } from './lib/api'
  import { connectWS } from './lib/ws'
  import { notifyWsResync } from './lib/wsext'
  import { onIncoming } from './lib/incoming'
  import { unread, applySummaries, applyRead, totalUnread } from './lib/unread.svelte'
  import { titleFor } from './lib/notify'
  import { t } from './lib/i18n/index.svelte'
  import { markOnline, markOffline, resetConn } from './lib/connection.svelte'
  import { serialRunner } from './lib/serial'
  import { app, upsertNodes, addMessage, addRadioHistory, addMqttHistory,setMessageStatus, setStatus, setRadios, setAlerts, setTraceroute, persistFilter, persistFeedFilter, coverage, setCoverageSessions, applyCoverage, configUi, setConfigJob, setMapJob, setUpdateStatus, setUpdateJob, openChat, carryOpenChat, setWaypoints, upsertWaypoint, removeWaypoint } from './lib/stores.svelte'
  import type { AuthStatus, Message, Node, Radio } from './lib/types'
  import GuestSettings from './components/settings/GuestSettings.svelte'
  import { isGuest, setRole, session } from './lib/guest.svelte'
  import { safeTab, tabsFor } from './lib/guest'

  let auth = $state<AuthStatus | null>(null)
  let error = $state(false)
  // Vista iniziale: prima l'hash (link diretto), poi la vista ricordata, poi il predefinito
  const initialRoute = parseHash(location.hash)
  const initialView = loadView(safeStorage())
  let tab = $state<Tab>(initialRoute.tab ?? initialView.tab ?? (viewport.phone ? 'map' : 'nodes'))
  let snap = $state<SheetSnap>(1)
  let now = $state(Math.floor(Date.now() / 1000))
  let track = $state<[number, number][] | null>(null)
  let focus = $state<{ lat: number; lon: number; seq: number } | null>(null)
  // Messaggi a pagina intera su desktop (pulsante Espandi), scelta ricordata
  let chatExpanded = $state(loadChatExpanded(safeStorage()))
  const chatWide = $derived(chatExpanded && !viewport.phone)
  function setChatExpanded(v: boolean) {
    carryOpenChat() // la chat viene ricreata nell'altra vista: la conversazione resta aperta
    chatExpanded = v
    saveChatExpanded(safeStorage(), v)
  }

  const visible = $derived(
    [...app.nodes.values()].filter((n) => matchNode(n, app.filter, now)),
  )
  let nodeSort = $state<NodeSortKey>(initialView.nodeSort)
  const origin = $derived(myOrigin(app.nodes, app.radios, geopos.pos))
  const selected = $derived(app.selectedId ? (app.nodes.get(app.selectedId) ?? null) : null)
  // Su desktop "Mappa" e "Altro" non esistono come schede: la mappa e' sempre visibile
  // l'ospite (E19) non ha Messaggi, Radio, Copertura: una scheda non ammessa ricade su Nodi
  const activeTab = $derived<Tab>(safeTab(effectiveTab(tab, viewport.phone), session.role))
  const guest = $derived(session.role === 'guest')
  const alertCount = $derived(app.alerts.length)
  const unreadTotal = $derived(totalUnread(unread.counts))

  function goTab(t: Tab) {
    tab = t
    if (!viewport.phone || t === 'map') return
    // le pagine lunghe si aprono al massimo, le altre almeno al primo fermo
    if (isPageTab(t)) snap = 2
    else if (snap === 0) snap = 1
  }

  function pick(n: Node) {
    app.selectedId = n.id
    if (n.lat !== null && n.lon !== null) focus = { lat: n.lat, lon: n.lon, seq: (focus?.seq ?? 0) + 1 }
    if (viewport.phone) {
      tab = 'map'
      if (snap === 0) snap = 1
    } else if (isPageTab(tab)) {
      tab = 'nodes'
    }
  }

  function pickId(id: string) {
    const n = app.nodes.get(id)
    if (n) pick(n)
    else app.selectedId = id
  }

  // Nodo del link diretto non ancora caricato: variabile semplice, non reattiva
  let pendingNode: string | null = null
  let nodesLoaded = false
  // id del nodo del link diretto che non esiste (il testo si compone nel template, nella lingua corrente)
  let routeError = $state('')

  function applyRoute(r: Route) {
    if (r.tab) goTab(r.tab)
    if (!r.nodeId) return
    if (app.nodes.has(r.nodeId)) {
      pendingNode = null
      pickId(r.nodeId)
    } else {
      pendingNode = r.nodeId
      if (nodesLoaded) void resolvePending()
    }
  }

  /** Dopo il caricamento dei nodi: seleziona il nodo in attesa (una volta sola) o segnala che non esiste. */
  async function resolvePending() {
    const id = pendingNode
    if (!id) return
    pendingNode = null
    if (app.nodes.has(id)) return pickId(id)
    try {
      upsertNodes([await getJSON<Node>('/nodes/' + encodeURIComponent(id))])
      pickId(id)
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) routeError = id
      else if (pendingNode === null) pendingNode = id // errore di rete: si riprova al prossimo caricamento
    }
  }

  function close() {
    app.selectedId = null
    track = null
  }

  async function refresh() {
    try {
      auth = await getJSON<AuthStatus>('/auth/status')
      setRole(auth.role)
      error = false
    } catch {
      error = true
    }
  }

  onMount(() => {
    setNavigator(goTab)
    applyRoute(initialRoute)
    // ultima conversazione: resta in attesa nel ponte finche' Messaggi non si monta
    if (initialView.conv && !initialRoute.nodeId) openChat(initialView.conv)
    const onHash = () => applyRoute(parseHash(location.hash))
    window.addEventListener('hashchange', onHash)
    refresh()
    const tick = setInterval(() => (now = Math.floor(Date.now() / 1000)), 30_000)
    const onAuth = () => {
      if (auth) auth = { ...auth, authenticated: false }
    }
    window.addEventListener(AUTH_REQUIRED, onAuth)
    return () => {
      window.removeEventListener(AUTH_REQUIRED, onAuth)
      window.removeEventListener('hashchange', onHash)
      clearInterval(tick)
      setNavigator(null)
    }
  })

  // server non raggiungibile: nuovo tentativo ogni 5 s finche' l'errore resta
  $effect(() => {
    if (!error) return
    const t = setInterval(() => void refresh(), 5000)
    return () => clearInterval(t)
  })

  // L'hash e la vista ricordata seguono scheda e nodo selezionato (nessuno stato reattivo scritto qui)
  $effect(() => {
    const t = activeTab === 'more' ? null : activeTab
    history.replaceState(null, '', formatHash({ tab: t, nodeId: app.selectedId ?? pendingNode }) || location.pathname)
    if (t) saveView(safeStorage(), { tab: t })
  })

  // legge lo stato, scrive solo il DOM
  $effect(() => {
    document.title = titleFor(t('shell.title'), unreadTotal)
  })

  $effect(persistFilter)
  $effect(persistFeedFilter)

  $effect(() => {
    if (!auth?.authenticated) return
    // un caricamento alla volta: un resync arrivato a metà riparte dopo, non si sovrappone
    const loader = serialRunner(() => {
      if (isGuest()) {
        // ospite: solo nodi e avvisi dei nodi (il resto il server lo nega)
        return Promise.allSettled([
          getJSON<Node[]>('/nodes').then((list) => {
            upsertNodes(list)
            nodesLoaded = true
            void resolvePending()
          }),
          fetchAlerts().then(setAlerts),
        ])
      }
      const jobs: Promise<unknown>[] = [
        getJSON<Node[]>('/nodes').then((list) => {
          upsertNodes(list)
          nodesLoaded = true
          void resolvePending()
        }),
        getJSON<Message[]>('/messages/radio?limit=200').then(addRadioHistory),
        getJSON<Message[]>('/messages?limit=200').then(addMqttHistory),
        getJSON<Radio[]>('/radios').then(setRadios),
        fetchAlerts().then(setAlerts),
        fetchAlertsHidden().then((r) => { app.alertsHidden = r.count }),
        conversations().then(applySummaries),
        fetchWaypoints().then(setWaypoints),
        coverageSessions().then(setCoverageSessions),
        updateStatus().then(setUpdateStatus),
      ]
      const openId = untrack(() => coverage.openId)
      if (openId !== null) {
        const id = openId
        jobs.push(
          coverageSession(id).then((d) => {
            if (coverage.openId === id) coverage.detail = d
          }),
        )
      }
      return Promise.allSettled(jobs)
    })
    const load = loader.trigger
    load()
    const stopWS = connectWS({
      reconnected: () => {
        load()
        app.reconnects++
        notifyWsResync()
      },
      resync: () => {
        load()
        notifyWsResync()
      },
      authLost: resetConn,
      connection: (on) => {
        if (on) {
          markOnline(Date.now())
          void checkServerVersion()
        } else markOffline(Date.now())
      },
      nodes: upsertNodes,
      message: (m) => {
        addMessage(m)
        onIncoming(m)
      },
      status: setStatus,
      radios: setRadios,
      alerts: setAlerts,
      traceroute: setTraceroute,
      coverage: applyCoverage,
      messageStatus: setMessageStatus,
      waypoint: upsertWaypoint,
      waypointDeleted: removeWaypoint,
      convRead: applyRead,
      configJob: setConfigJob,
      mapJob: setMapJob,
      updateJob: setUpdateJob,
      prediction_job: applyPredictionJob,
      sf_job: applySfJob,
      sf_routers: setSfRouters,
    })
    const onVisible = () => {
      if (document.visibilityState === 'visible') void checkServerVersion()
    }
    document.addEventListener('visibilitychange', onVisible)
    return () => {
      document.removeEventListener('visibilitychange', onVisible)
      loader.dispose()
      stopWS()
    }
  })
</script>

{#snippet screens()}
  {#if activeTab === 'nodes'}
    <Filters />
    <ActiveFilters />
    <NodeSortBar
      value={nodeSort}
      hasOrigin={origin !== null}
      onchange={(k) => {
        nodeSort = k
        saveView(safeStorage(), { nodeSort: k })
      }}
    />
    <NodeList nodes={visible} {now} sort={nodeSort} {origin} onpick={pick} />
  {:else if activeTab === 'network'}
    <NetworkPage nodes={visibleNodes(app.nodes.values())} {now} onpick={pick} />
  {:else if activeTab === 'coverage'}
    <Coverage {now} />
  {:else if activeTab === 'chat'}
    <Chat {now} onpick={pickId} expanded={chatWide} canExpand={!viewport.phone} ontoggleexpand={() => setChatExpanded(!chatExpanded)} />
  {:else if activeTab === 'radio'}
    <Radios />
  {:else if activeTab === 'settings' && guest}
    <GuestSettings onlogout={refresh} />
  {:else if activeTab === 'settings'}
    <Settings onlogout={refresh} />
  {/if}
{/snippet}

{#if error}
  <div class="center">
    <Empty icon="cloudoff" title={t('shell.serverUnreachable')}>
      {t('shell.serverUnreachableHint')}
      {#snippet action()}<Button kind="primary" onclick={refresh}>{t('common.retry')}</Button>{/snippet}
    </Empty>
  </div>
{:else if !auth}
  <p class="center">{t('shell.loading')}</p>
{:else if !auth.authenticated}
  <Login status={auth} onsuccess={refresh} />
{:else}
  <div class="app">
    {#if !guest}
      <Onboarding />
      <GlobalSearch />
      <WhatsNew />
    {/if}
    <TopBar visible={visible.length} {now} tab={activeTab} onselect={goTab} onupdate={() => goTab('settings')} onpickalert={pickId} />
    <ConnectionBar />
    <UpdatedBanner />
    <div class="main">
      {#if routeError}
        <div class="route-toast"><Toast kind="warn" onclose={() => (routeError = '')}>{t('shell.nodeNotFound', { id: routeError })}</Toast></div>
      {/if}
      <div class="mapwrap"><MapView nodes={visible} total={app.nodes.size} {now} {track} {focus} onpick={pickId} /></div>

      {#if !viewport.phone}
        {#if isPageTab(activeTab, chatWide)}
          <div class="page" class:chatpage={activeTab === 'chat'}>
            {@render screens()}
            {#if activeTab === 'chat' && selected}
              <!-- Messaggi espansi: la scheda del nodo si apre sopra la chat, senza uscire dalla conversazione -->
              <aside class="nodedrawer" aria-label={t('chat.nodeDrawer')}>
                <div class="drawerbar">
                  <Button icon="map" onclick={() => setChatExpanded(false)}>{t('chat.showOnMap')}</Button>
                </div>
                <NodeDetail node={selected} {now} ontrack={(tr) => (track = tr)} onclose={close} onchat={() => goTab('chat')} />
              </aside>
            {/if}
          </div>
        {:else}
          <Panel>
            {#if selected}
              <NodeDetail node={selected} {now} ontrack={(t) => (track = t)} onclose={close} onchat={() => goTab('chat')} />
            {/if}
            {@render screens()}
          </Panel>
        {/if}
      {:else if sheetVisible(activeTab, !!selected)}
        <Sheet bind:snap label={t('shell.panel')}>
          {#if tab === 'more'}
            <ul class="more">
              {#each tabsFor(MORE_TABS, session.role) as m (m.id)}
                <li>
                  <button type="button" onclick={() => goTab(m.id)}>
                    <Icon name={m.icon} size={20} /><span>{t(m.labelKey)}</span><Icon name="chevR" size={18} />
                  </button>
                </li>
              {/each}
            </ul>
          {:else}
            {#if isMoreTab(tab)}
              <button type="button" class="back" onclick={() => goTab('more')}><Icon name="back" size={18} />{t('nav.more')}</button>
            {/if}
            {#if selected}
              <NodeDetail node={selected} {now} ontrack={(t) => (track = t)} onclose={close} onchat={() => goTab('chat')} />
            {/if}
            {@render screens()}
          {/if}
        </Sheet>
      {/if}
    </div>
    {#if viewport.phone}
      <BottomNav tab={tab} alerts={alertCount} unread={unreadTotal} onselect={goTab} />
    {/if}
  </div>
  {#if configUi.target && !guest}
    <ConfigPanel nodeId={configUi.target.nodeId} radioId={configUi.target.radioId} initialTab={configUi.target.tab} {now} onclose={() => (configUi.target = null)} />
  {/if}
{/if}

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100dvh;
    overflow: hidden;
    background: var(--bg);
    color: var(--ink);
  }
  .main {
    flex: 1;
    min-height: 0;
    display: flex;
    position: relative;
  }
  .mapwrap {
    flex: 1;
    position: relative;
    order: 2;
    min-width: 0;
  }
  /* Pagine lunghe (Rete, Impostazioni): occupano tutta l'area sotto la barra */
  .page.chatpage {
    overflow: hidden;
  }
  .nodedrawer {
    position: absolute;
    top: 0;
    right: 0;
    bottom: 0;
    width: min(420px, 100%);
    overflow: auto;
    background: var(--surface);
    border-left: 1px solid var(--line-strong);
    box-shadow: var(--shadow-lg, 0 8px 24px rgba(0, 0, 0, 0.18));
    z-index: 2;
  }
  .drawerbar {
    display: flex;
    justify-content: flex-end;
    padding: var(--space-2) var(--space-3) 0;
  }
  .page {
    position: absolute;
    inset: 0;
    overflow: auto;
    background: var(--surface);
    z-index: var(--z-panel);
  }
  :global(.vp-phone) .mapwrap {
    position: absolute;
    inset: 0;
  }
  /* La barra in basso gestisce gia' la safe area: lo Sheet non la raddoppia */
  .main :global(.ui-sheet) {
    padding-bottom: 0;
  }
  .route-toast {
    position: absolute;
    top: var(--space-3);
    left: 50%;
    transform: translateX(-50%);
    z-index: var(--z-toast);
    width: max-content;
    max-width: calc(100% - 2 * var(--space-3));
  }
  .more {
    list-style: none;
    margin: 0;
    padding: var(--space-2) var(--space-3);
  }
  .more button,
  .back {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    min-height: var(--touch-min);
    padding: 0 var(--space-3);
    background: none;
    border: 0;
    border-bottom: 1px solid var(--line);
    color: var(--ink);
    font: 500 16px/24px var(--font-sans);
    text-align: left;
    cursor: pointer;
  }
  .more button span {
    flex: 1;
  }
  .back {
    color: var(--accent);
    font-size: 14px;
  }
  .center {
    text-align: center;
    margin-top: 20vh;
    color: var(--ink);
  }
</style>
