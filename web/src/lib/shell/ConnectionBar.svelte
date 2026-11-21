<script lang="ts">
  import Icon from '../ui/Icon.svelte'
  import { conn, connectionView, RESTORED_MS } from '../connection.svelte'
  import { reconnectNow } from '../ws'

  let nowMs = $state(Date.now())
  let browserOnline = $state(typeof navigator === 'undefined' ? true : navigator.onLine)

  const view = $derived(connectionView(conn, nowMs, browserOnline))
  // il ricalcolo periodico serve solo mentre si e' offline o il "ripristinata" e' recente
  const ticking = $derived(!conn.online || (conn.restoredAt !== null && nowMs - conn.restoredAt < RESTORED_MS))

  $effect(() => {
    const on = () => (browserOnline = true)
    const off = () => (browserOnline = false)
    window.addEventListener('online', on)
    window.addEventListener('offline', off)
    return () => {
      window.removeEventListener('online', on)
      window.removeEventListener('offline', off)
    }
  })

  $effect(() => {
    if (!ticking) return
    const id = setInterval(() => (nowMs = Date.now()), 1000)
    return () => clearInterval(id)
  })
</script>

{#if view.show}
  <div class="bar {view.tone}" role="status" aria-live="polite">
    <Icon name={view.tone === 'ok' ? 'check' : 'cloudoff'} size={18} />
    <span class="txt">{view.text}</span>
    {#if view.retry}
      <button type="button" onclick={reconnectNow}>Riprova ora</button>
    {/if}
  </div>
{/if}

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    color: var(--ink);
    font: 500 14px/20px var(--font-sans);
    border-bottom: 1px solid var(--line);
  }
  .warn {
    background: var(--warn-soft);
  }
  .ok {
    background: var(--ok-soft);
  }
  .txt {
    flex: 1;
    min-width: 0;
  }
  button {
    min-height: 32px;
    padding: 0 var(--space-3);
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-strong);
    border-radius: var(--radius-md);
    font: 500 14px/20px var(--font-sans);
    cursor: pointer;
  }
  button:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  :global(.vp-phone) button {
    min-height: var(--touch-min);
  }
</style>
