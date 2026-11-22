<script lang="ts">
  import { untrack } from 'svelte'
  import { ApiError, traceroute, traceroutes } from '../lib/api'
  import { formatDate, signed } from '../lib/format'
  import { t } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Select from '../lib/ui/Select.svelte'
  import { app, setTraceroute } from '../lib/stores.svelte'
  import { mergeHistory } from '../lib/traceroute'
  import type { Node, Traceroute, TracerouteHop } from '../lib/types'

  let { node }: { node: Node } = $props()

  const connected = $derived(app.radios.filter((r) => r.state === 'connected'))
  let radioId = $state('')
  let busy = $state(false)
  let error = $state('')
  let history = $state<Traceroute[]>([])

  const current = $derived(app.traceroutes.get(node.id) ?? null)

  // Un esito finale arrivato dallo store entra nello storico (sostituisce la voce con lo stesso id)
  $effect(() => {
    const c = app.traceroutes.get(node.id)
    if (!c || c.status === 'pending') return
    // lettura senza dipendenza: l'effetto scrive history e non deve riattivarsi da solo
    const current = untrack(() => history)
    const next = mergeHistory(current, c)
    if (next !== current) history = next
  })

  // Una radio scelta che si scollega torna ad "automatica"
  $effect(() => {
    if (radioId && !connected.some((r) => r.id === radioId)) radioId = ''
  })

  // Storico del nodo e semina dello store col piu' recente
  // (un esito arrivato a WebSocket giu' non resta "pending")
  function refresh(id: string) {
    traceroutes(id)
      .then((list) => {
        if (id !== node.id) return
        history = list
        const latest = [...list].sort((a, b) => b.time - a.time || b.id - a.id)[0]
        const have = app.traceroutes.get(id)
        if (latest && (!have || latest.id >= have.id)) setTraceroute(latest)
      })
      .catch(() => {
        /* lo storico e' accessorio */
      })
  }

  // All'apertura del nodo
  $effect(() => {
    const id = node.id
    error = ''
    history = []
    refresh(id)
  })

  // Riconnessione del WebSocket: l'esito finale potrebbe essersi perso
  let seenReconnects = app.reconnects
  $effect(() => {
    const n = app.reconnects
    if (n === seenReconnects) return
    seenReconnects = n
    refresh(node.id)
  })

  // Ancora "pending" dopo 65 s (oltre il timeout del server): ricarica dal server
  $effect(() => {
    const id = node.id
    const c = app.traceroutes.get(id)
    if (c?.status !== 'pending') return
    const timer = setTimeout(() => refresh(id), 65_000)
    return () => clearTimeout(timer)
  })

  async function run() {
    busy = true
    error = ''
    const id = node.id
    try {
      setTraceroute(await traceroute(id, radioId || undefined))
    } catch (e) {
      if (id === node.id) error = e instanceof ApiError ? e.message : t('nodes.tr.failedRun')
    } finally {
      busy = false
    }
  }

  function name(id: string): string {
    const n = app.nodes.get(id)
    return n?.short_name || n?.long_name || id
  }

  function snr(v: number | null): string {
    if (v === null) return '? dB'
    return `${signed(v, 1)} dB`
  }

  /** `Base → Rip1 (6 dB) → Nodo (−1 dB)`: SNR con cui ogni salto e' stato ricevuto. */
  function path(hops: TracerouteHop[]): string {
    if (hops.length === 0) return '–'
    return hops.map((h, i) => (i === 0 ? name(h.id) : `${name(h.id)} (${snr(h.snr)})`)).join(' → ')
  }

  function failure(tr: Traceroute): string {
    if (tr.status === 'timeout') return t('nodes.tr.timeout')
    return tr.error ? t('nodes.tr.failedWith', { error: translateServer(tr.error) }) : t('nodes.tr.failed')
  }

  const pending = $derived(busy || current?.status === 'pending')
  const older = $derived(history.filter((h) => h.id !== current?.id))
</script>

<h3>{t('nodes.tr.title')}</h3>
<div class="row">
  <Button icon="route" disabled={connected.length === 0 || pending} onclick={run}>{pending ? t('nodes.tr.running') : t('nodes.tr.title')}</Button>
  {#if connected.length > 1}
    <Select bind:value={radioId} aria-label={t('nodes.tr.radioAria')}>
      <option value="">{t('nodes.tr.radioAuto')}</option>
      {#each connected as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
    </Select>
  {/if}
</div>
{#if connected.length === 0}<p class="none">{t('nodes.tr.connectRadio')}</p>{/if}
{#if error}<div class="gap"><Banner kind="danger" title={error} /></div>{/if}
{#if pending}
  <p class="none" role="status">{t('nodes.tr.runningMax')}</p>
{:else if current}
  {#if current.status === 'ok'}
    <p class="res"><b>{t('nodes.tr.forward')}</b> {path(current.forward)}</p>
    <p class="res"><b>{t('nodes.tr.back')}</b> {path(current.back)}</p>
  {:else}
    <div class="gap"><Banner kind="warn" title={failure(current)} /></div>
  {/if}
{/if}
{#if older.length > 0}
  <ul class="hist">
    {#each older as h (h.id)}
      <li>
        <span class="when ui-mono">{formatDate(h.time)}</span>
        {#if h.status === 'ok'}
          {path(h.forward)}
        {:else if h.status === 'pending'}
          {t('nodes.tr.running')}
        {:else}
          {failure(h)}
        {/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  h3 {
    font: 600 14px/20px var(--font-sans);
    margin: var(--space-4) 0 var(--space-2);
  }
  .row {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    flex-wrap: wrap;
  }
  .row :global(.ui-select) {
    width: auto;
    min-width: 160px;
  }
  .gap {
    margin: var(--space-2) 0;
  }
  .none {
    margin: var(--space-2) 0;
    font-size: 13px;
    color: var(--ink-muted);
  }
  .res {
    font-size: 13px;
    margin: var(--space-2) 0;
    word-break: break-word;
    color: var(--ink);
  }
  .hist {
    list-style: none;
    margin: var(--space-2) 0;
    padding: 0;
    font-size: 12px;
    color: var(--ink-muted);
  }
  .hist li {
    margin-bottom: var(--space-1);
  }
  .when {
    margin-right: var(--space-2);
  }
  :global(.vp-phone) .none,
  :global(.vp-phone) .res,
  :global(.vp-phone) .hist {
    font-size: 14px;
  }
</style>
