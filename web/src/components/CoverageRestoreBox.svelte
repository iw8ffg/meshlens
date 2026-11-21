<script lang="ts">
  import { ApiError, lastPlan, restorePlan } from '../lib/api'
  import { prepareStatus } from '../lib/coverage'
  import { configJobs } from '../lib/stores.svelte'
  import type { CoverageLastPlan, CoveragePlan } from '../lib/types'
  import CoveragePlanFlow from './CoveragePlanFlow.svelte'

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
      error = e instanceof ApiError ? e.message : 'Operazione non riuscita'
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
  <div class="box">
    {#if status}
      <ul class="prog" aria-label="Stato della preparazione">
        {#each status.nodes as n (n.node_id)}
          <li class={n.state}><b>{n.role}</b>: {n.text}</li>
        {/each}
      </ul>
      <span class:err={status.failed}>{status.summary}</span>
    {:else}
      <span>Radio preparate per la prova.</span>
    {/if}
    {#if !plan}<button disabled={busy} onclick={start}>Ripristina configurazione</button>{/if}
    {#if error}<p class="err">{error}</p>{/if}
    {#if plan}
      {#key plan.plan_id}
        <CoveragePlanFlow {plan} kind="restore" oncancel={close} />
      {/key}
    {/if}
  </div>
{/if}

<style>
  .box {
    margin: 0 12px;
    padding: 8px;
    border: 1px solid #d9a400;
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 0.9em;
  }
  .err,
  li.failed {
    color: #f87171;
    margin: 0;
  }
  .prog {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li.ok {
    color: #2e9d4b;
  }
  li.mismatch {
    color: #d9a400;
  }
  button {
    padding: 8px 10px;
    border: 0;
    border-radius: 6px;
    background: #2563eb;
    color: #fff;
    font: inherit;
    cursor: pointer;
    align-self: flex-start;
  }
  button:disabled {
    opacity: 0.5;
  }
</style>
