<script lang="ts">
  import { onMount, untrack } from 'svelte'
  import Login from './components/Login.svelte'
  import MapView from './components/MapView.svelte'
  import NodeList from './components/NodeList.svelte'
  import NodeDetail from './components/NodeDetail.svelte'
  import Filters from './components/Filters.svelte'
  import Chat from './components/Chat.svelte'
  import Radios from './components/Radios.svelte'
  import Settings from './components/Settings.svelte'
  import Network from './components/Network.svelte'
  import Coverage from './components/Coverage.svelte'
  import ConfigPanel from './components/ConfigPanel.svelte'
  import TopBar from './lib/shell/TopBar.svelte'
  import Panel from './lib/shell/Panel.svelte'
  import BottomNav from './lib/shell/BottomNav.svelte'
  import Icon from './lib/ui/Icon.svelte'
  import Sheet from './lib/ui/Sheet.svelte'
  import { viewport } from './lib/viewport.svelte'
  import { MORE_TABS, effectiveTab, isMoreTab, isPageTab, sheetVisible, type Tab } from './lib/shell/nav'
  import type { SheetSnap } from './lib/ui/sheetSnap'
  import { matchNode } from './lib/filters'
  import { getJSON, alerts as fetchAlerts, coverageSessions, coverageSession, updateStatus, AUTH_REQUIRED } from './lib/api'
  import { connectWS } from './lib/ws'
  import { app, upsertNodes, addMessage, addRadioHistory, setMessageStatus, setStatus, setRadios, setAlerts, setTraceroute, persistFilter, persistFeedFilter, coverage, setCoverageSessions, applyCoverage, configUi, setConfigJob, setMapJob, setUpdateStatus, setUpdateJob } from './lib/stores.svelte'
  import type { AuthStatus, Message, Node, Radio } from './lib/types'

  let auth = $state<AuthStatus | null>(null)
  let error = $state('')
  let tab = $state<Tab>(viewport.phone ? 'map' : 'nodes')
  let snap = $state<SheetSnap>(1)
  let now = $state(Math.floor(Date.now() / 1000))
  let track = $state<[number, number][] | null>(null)
  let focus = $state<{ lat: number; lon: number; seq: number } | null>(null)

  const visible = $derived(
    [...app.nodes.values()].filter((n) => matchNode(n, app.filter, now)),
  )
  const selected = $derived(app.selectedId ? (app.nodes.get(app.selectedId) ?? null) : null)
  // Su desktop "Mappa" e "Altro" non esistono come schede: la mappa e' sempre visibile
  const activeTab = $derived<Tab>(effectiveTab(tab, viewport.phone))
  const alertCount = $derived(app.alerts.length)

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

  function close() {
    app.selectedId = null
    track = null
  }

  async function refresh() {
    try {
      auth = await getJSON<AuthStatus>('/auth/status')
      error = ''
    } catch {
      error = 'Server non raggiungibile'
    }
  }

  onMount(() => {
    refresh()
    const tick = setInterval(() => (now = Math.floor(Date.now() / 1000)), 30_000)
    const onAuth = () => {
      if (auth) auth = { ...auth, authenticated: false }
    }
    window.addEventListener(AUTH_REQUIRED, onAuth)
    return () => {
      window.removeEventListener(AUTH_REQUIRED, onAuth)
      clearInterval(tick)
    }
  })

  $effect(persistFilter)
  $effect(persistFeedFilter)

  $effect(() => {
    if (!auth?.authenticated) return
    const load = () => {
      getJSON<Node[]>('/nodes')
        .then(upsertNodes)
        .catch(() => {})
      getJSON<Message[]>('/messages/radio?limit=200')
        .then(addRadioHistory)
        .catch(() => {})
      getJSON<Radio[]>('/radios')
        .then(setRadios)
        .catch(() => {})
      fetchAlerts()
        .then(setAlerts)
        .catch(() => {})
      coverageSessions()
        .then(setCoverageSessions)
        .catch(() => {})
      updateStatus()
        .then(setUpdateStatus)
        .catch(() => {})
      const openId = untrack(() => coverage.openId)
      if (openId !== null) {
        const id = openId
        coverageSession(id)
          .then((d) => {
            if (coverage.openId === id) coverage.detail = d
          })
          .catch(() => {})
      }
    }
    load()
    return connectWS({
      reconnected: () => {
        load()
        app.reconnects++
      },
      nodes: upsertNodes,
      message: addMessage,
      status: setStatus,
      radios: setRadios,
      alerts: setAlerts,
      traceroute: setTraceroute,
      coverage: applyCoverage,
      messageStatus: setMessageStatus,
      configJob: setConfigJob,
      mapJob: setMapJob,
      updateJob: setUpdateJob,
    })
  })
</script>

{#snippet screens()}
  {#if activeTab === 'nodes'}
    <Filters />
    <NodeList nodes={visible} {now} onpick={pick} />
  {:else if activeTab === 'network'}
    <Network nodes={[...app.nodes.values()]} {now} onpick={pick} />
  {:else if activeTab === 'coverage'}
    <Coverage {now} />
  {:else if activeTab === 'chat'}
    <Chat {now} onpick={pickId} />
  {:else if activeTab === 'radio'}
    <Radios />
  {:else if activeTab === 'settings'}
    <Settings onlogout={refresh} />
  {/if}
{/snippet}

{#if error}
  <p class="center">{error}</p>
{:else if !auth}
  <p class="center">Caricamento…</p>
{:else if !auth.authenticated}
  <Login status={auth} onsuccess={refresh} />
{:else}
  <div class="app">
    <TopBar visible={visible.length} tab={activeTab} onselect={goTab} onupdate={() => goTab('settings')} onpickalert={pickId} />
    <div class="main">
      <div class="mapwrap"><MapView nodes={visible} {now} {track} {focus} /></div>

      {#if !viewport.phone}
        {#if isPageTab(activeTab)}
          <div class="page">{@render screens()}</div>
        {:else}
          <Panel>
            {#if selected}
              <NodeDetail node={selected} {now} ontrack={(t) => (track = t)} onclose={close} onchat={() => goTab('chat')} />
            {/if}
            {@render screens()}
          </Panel>
        {/if}
      {:else if sheetVisible(activeTab, !!selected)}
        <Sheet bind:snap label="Pannello">
          {#if tab === 'more'}
            <ul class="more">
              {#each MORE_TABS as m (m.id)}
                <li>
                  <button type="button" onclick={() => goTab(m.id)}>
                    <Icon name={m.icon} size={20} /><span>{m.label}</span><Icon name="chevR" size={18} />
                  </button>
                </li>
              {/each}
            </ul>
          {:else}
            {#if isMoreTab(tab)}
              <button type="button" class="back" onclick={() => goTab('more')}><Icon name="back" size={18} />Altro</button>
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
      <BottomNav tab={tab} alerts={alertCount} onselect={goTab} />
    {/if}
  </div>
  {#if configUi.target}
    <ConfigPanel nodeId={configUi.target.nodeId} radioId={configUi.target.radioId} initialTab={configUi.target.tab} {now} onclose={() => (configUi.target = null)} />
  {/if}
{/if}

<style>
  .app {
    display: flex;
    flex-direction: column;
    height: 100dvh;
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
