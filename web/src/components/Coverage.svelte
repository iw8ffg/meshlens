<script lang="ts">
  import { coverageSession, deleteCoverage, patchCoverage, stopCoverage } from '../lib/api'
  import { formatLoss } from '../lib/coverage'
  import { formatDate } from '../lib/format'
  import { formatMeters } from '../lib/geo'
  import { applyCoverage, coverage } from '../lib/stores.svelte'
  import type { CoverageSession } from '../lib/types'
  import CoverageSetup from './CoverageSetup.svelte'
  import CoverageRestoreBox from './CoverageRestoreBox.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Modal from '../lib/ui/Modal.svelte'

  let { now }: { now: number } = $props()

  const active = $derived(coverage.sessions.find((s) => s.ended === null) ?? null)
  let prepared = $state(0) // cresce a ogni preparazione terminata: ricarica il riquadro di ripristino
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
      applyCoverage(await stopCoverage(s.id), null)
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
    {@const last = coverage.last?.id === active.id ? coverage.last : null}
    <Banner kind="ok" title="Prova in corso: {active.name}">
      {active.received} punti{#if active.missing !== null}, {active.missing} mancanti ({formatLoss(active)}){/if}{#if last && last.snr !== null}, ultimo SNR <span class="ui-mono">{last.snr}</span> dB{/if}, da {duration(active)}
      {#snippet action()}
        <Button kind="danger" icon="x" onclick={() => stop(active)}>Ferma</Button>
      {/snippet}
    </Banner>
  {/if}
  <CoverageRestoreBox reloadKey={coverage.sessions.filter((s) => s.ended !== null).length + (active ? 1000 : 0) + prepared * 10000} />
  <div class="bar">
    <Button kind="primary" icon="plus" disabled={!!active} onclick={() => (creating = !creating)}>Nuova prova</Button>
  </div>
  {#if creating && !active}
    <CoverageSetup onprepared={() => prepared++} />
  {/if}
  {#if error}<Banner kind="danger" title={error} />{/if}

  {#if opened}
    <Card>
      <section class="detail">
        <div><Button kind="ghost" icon="back" onclick={closeDetail}>Storico</Button></div>
        <Field label="Nome" for="cov-name">
          {#snippet children()}<input id="cov-name" class="ui-input" bind:value={name} />{/snippet}
        </Field>
        <Field label="Note" for="cov-notes">
          {#snippet children()}<textarea id="cov-notes" class="ui-input area" rows="3" bind:value={notes}></textarea>{/snippet}
        </Field>
        <p class="meta">
          {formatDate(opened.started)} · {duration(opened)} · {opened.received} punti · perdita {formatLoss(opened)} ·
          distanza max {dist(opened)}
        </p>
        <div class="row">
          <Button kind="primary" onclick={save}>Salva</Button>
          {#if opened.ended !== null}
            <Button kind="danger" icon="trash" onclick={() => (confirmDelete = true)}>Elimina</Button>
          {/if}
        </div>
      </section>
    </Card>
    <Modal open={confirmDelete} title="Eliminare la prova?" danger confirmLabel="Elimina" onconfirm={remove} oncancel={() => (confirmDelete = false)}>
      <p>Eliminare definitivamente questa prova? L'operazione non si può annullare.</p>
    </Modal>
  {:else}
    <h3>Storico</h3>
    {#if coverage.sessions.length === 0}
      <Empty icon="coverage" title="Nessuna prova registrata">Avvia una prova per vedere qui i risultati.</Empty>
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
  .cov { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  .hist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .hist button { width: 100%; min-height: var(--touch-min); text-align: left; padding: var(--space-3); border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-raised); color: var(--ink); font: 400 14px/20px var(--font-sans); cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
  .hist button:hover { border-color: var(--line-strong); }
  .hist small { color: var(--ink-muted); font-size: 13px; }
  .detail { display: flex; flex-direction: column; gap: var(--space-3); }
  .area { height: auto; padding: var(--space-2) var(--space-3); resize: vertical; }
  .meta { margin: 0; font: 400 13px/18px var(--font-sans); color: var(--ink-muted); }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  :global(.vp-phone) .hist small, :global(.vp-phone) .meta { font-size: 14px; line-height: 20px; }
</style>
