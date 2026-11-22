<script lang="ts">
  import { locale, t } from '../../lib/i18n/index.svelte'
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
      loadError = errMsg(e, t('settings.db.statsFailed'))
    }
  }

  async function loadBackups() {
    try {
      backups = await getJSON<BackupInfo[]>('/backups')
    } catch (e) {
      error = errMsg(e, t('settings.db.listFailed'))
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
      ok = t('settings.db.created')
      await loadBackups()
    } catch (e) {
      error = errMsg(e, t('settings.db.backupFailed'))
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
      error = errMsg(e, t('settings.db.restoreFailed'))
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
          ? t('settings.db.importedSkipped', { list: r.skipped.join(', ') })
          : t('settings.db.imported')
    } catch (e) {
      error = e instanceof SyntaxError ? t('settings.db.badJson') : errMsg(e, t('settings.db.importFailed'))
    }
  }

  async function compact() {
    confirming = false
    error = ok = ''
    busy = true
    try {
      const r = await send<{ before_bytes: number; after_bytes: number }>('POST', '/db/compact', { confirm: true })
      ok = t('settings.db.compacted', { from: bytes(r.before_bytes), to: bytes(r.after_bytes) })
      await load()
    } catch (e) {
      error = errMsg(e, t('settings.db.compactFailed'))
    } finally {
      busy = false
    }
  }

  const when = (ts: number) => new Date(ts * 1000).toLocaleString(locale())
  const deletedTotal = (d: Record<string, number>) => Object.values(d).reduce((a, b) => a + b, 0)
</script>

<Card>
  <section class="sec">
    <h3>{t('settings.db.title')}</h3>
    {#if loadError}<Banner kind="danger" title={loadError} />{/if}
    {#if info && integrityDamaged(info.integrity)}
      <Banner kind="danger" title={t('settings.db.damaged')} />
    {/if}
    {#if info}
      <dl class="stats">
        <div><dt>{t('settings.db.size')}</dt><dd class="ui-mono">{bytes(info.size_bytes)}</dd></div>
        <div><dt>{t('settings.db.free')}</dt><dd class="ui-mono">{bytes(info.free_bytes)}</dd></div>
        {#each Object.entries(info.rows) as [table, n] (table)}
          <div><dt>{TABLE_LABELS[table] ?? table}</dt><dd class="ui-mono">{n.toLocaleString(locale())}</dd></div>
        {/each}
      </dl>
      <p class="line">
        {t('settings.db.lastPurge')}
        {#if info.last_purge}
          {t('settings.db.purged', { when: when(info.last_purge.time), n: deletedTotal(info.last_purge.deleted).toLocaleString(locale()) })}
        {:else}
          {t('settings.db.neverPurged')}
        {/if}
      </p>
    {/if}
    <div class="row">
      <Button disabled={busy} onclick={() => (confirming = true)}>{t('settings.db.compact')}</Button>
    </div>
    <p class="muted">{t('settings.db.compactNote')}</p>
    <h3>{t('settings.db.backups')}</h3>
    {#if restoreScheduled}
      <Banner kind="warn" title={t('settings.db.restoreScheduled')} />
    {/if}
    {#if backups.length === 0}
      <p class="muted">{t('settings.db.noBackups')}</p>
    {:else}
      <ul class="backups">
        {#each backups as b (b.name)}
          <li>
            <span>{when(b.time)} · {reasonLabel(b.reason)} · <span class="ui-mono">{bytes(b.size_bytes)}</span></span>
            <Button disabled={busy || restoreScheduled} onclick={() => (restoring = b)}>{t('settings.db.restore')}</Button>
          </li>
        {/each}
      </ul>
    {/if}
    <div class="row">
      <Button disabled={busy} onclick={createBackup}>{t('settings.db.create')}</Button>
    </div>
    <h3>{t('settings.db.settings')}</h3>
    <div class="row">
      <a class="ui-btn" href={exportUrl(isLocal && withSecrets)} download>{t('settings.db.export')}</a>
      <label class="ui-btn file">
        {t('settings.db.import')}
        <input type="file" accept="application/json,.json" onchange={importFile} />
      </label>
    </div>
    {#if isLocal}
      <Check bind:checked={withSecrets} label={t('settings.db.withSecrets')} />
    {:else}
      <p class="muted">{t('settings.db.secretsLocal')}</p>
    {/if}
    {#if importMsg}<Banner kind="ok" title={importMsg} />{/if}
    {#if error}<Banner kind="danger" title={error} />{/if}
    {#if ok}<Banner kind="ok" title={ok} />{/if}
  </section>
</Card>

<Modal
  open={restoring !== null}
  risk
  title={t('settings.db.restoreTitle')}
  riskLabel={t('settings.db.restoreRisk')}
  confirmLabel={t('settings.db.restore')}
  onconfirm={restore}
  oncancel={() => (restoring = null)}
>
  <p>{t('settings.db.restoreBody')}</p>
</Modal>

<Modal
  open={confirming}
  risk
  title={t('settings.db.compactTitle')}
  riskLabel={t('settings.db.compactRisk')}
  confirmLabel={t('settings.db.compactConfirm')}
  onconfirm={compact}
  oncancel={() => (confirming = false)}
>
  <p>{t('settings.db.compactBody')}</p>
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
