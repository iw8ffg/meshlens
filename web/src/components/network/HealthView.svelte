<script module lang="ts">
  // La vista «Salute» compare in NetworkPage solo con ready = true.
  export const ready: boolean = true
</script>

<script lang="ts">
  // Salute della rete (E11): batterie in calo con autonomia stimata dal server, tendenza dei nodi
  // solari, tensione/corrente/uptime e confronto di 2–3 nodi sullo stesso grafico.
  import { onDestroy, onMount, untrack } from 'svelte'
  import { ApiError } from '../../lib/api'
  import { levelOf, statusLabel, statusTone, uptimeLabel } from '../../lib/autonomy'
  import { COMPARE_MAX, healthBatteries, splitHealth, toggleCompare } from '../../lib/health'
  import { ago, num } from '../../lib/format'
  import { t, tn } from '../../lib/i18n/index.svelte'
  import { app } from '../../lib/stores.svelte'
  import type { HealthNode, HealthResponse } from '../../lib/types'
  import { onWsResync } from '../../lib/wsext'
  import Banner from '../../lib/ui/Banner.svelte'
  import BatteryBadge from '../../lib/ui/BatteryBadge.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Check from '../../lib/ui/Check.svelte'
  import Empty from '../../lib/ui/Empty.svelte'
  import Segmented from '../../lib/ui/Segmented.svelte'
  import NodeCompare from '../NodeCompare.svelte'

  let { onpick }: { onpick?: (nodeId: string) => void } = $props()

  const OTHERS_COLLAPSE_AFTER = 8

  let scope = $state<'mine' | 'all'>('mine')
  let data = $state<HealthResponse | null>(null)
  let loading = $state(false)
  let failed = $state('')
  let compareIds = $state<string[]>([])
  let showOthers = $state(true)
  let now = $state(Date.now() / 1000)
  let alive = true
  let seq = 0

  const groups = $derived(data ? splitHealth(data.nodes) : { attention: [], others: [] })
  const names = $derived(new Map((data?.nodes ?? []).map((n) => [n.node_id, n.name])))
  const scopeItems = $derived([
    { value: 'mine' as const, label: t('health.scope.mine') },
    { value: 'all' as const, label: t('health.scope.all') },
  ])

  async function load(s: 'mine' | 'all') {
    const mine = ++seq
    loading = true
    failed = ''
    try {
      const r = await healthBatteries(s)
      if (!alive || mine !== seq) return
      data = r
      now = Date.now() / 1000
      showOthers = splitHealth(r.nodes).others.length <= OTHERS_COLLAPSE_AFTER
      // stesso array se nulla cambia: NodeCompare non deve riscaricare tutto a ogni risincronizzazione
      const kept = compareIds.filter((id) => r.nodes.some((n) => n.node_id === id))
      if (kept.length !== compareIds.length) compareIds = kept
    } catch (e) {
      if (!alive || mine !== seq) return
      failed = e instanceof ApiError ? e.message : t('health.loadFailed')
    } finally {
      if (alive && mine === seq) loading = false
    }
  }

  // carica all'apertura e a ogni cambio di ambito (nessun polling continuo)
  $effect(() => {
    const s = scope
    untrack(() => void load(s))
  })

  let offResync: (() => void) | null = null
  onMount(() => {
    offResync = onWsResync(() => void load(scope))
  })
  onDestroy(() => {
    alive = false
    offResync?.()
  })

  const pick = (id: string) => (onpick ? onpick(id) : (app.selectedId = id))
  const selected = (n: HealthNode) => compareIds.includes(n.node_id)
  const toggle = (id: string) => (compareIds = toggleCompare(compareIds, id))
</script>

{#snippet row(n: HealthNode)}
  {@const tone = statusTone(n)}
  {@const lvl = levelOf(n)}
  <li class="row">
    <div class="head">
      <button type="button" class="name" onclick={() => pick(n.node_id)}>{n.name}</button>
      {#if lvl !== null || n.status === 'external'}<BatteryBadge pct={lvl ?? 0} usb={n.status === 'external'} />{/if}
      <span class="st {tone}">{statusLabel(n)}</span>
      {#if n.solar}<span class="ui-hint">{t('health.solar')}</span>{/if}
    </div>
    <dl class="stats">
      <div><dt>{t('health.col.voltage')}</dt><dd>{n.voltage === null ? '—' : `${num(n.voltage, 2)} V`}</dd></div>
      <div><dt>{t('health.col.current')}</dt><dd>{n.current_ma === null ? '—' : `${num(n.current_ma, 0)} mA`}</dd></div>
      <div><dt>{t('health.col.uptime')}</dt><dd>{uptimeLabel(n.uptime_s)}{#if n.reboots > 0} · {tn('health.reboots', n.reboots)}{/if}</dd></div>
    </dl>
    <!-- svelte-ignore a11y_no_static_element_interactions -->
    <div class="cmp" onchange={() => toggle(n.node_id)}>
      <Check checked={selected(n)} disabled={!selected(n) && compareIds.length >= COMPARE_MAX} label={t('health.compare.select', { name: n.name })} />
    </div>
  </li>
{/snippet}

<div class="page">
  <div class="top">
    <Segmented items={scopeItems} bind:value={scope} label={t('health.scopeAria')} />
    <Button icon="refresh" disabled={loading} onclick={() => load(scope)}>{t('health.refresh')}</Button>
  </div>
  <p class="ui-hint">
    {t('health.window')}{#if data} · {t('health.updated', { when: ago(Math.max(0, (now - data.generated) / 60)) })}{/if}
  </p>

  {#if failed}
    <Banner kind="danger" title={failed} />
  {:else if !data}
    <p class="ui-hint">{t('shell.loading')}</p>
  {:else if data.nodes.length === 0}
    <Empty icon="battery" title={t('health.none')} />
  {:else}
    {#if data.truncated}<p class="ui-hint">{t('health.truncated')}</p>{/if}
    {#if groups.attention.length > 0}
      <h3>{t('health.attention')}</h3>
      <ul class="list">
        {#each groups.attention as n (n.node_id)}{@render row(n)}{/each}
      </ul>
    {/if}
    {#if groups.others.length > 0}
      <h3>
        <button type="button" class="fold" aria-expanded={showOthers} onclick={() => (showOthers = !showOthers)}>{t('health.others')} ({groups.others.length})</button>
      </h3>
      {#if showOthers}
        <ul class="list">
          {#each groups.others as n (n.node_id)}{@render row(n)}{/each}
        </ul>
      {/if}
    {/if}

    <h3>{t('health.compare.title')}</h3>
    {#if compareIds.length >= 2}
      <NodeCompare nodeIds={compareIds} nodes={names} />
    {:else}
      <p class="ui-hint">{t('health.compare.pick')}</p>
    {/if}
    {#if compareIds.length >= COMPARE_MAX}<p class="ui-hint">{t('health.compare.max')}</p>{/if}
  {/if}
</div>

<style>
  .page { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-3); color: var(--ink); overflow-y: auto; }
  .top { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; justify-content: space-between; }
  h3 { margin: var(--space-2) 0 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .row { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-2) var(--space-3); border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface); }
  .head { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
  .name { background: none; border: 0; padding: 0; min-height: var(--touch-min); color: var(--accent-ink); font: 600 14px/20px var(--font-sans); cursor: pointer; text-align: left; overflow-wrap: anywhere; }
  .name:focus-visible, .fold:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .st { font: 500 14px/20px var(--font-sans); color: var(--ink-muted); }
  .st.warn { color: var(--warn); }
  .st.ok { color: var(--ok); }
  .stats { display: flex; gap: var(--space-4); flex-wrap: wrap; margin: 0; font: 400 13px/18px var(--font-sans); }
  .stats div { display: flex; gap: var(--space-1); }
  dt { color: var(--ink-muted); }
  dd { margin: 0; }
  .fold { background: none; border: 0; padding: 0; min-height: var(--touch-min); color: inherit; font: inherit; cursor: pointer; }
  :global(.vp-phone) .stats, :global(.vp-phone) .ui-hint { font-size: 14px; line-height: 20px; }
  :global(.vp-phone) .stats { flex-direction: column; gap: var(--space-1); }
</style>
