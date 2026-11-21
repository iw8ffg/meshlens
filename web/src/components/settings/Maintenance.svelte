<script lang="ts">
  import { onMount } from 'svelte'
  import { ApiError, getJSON, send } from '../../lib/api'
  import { bytes, exportUrl, integrityDamaged, reasonLabel, TABLE_LABELS, type BackupInfo, type DbInfo, type ImportResult } from '../../lib/maintenance'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Check from '../../lib/ui/Check.svelte'
  import Modal from '../../lib/ui/Modal.svelte'

  let info = $state<DbInfo | null>(null)
  let loadError = $state('')
  let error = $state('')
  let ok = $state('')
  let busy = $state(false)
  let confirming = $state(false)
  let backups = $state<BackupInfo[]>([])
  let restoring = $state<BackupInfo | null>(null)
  let restoreScheduled = $state(false)
  let isLocal = $state(false)
  let withSecrets = $state(false)
  let importMsg = $state('')

  const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

  async function load() {
    try {
      info = await getJSON<DbInfo>('/db')
      loadError = ''
    } catch (e) {
      loadError = errMsg(e, 'Statistiche del database non disponibili')
    }
  }

  async function loadBackups() {
    try {
      backups = await getJSON<BackupInfo[]>('/backups')
    } catch (e) {
      error = errMsg(e, 'Elenco dei backup non disponibile')
    }
  }

  onMount(() => {
    void load()
    void loadBackups()
    getJSON<{ is_local?: boolean }>('/auth/status')
      .then((a) => (isLocal = !!a.is_local))
      .catch(() => {})
  })

  async function createBackup() {
    error = ok = ''
    busy = true
    try {
      await send<BackupInfo>('POST', '/backups')
      ok = 'Backup creato'
      await loadBackups()
    } catch (e) {
      error = errMsg(e, 'Backup non riuscito')
    } finally {
      busy = false
    }
  }

  async function restore() {
    const b = restoring
    restoring = null
    if (!b) return
    error = ok = ''
    try {
      await send('POST', `/backups/${encodeURIComponent(b.name)}/restore`, { confirm: true })
      restoreScheduled = true
    } catch (e) {
      error = errMsg(e, 'Ripristino non riuscito')
    }
  }

  async function importFile(ev: Event) {
    const input = ev.currentTarget as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    if (!file) return
    error = ok = importMsg = ''
    try {
      const body = JSON.parse(await file.text())
      const r = await send<ImportResult>('POST', '/settings/import', body)
      importMsg =
        r.skipped.length > 0
          ? `Impostazioni importate. Valori non importati: ${r.skipped.join(', ')}.`
          : 'Impostazioni importate.'
    } catch (e) {
      error = e instanceof SyntaxError ? 'Il file non è un JSON valido' : errMsg(e, 'Importazione non riuscita')
    }
  }

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
    {#if info && integrityDamaged(info.integrity)}
      <Banner kind="danger" title="Il database risulta danneggiato: ripristina un backup" />
    {/if}
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
    <h3>Backup</h3>
    {#if restoreScheduled}
      <Banner kind="warn" title="Ripristino programmato: riavvia MeshLens per completarlo." />
    {/if}
    {#if backups.length === 0}
      <p class="muted">Nessun backup ancora. Se ne crea uno ogni settimana e prima di ogni aggiornamento.</p>
    {:else}
      <ul class="backups">
        {#each backups as b (b.name)}
          <li>
            <span>{when(b.time)} · {reasonLabel(b.reason)} · <span class="ui-mono">{bytes(b.size_bytes)}</span></span>
            <Button disabled={busy || restoreScheduled} onclick={() => (restoring = b)}>Ripristina</Button>
          </li>
        {/each}
      </ul>
    {/if}
    <div class="row">
      <Button disabled={busy} onclick={createBackup}>Crea backup ora</Button>
    </div>
    <h3>Impostazioni</h3>
    <div class="row">
      <a class="ui-btn" href={exportUrl(isLocal && withSecrets)} download>Esporta impostazioni</a>
      <label class="ui-btn file">
        Importa impostazioni
        <input type="file" accept="application/json,.json" onchange={importFile} />
      </label>
    </div>
    {#if isLocal}
      <Check bind:checked={withSecrets} label="Includi i segreti (password, token, chiavi) nell'esportazione" />
    {:else}
      <p class="muted">I segreti si possono esportare solo dal PC su cui gira MeshLens.</p>
    {/if}
    {#if importMsg}<Banner kind="ok" title={importMsg} />{/if}
    {#if error}<Banner kind="danger" title={error} />{/if}
    {#if ok}<Banner kind="ok" title={ok} />{/if}
  </section>
</Card>

<Modal
  open={restoring !== null}
  risk
  title="Ripristinare questo backup?"
  riskLabel="Ho capito, sostituisci i dati attuali"
  confirmLabel="Ripristina"
  onconfirm={restore}
  oncancel={() => (restoring = null)}
>
  <p>
    Il ripristino sostituisce tutti i dati attuali. Riavvia MeshLens per completarlo. Il PIN torna quello in
    uso al momento del backup e tutti i dispositivi, compreso questo, dovranno accedere di nuovo.
  </p>
</Modal>

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
  .backups { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .backups li { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); flex-wrap: wrap; font: 400 14px/20px var(--font-sans); }
  a.ui-btn { text-decoration: none; }
  .file input { display: none; }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
