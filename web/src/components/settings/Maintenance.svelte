<script lang="ts">
  import { onMount } from 'svelte'
  import { ApiError, getJSON, send } from '../../lib/api'
  import { bytes, TABLE_LABELS, type DbInfo } from '../../lib/maintenance'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Modal from '../../lib/ui/Modal.svelte'

  let info = $state<DbInfo | null>(null)
  let loadError = $state('')
  let error = $state('')
  let ok = $state('')
  let busy = $state(false)
  let confirming = $state(false)

  const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

  async function load() {
    try {
      info = await getJSON<DbInfo>('/db')
      loadError = ''
    } catch (e) {
      loadError = errMsg(e, 'Statistiche del database non disponibili')
    }
  }

  onMount(() => void load())

  async function compact() {
    confirming = false
    error = ok = ''
    busy = true
    try {
      const r = await send<{ before_bytes: number; after_bytes: number }>('POST', '/db/compact', { confirm: true })
      ok = `Database compattato: da ${bytes(r.before_bytes)} a ${bytes(r.after_bytes)}`
      await load()
    } catch (e) {
      error = errMsg(e, 'Compattazione non riuscita')
    } finally {
      busy = false
    }
  }

  const when = (t: number) => new Date(t * 1000).toLocaleString('it-IT')
  const deletedTotal = (d: Record<string, number>) => Object.values(d).reduce((a, b) => a + b, 0)
</script>

<Card>
  <section class="sec">
    <h3>Database e backup</h3>
    {#if loadError}<Banner kind="danger" title={loadError} />{/if}
    {#if info}
      <dl class="stats">
        <div><dt>Dimensione</dt><dd class="ui-mono">{bytes(info.size_bytes)}</dd></div>
        <div><dt>Spazio libero</dt><dd class="ui-mono">{bytes(info.free_bytes)}</dd></div>
        {#each Object.entries(info.rows) as [table, n] (table)}
          <div><dt>{TABLE_LABELS[table] ?? table}</dt><dd class="ui-mono">{n.toLocaleString('it-IT')}</dd></div>
        {/each}
      </dl>
      <p class="line">
        Ultima pulizia:
        {#if info.last_purge}
          {when(info.last_purge.time)} ({deletedTotal(info.last_purge.deleted).toLocaleString('it-IT')} righe rimosse)
        {:else}
          non ancora eseguita
        {/if}
      </p>
    {/if}
    <div class="row">
      <Button disabled={busy} onclick={() => (confirming = true)}>Compatta database</Button>
    </div>
    <p class="muted">Restituisce al disco lo spazio delle righe cancellate.</p>
    {#if error}<Banner kind="danger" title={error} />{/if}
    {#if ok}<Banner kind="ok" title={ok} />{/if}
  </section>
</Card>

<Modal
  open={confirming}
  risk
  title="Compattare il database?"
  riskLabel="Ho capito, avvia la compattazione"
  confirmLabel="Compatta"
  onconfirm={compact}
  oncancel={() => (confirming = false)}
>
  <p>L'interfaccia resterà ferma durante la compattazione: con un database grande può servire un minuto.</p>
</Modal>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .line { font: 400 14px/20px var(--font-sans); }
  .stats { margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: var(--space-2) var(--space-4); }
  .stats div { display: flex; justify-content: space-between; gap: var(--space-2); font: 400 14px/20px var(--font-sans); }
  dt { color: var(--ink-muted); }
  dd { margin: 0; }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
