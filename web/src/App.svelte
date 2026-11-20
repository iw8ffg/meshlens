<script lang="ts">
  import { onMount } from 'svelte'
  import Login from './components/Login.svelte'
  import MapView from './components/MapView.svelte'
  import NodeList from './components/NodeList.svelte'
  import NodeDetail from './components/NodeDetail.svelte'
  import Filters from './components/Filters.svelte'
  import StatusBar from './components/StatusBar.svelte'
  import Chat from './components/Chat.svelte'
  import Radios from './components/Radios.svelte'
  import Settings from './components/Settings.svelte'
  import { matchNode } from './lib/filters'
  import { getJSON, AUTH_REQUIRED } from './lib/api'
  import { connectWS } from './lib/ws'
  import { app, upsertNodes, addMessage, addRadioHistory, setMessageStatus, setStatus, setRadios, persistFilter } from './lib/stores.svelte'
  import type { AuthStatus, Message, Node, Radio } from './lib/types'

  let auth = $state<AuthStatus | null>(null)
  let error = $state('')
  type Tab = 'map' | 'nodes' | 'chat' | 'radio' | 'settings'
  const TABS: [Tab, string][] = [
    ['map', 'Mappa'],
    ['nodes', 'Nodi'],
    ['chat', 'Chat'],
    ['radio', 'Radio'],
    ['settings', 'Impostazioni'],
  ]
  let tab = $state<Tab>('nodes')
  let mobile = $state(false)
  let now = $state(Math.floor(Date.now() / 1000))
  let track = $state<[number, number][] | null>(null)
  let focus = $state<{ lat: number; lon: number; seq: number } | null>(null)

  const visible = $derived(
    [...app.nodes.values()].filter((n) => matchNode(n, app.filter, now)),
  )
  const selected = $derived(app.selectedId ? (app.nodes.get(app.selectedId) ?? null) : null)
  // Su desktop la scheda "Mappa" non esiste: la mappa e' sempre visibile
  const activeTab = $derived<Tab>(!mobile && tab === 'map' ? 'nodes' : tab)
  const panelOpen = $derived(activeTab !== 'map')

  function pick(n: Node) {
    app.selectedId = n.id
    if (n.lat !== null && n.lon !== null) focus = { lat: n.lat, lon: n.lon, seq: (focus?.seq ?? 0) + 1 }
    if (mobile) tab = 'map'
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
    const mq = window.matchMedia('(max-width: 767px)')
    mobile = mq.matches
    if (mobile) tab = 'map'
    const onMq = () => (mobile = mq.matches)
    mq.addEventListener('change', onMq)
    const tick = setInterval(() => (now = Math.floor(Date.now() / 1000)), 30_000)
    const onAuth = () => {
      if (auth) auth = { ...auth, authenticated: false }
    }
    window.addEventListener(AUTH_REQUIRED, onAuth)
    return () => {
      window.removeEventListener(AUTH_REQUIRED, onAuth)
      mq.removeEventListener('change', onMq)
      clearInterval(tick)
    }
  })

  $effect(persistFilter)

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
    }
    load()
    return connectWS({
      reconnected: load,
      nodes: upsertNodes,
      message: addMessage,
      status: setStatus,
      radios: setRadios,
      messageStatus: setMessageStatus,
    })
  })
</script>

{#if error}
  <p class="center">{error}</p>
{:else if !auth}
  <p class="center">Caricamento…</p>
{:else if !auth.authenticated}
  <Login status={auth} onsuccess={refresh} />
{:else}
  <div class="app" class:mobile>
    <StatusBar visible={visible.length} />
    <div class="main">
      <div class="mapwrap"><MapView nodes={visible} {now} {track} {focus} /></div>
      <aside class="panel" class:open={panelOpen || !!selected}>
        <nav class="tabs" aria-label="Sezioni">
          {#each TABS as [id, label] (id)}
            {#if mobile || id !== 'map'}
              <button class:on={activeTab === id} onclick={() => (tab = id)}>{label}</button>
            {/if}
          {/each}
        </nav>
        <div class="content">
          {#if selected}
            <NodeDetail node={selected} {now} ontrack={(t) => (track = t)} onclose={close} onchat={() => (tab = 'chat')} />
          {/if}
          {#if activeTab === 'nodes'}
            <Filters />
            <NodeList nodes={visible} {now} onpick={pick} />
          {:else if activeTab === 'chat'}
            <Chat {now} onpick={pickId} />
          {:else if activeTab === 'radio'}
            <Radios />
          {:else if activeTab === 'settings'}
            <Settings onlogout={refresh} />
          {/if}
        </div>
      </aside>
    </div>
  </div>
{/if}

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, sans-serif;
    background: #111827;
    color: #e5e7eb;
  }
  .app {
    display: flex;
    flex-direction: column;
    height: 100dvh;
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
  }
  .panel {
    order: 1;
    width: 360px;
    display: flex;
    flex-direction: column;
    background: #111827;
    border-right: 1px solid #1f2937;
  }
  .tabs {
    display: flex;
    border-bottom: 1px solid #1f2937;
  }
  .tabs button {
    flex: 1;
    padding: 10px 4px;
    background: none;
    color: inherit;
    border: 0;
    border-bottom: 2px solid transparent;
    cursor: pointer;
    font: inherit;
  }
  .tabs button.on {
    border-bottom-color: #2563eb;
    color: #93c5fd;
  }
  .content {
    flex: 1;
    overflow: auto;
  }
  /* Mobile: mappa a tutto schermo, schede in basso, pannello dal basso */
  .mobile .main {
    flex-direction: column;
  }
  .mobile .mapwrap {
    order: 1;
  }
  .mobile .panel {
    order: 2;
    width: auto;
    border-right: 0;
    border-top: 1px solid #1f2937;
  }
  .mobile .panel .tabs {
    order: 2;
    border-bottom: 0;
    border-top: 1px solid #1f2937;
  }
  .mobile .panel .content {
    order: 1;
    display: none;
    max-height: 55dvh;
  }
  .mobile .panel.open .content {
    display: block;
  }
  .center {
    text-align: center;
    margin-top: 20vh;
  }
</style>
