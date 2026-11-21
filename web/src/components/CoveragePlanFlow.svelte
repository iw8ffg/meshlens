<script lang="ts">
  import { untrack } from 'svelte'
  import { ApiError, applyPlan, configJob } from '../lib/api'
  import { MASK, pathLabel } from '../lib/config'
  import { prepareStatus } from '../lib/coverage'
  import { app, configJobs, setConfigJob } from '../lib/stores.svelte'
  import type { CoveragePlan } from '../lib/types'

  // Il genitore lo monta con {#key plan.plan_id}: la conferma di rischio non passa mai a un altro piano.
  let {
    plan,
    kind,
    oncancel,
    onfinished,
  }: { plan: CoveragePlan; kind: 'prepare' | 'restore'; oncancel: () => void; onfinished?: () => void } = $props()

  let understood = $state(false)
  let busy = $state(false)
  let error = $state('')
  let jobIds = $state<number[]>([])

  const risky = $derived(plan.steps.some((s) => s.preview.risky))
  const empty = $derived(plan.steps.every((s) => s.preview.changes.length === 0))
  const started = $derived(jobIds.length > 0)
  const status = $derived(
    prepareStatus({ steps: plan.steps, jobs: jobIds.map((id) => configJobs.get(id) ?? null) }, kind),
  )

  let notified = false
  $effect(() => {
    if (started && status.finished && !notified) {
      notified = true
      untrack(() => onfinished?.())  // il genitore puo' leggere e scrivere il proprio stato
    }
  })

  // Rilegge i lavori non terminati (il WebSocket puo' aver perso aggiornamenti)
  async function refresh() {
    for (const id of jobIds) {
      const cur = configJobs.get(id)
      if (cur && cur.status !== 'running') continue
      try {
        setConfigJob(await configJob(id))
      } catch {
        /* riprova al prossimo giro */
      }
    }
  }
  // dopo una riconnessione del WebSocket
  $effect(() => {
    void app.reconnects
    if (untrack(() => jobIds.length) > 0) untrack(refresh)
  })
  // ogni 5 s finche' qualche lavoro e' in corso
  $effect(() => {
    if (!started) return
    const t = setInterval(() => {
      if (!status.finished) void refresh()
    }, 5000)
    return () => clearInterval(t)
  })

  const show = (v: unknown) => {
    if (v === null || v === undefined) return '–'
    if (v === MASK) return MASK
    return typeof v === 'object' ? JSON.stringify(v) : String(v)
  }
  const roleOf = (role: string) => (role === 'mobile' ? 'Mobile' : 'Base')

  async function apply() {
    busy = true
    error = ''
    try {
      const r = await applyPlan(plan.plan_id, risky && understood)
      for (const j of r.jobs) setConfigJob(j)
      jobIds = r.jobs.map((j) => j.id)
    } catch (e) {
      error = e instanceof ApiError ? e.message : 'Operazione non riuscita'
    } finally {
      busy = false
    }
  }
</script>

<div class="flow">
  <h4>{kind === 'prepare' ? 'Anteprima: prepara le radio' : 'Anteprima: ripristina la configurazione'}</h4>
  {#each plan.steps as s (s.node_id)}
    <div class="step">
      <b>{roleOf(s.role)}</b> <small>{s.node_id}</small>
      {#if s.preview.changes.length === 0}
        <p class="muted">Nessuna modifica.</p>
      {:else}
        <table>
          <thead><tr><th>Campo</th><th>Attuale</th><th>Nuovo</th></tr></thead>
          <tbody>
            {#each s.preview.changes as c (c.path)}
              <tr class:risky={c.risky}>
                <td>
                  {pathLabel(c.path)}
                  {#if c.risky}<br /><small class="why">A rischio{c.reason ? `: ${c.reason}` : ''}</small>{/if}
                </td>
                <td>{show(c.old)}</td>
                <td>{show(c.new)}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
      <p class="muted">Prima di scrivere viene salvata una copia di: {s.preview.backup_sections.join(', ') || '–'}.</p>
    </div>
  {/each}

  {#if !started}
    {#if risky}
      <label class="ack">
        <input type="checkbox" bind:checked={understood} />
        Ho capito che queste modifiche possono isolare le radio dalla rete
      </label>
    {/if}
    <div class="btns">
      <button class="go" disabled={busy || empty || (risky && !understood)} onclick={apply}>Applica</button>
      <button onclick={oncancel}>Annulla</button>
    </div>
  {:else}
    <ul class="prog" aria-label="Avanzamento">
      {#each status.nodes as n (n.node_id)}
        <li class={n.state}><b>{n.role}</b>: {n.text}</li>
      {/each}
    </ul>
    <p class:err={status.failed} class="sum">{status.summary}</p>
    {#if status.finished}<button onclick={oncancel}>Chiudi</button>{/if}
  {/if}
  {#if error}<p class="err">{error}</p>{/if}
</div>

<style>
  .flow {
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  h4,
  p {
    margin: 0;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th,
  td {
    text-align: left;
    padding: 4px;
    border-bottom: 1px solid #1f2937;
    vertical-align: top;
    word-break: break-all;
  }
  tr.risky td {
    background: rgba(239, 68, 68, 0.15);
  }
  .why,
  .err,
  li.failed {
    color: #f87171;
  }
  .muted {
    color: #9ca3af;
    font-size: 12px;
  }
  .ack {
    display: flex;
    gap: 8px;
    align-items: center;
    color: #f87171;
  }
  .btns {
    display: flex;
    gap: 6px;
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
    font: inherit;
    padding: 6px 12px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 4px;
    cursor: pointer;
  }
  button.go {
    background: #2563eb;
    border-color: #2563eb;
    color: #fff;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
