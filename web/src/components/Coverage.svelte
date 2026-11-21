<script lang="ts">
  import { coverageSession, deleteCoverage, patchCoverage, stopCoverage } from '../lib/api'
  import { formatLoss } from '../lib/coverage'
  import { formatDate } from '../lib/format'
  import { formatMeters } from '../lib/geo'
  import { coverage } from '../lib/stores.svelte'
  import type { CoverageSession } from '../lib/types'
  import CoverageSetup from './CoverageSetup.svelte'

  let { now }: { now: number } = $props()

  const active = $derived(coverage.sessions.find((s) => s.ended === null) ?? null)
  let creating = $state(false)
  let error = $state('')
  let name = $state('')
  let notes = $state('')
  let confirmDelete = $state(false)

  const duration = (s: CoverageSession) => {
    const m = Math.max(0, Math.round(((s.ended ?? now) - s.started) / 60))
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`
  }
  const dist = (s: CoverageSession) => (s.max_distance_m === null ? '—' : formatMeters(s.max_distance_m))
  const msg = (e: unknown) => (e instanceof Error ? e.message : 'Errore')

  // Chiude il modulo di avvio quando parte una sessione
  $effect(() => {
    if (active) creating = false
  })

  async function stop(s: CoverageSession) {
    error = ''
    try {
      await stopCoverage(s.id)
    } catch (e) {
      error = msg(e)
    }
  }

  async function open(s: CoverageSession) {
    coverage.openId = s.id
    confirmDelete = false
    name = s.name
    notes = s.notes
    error = ''
    try {
      const d = await coverageSession(s.id)
      if (coverage.openId === s.id) coverage.detail = d
    } catch (e) {
      error = msg(e)
    }
  }

  function closeDetail() {
    coverage.openId = null
    coverage.detail = null
  }

  async function save() {
    const id = coverage.openId
    if (id === null) return
    error = ''
    try {
      const s = await patchCoverage(id, { name: name.trim() || undefined, notes })
      const i = coverage.sessions.findIndex((x) => x.id === id)
      if (i >= 0) coverage.sessions[i] = s
      if (coverage.detail?.id === id) coverage.detail = { ...coverage.detail, ...s }
    } catch (e) {
      error = msg(e)
    }
  }

  async function remove() {
    const id = coverage.openId
    if (id === null) return
    error = ''
    try {
      await deleteCoverage(id)
      coverage.sessions = coverage.sessions.filter((s) => s.id !== id)
      closeDetail()
      confirmDelete = false
    } catch (e) {
      error = msg(e)
    }
  }

  const opened = $derived(coverage.sessions.find((s) => s.id === coverage.openId) ?? null)
</script>

<div class="cov">
  {#if active}
    {@const last = coverage.detail?.id === active.id ? coverage.detail.points.at(-1) : undefined}
    <div class="running">
      <span>
        In corso: <b>{active.name}</b> — {active.received} punti{#if active.missing !== null}, {active.missing}
          mancanti ({formatLoss(active)}){/if}{#if last && last.snr !== null}, ultimo SNR {last.snr} dB{/if}, da {duration(active)}
      </span>
      <button class="stop" onclick={() => stop(active)}>Ferma</button>
    </div>
  {/if}
  <div class="bar">
    <button disabled={!!active} onclick={() => (creating = !creating)}>Nuova prova</button>
  </div>
  {#if creating && !active}
    <CoverageSetup />
  {/if}
  {#if error}<p class="err">{error}</p>{/if}

  {#if opened}
    <section class="detail">
      <button class="ghost" onclick={closeDetail}>← Storico</button>
      <label>
        Nome
        <input bind:value={name} />
      </label>
      <label>
        Note
        <textarea rows="3" bind:value={notes}></textarea>
      </label>
      <p class="meta">
        {formatDate(opened.started)} · {duration(opened)} · {opened.received} punti · perdita {formatLoss(opened)} ·
        distanza max {dist(opened)}
      </p>
      <div class="row">
        <button onclick={save}>Salva</button>
        {#if opened.ended !== null}
          {#if confirmDelete}
            <span>Eliminare definitivamente questa prova?</span>
            <button class="stop" onclick={remove}>Elimina</button>
            <button class="ghost" onclick={() => (confirmDelete = false)}>Annulla</button>
          {:else}
            <button class="stop" onclick={() => (confirmDelete = true)}>Elimina</button>
          {/if}
        {/if}
      </div>
    </section>
  {:else}
    <h3>Storico</h3>
    {#if coverage.sessions.length === 0}
      <p class="empty">Nessuna prova registrata.</p>
    {:else}
      <ul class="hist">
        {#each coverage.sessions as s (s.id)}
          <li>
            <button onclick={() => open(s)}>
              <b>{s.name}</b>
              <small>
                {formatDate(s.started)} · {duration(s)} · {s.received} punti · perdita {formatLoss(s)} · max {dist(s)}{s.ended === null ? ' · in corso' : ''}
              </small>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
</div>

<style>
  .cov {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 8px 0;
  }
  .running {
    margin: 0 12px;
    padding: 8px;
    border: 1px solid #2e9d4b;
    border-radius: 6px;
    display: flex;
    gap: 8px;
    align-items: center;
    justify-content: space-between;
    font-size: 0.9em;
  }
  .bar,
  h3,
  .empty,
  .err,
  .hist {
    margin: 0 12px;
  }
  h3 {
    font-size: 1em;
  }
  .empty {
    color: #9ca3af;
  }
  .err {
    color: #f87171;
  }
  button {
    padding: 8px 10px;
    border: 0;
    border-radius: 6px;
    background: #2563eb;
    color: #fff;
    font: inherit;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .stop {
    background: #c8382e;
  }
  .ghost {
    background: #374151;
  }
  .hist {
    list-style: none;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .hist button {
    width: 100%;
    text-align: left;
    background: #1f2937;
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .hist small {
    color: #9ca3af;
  }
  .detail {
    margin: 0 12px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  .detail label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.9em;
  }
  .detail input,
  .detail textarea {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 4px;
    padding: 6px;
    font: inherit;
  }
  .meta {
    margin: 0;
    font-size: 0.85em;
    color: #9ca3af;
  }
  .row {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
  }
</style>
