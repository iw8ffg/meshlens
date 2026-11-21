<script lang="ts">
  import { ApiError, lastPlan, restorePlan } from '../lib/api'
  import type { CoverageLastPlan, CoveragePlan } from '../lib/types'
  import CoveragePlanFlow from './CoveragePlanFlow.svelte'

  // reloadKey cambia a ogni avvio/fine prova: il riquadro si ricarica
  let { reloadKey = 0 }: { reloadKey?: number } = $props()

  let last = $state<CoverageLastPlan | null>(null)
  let plan = $state<CoveragePlan | null>(null)
  let busy = $state(false)
  let error = $state('')

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
    <span>Radio preparate per la prova.</span>
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
  .err {
    color: #f87171;
    margin: 0;
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
