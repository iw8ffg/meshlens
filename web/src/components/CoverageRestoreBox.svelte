<script lang="ts">
  import { ApiError, lastPlan, restorePlan } from '../lib/api'
  import { prepareStatus } from '../lib/coverage'
  import { configJobs } from '../lib/stores.svelte'
  import { t } from '../lib/i18n/index.svelte'
  import type { CoverageLastPlan, CoveragePlan } from '../lib/types'
  import CoveragePlanFlow from './CoveragePlanFlow.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'

  // reloadKey cambia a ogni avvio/fine prova: il riquadro si ricarica
  let { reloadKey = 0 }: { reloadKey?: number } = $props()

  let last = $state<CoverageLastPlan | null>(null)
  let plan = $state<CoveragePlan | null>(null)
  let busy = $state(false)
  let error = $state('')

  // stato (anche parziale) della preparazione, aggiornato dal WebSocket
  const status = $derived(
    last && last.jobs?.length
      ? prepareStatus({ steps: last.steps, jobs: last.jobs.map((j) => configJobs.get(j.id) ?? j) })
      : null,
  )

  async function load() {
    try {
      last = await lastPlan()
    } catch {
      /* riquadro non disponibile */
    }
  }
  $effect(() => {
    void reloadKey
    load()
  })

  async function start() {
    if (!last) return
    busy = true
    error = ''
    try {
      plan = await restorePlan(last.plan_id)
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('coverage.failedOp')
      // il server puo' aver segnato il piano come ripristinato (niente da rimettere)
      if (e instanceof ApiError && e.status === 400) load()
    } finally {
      busy = false
    }
  }
  function close() {
    plan = null
    load()
  }
</script>

{#if last}
  <Banner kind="warn" title={status ? t('coverage.restore.titleBusy') : t('coverage.restore.title')}>
    {#if status}
      <ul class="prog" aria-label={t('coverage.restore.statusAria')}>
        {#each status.nodes as n (n.node_id)}
          <li class={n.state}><b>{n.role}</b>: {n.text}</li>
        {/each}
      </ul>
      <span class:err={status.failed}>{status.summary}</span>
    {:else}
      <span>{t('coverage.restore.can')}</span>
    {/if}
    {#if !plan}<div class="act"><Button disabled={busy} onclick={start}>{t('coverage.restore.btn')}</Button></div>{/if}
    {#if error}<p class="err">{error}</p>{/if}
    {#if plan}
      {#key plan.plan_id}
        <CoveragePlanFlow {plan} kind="restore" oncancel={close} />
      {/key}
    {/if}
  </Banner>
{/if}

<style>
  .err, li.failed { color: var(--danger); margin: 0; }
  .prog { list-style: none; margin: 0; padding: 0; }
  li.ok { color: var(--ok); }
  li.mismatch { color: var(--warn); }
  .act { margin-top: var(--space-2); }
</style>
