<script lang="ts">
  // WP4 (E3): stella copiata sulle radio e nodi ignorati da ripristinare. Nessuna prop (contratto §10.2).
  // Unica vista che mostra i nodi ignorati (eccezione prevista: non passa da visibleNodes).
  import { onDestroy, onMount } from 'svelte'
  import { ApiError, getJSON, send } from '../../lib/api'
  import { getIgnoredNodes, ignoredNodes, nodeName, setIgnored } from '../../lib/nodes'
  import type { AppSettings } from '../../lib/settings'
  import { app, upsertNodes } from '../../lib/stores.svelte'
  import { onWsResync } from '../../lib/wsext'
  import { t } from '../../lib/i18n/index.svelte'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Empty from '../../lib/ui/Empty.svelte'
  import Switch from '../../lib/ui/Switch.svelte'
  import type { Node } from '../../lib/types'

  let toRadio = $state(false)
  let loaded = $state(false)
  let saving = $state(false)
  let error = $state('')
  let fetched = $state<Node[]>([])
  let restoring = $state<string | null>(null)

  // nodi ignorati: dal server (anche quelli non in memoria) uniti allo stato attuale in memoria
  const list = $derived.by(() => {
    const byId = new Map<string, Node>()
    for (const n of fetched) byId.set(n.id, n)
    for (const n of app.nodes.values()) {
      if (byId.has(n.id) || n.is_ignored) byId.set(n.id, n)
    }
    return ignoredNodes(byId.values())
  })

  async function loadIgnored() {
    try {
      fetched = await getIgnoredNodes()
    } catch {
      /* resta l'elenco in memoria */
    }
  }

  onMount(async () => {
    try {
      const s = await getJSON<AppSettings>('/settings')
      toRadio = s.favorites_to_radio ?? false
      loaded = true
    } catch {
      error = t('nodeflags.settings.loadFailed')
    }
    await loadIgnored()
  })
  const offResync = onWsResync(() => void loadIgnored())
  onDestroy(offResync)

  async function saveToRadio(v: boolean) {
    saving = true
    error = ''
    try {
      await send<AppSettings>('PUT', '/settings', { favorites_to_radio: v })
    } catch (e) {
      toRadio = !v
      error = e instanceof ApiError ? e.message : t('nodeflags.settings.saveFailed')
    } finally {
      saving = false
    }
  }

  async function restore(n: Node) {
    restoring = n.id
    error = ''
    try {
      const res = await setIgnored(n.id, false)
      upsertNodes([res.node])
      fetched = fetched.filter((x) => x.id !== n.id)
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('nodeflags.failed')
    } finally {
      restoring = null
    }
  }
</script>

<Card>
  <section class="sec">
    <h3>{t('nodeflags.settings.title')}</h3>
    <Switch bind:checked={toRadio} disabled={!loaded || saving} label={t('nodeflags.settings.toRadio')} onchange={saveToRadio} />
    <p class="muted">{t('nodeflags.settings.toRadioHelp')}</p>

    <h4>{t('nodeflags.settings.ignoredTitle')}</h4>
    <p class="muted">{t('nodeflags.settings.ignoredHelp')}</p>
    {#if list.length === 0}
      <Empty icon="eye" title={t('nodeflags.settings.empty')}>
        <p>{t('nodeflags.settings.emptyHint')}</p>
      </Empty>
    {:else}
      <ul>
        {#each list as n (n.id)}
          <li>
            <span class="name">{nodeName(n)}</span>
            <span class="ui-mono id">{n.id}</span>
            <Button icon="refresh" disabled={restoring === n.id} onclick={() => restore(n)}>{t('nodeflags.settings.restore')}</Button>
          </li>
        {/each}
      </ul>
    {/if}
    {#if error}<Banner kind="danger" title={error} />{/if}
  </section>
</Card>

<style>
  .sec {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    color: var(--ink);
  }
  h3 {
    margin: 0;
    font: 600 15px/20px var(--font-sans);
  }
  h4 {
    margin: 0;
    font: 600 14px/20px var(--font-sans);
    color: var(--ink-muted);
  }
  .muted {
    margin: 0;
    color: var(--ink-muted);
    font: 400 13px/18px var(--font-sans);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-3);
    min-height: 44px;
    border-bottom: 1px solid var(--line);
    font-size: 14px;
  }
  .name {
    flex: 1;
    min-width: 120px;
    overflow-wrap: anywhere;
  }
  .id {
    color: var(--ink-muted);
  }
  :global(.vp-phone) .muted {
    font-size: 14px;
    line-height: 20px;
  }
</style>
