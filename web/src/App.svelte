<script lang="ts">
  import { onMount } from 'svelte'
  import Login from './components/Login.svelte'
  import { getJSON, AUTH_REQUIRED } from './lib/api'
  import { connectWS } from './lib/ws'
  import { upsertNodes, addMessage, setStatus } from './lib/stores.svelte'
  import type { AuthStatus } from './lib/types'

  let auth = $state<AuthStatus | null>(null)
  let error = $state('')

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
    const onAuth = () => {
      if (auth) auth = { ...auth, authenticated: false }
    }
    window.addEventListener(AUTH_REQUIRED, onAuth)
    return () => window.removeEventListener(AUTH_REQUIRED, onAuth)
  })

  $effect(() => {
    if (!auth?.authenticated) return
    return connectWS({ nodes: upsertNodes, message: addMessage, status: setStatus })
  })
</script>

{#if error}
  <p class="center">{error}</p>
{:else if !auth}
  <p class="center">Caricamento…</p>
{:else if !auth.authenticated}
  <Login status={auth} onsuccess={refresh} />
{:else}
  <p class="center">Connesso</p>
{/if}

<style>
  :global(body) {
    margin: 0;
    font-family: system-ui, sans-serif;
    background: #111827;
    color: #e5e7eb;
  }
  .center {
    text-align: center;
    margin-top: 20vh;
  }
</style>
