<script lang="ts">
  import { locale, t } from '../../lib/i18n/index.svelte'
  import { onMount } from 'svelte'
  import { ApiError, getJSON, send } from '../../lib/api'
  import type { AppSettings } from '../../lib/settings'
  import {
    buildBrokerRetention, bytes, effectiveBrokerDays, exportUrl, integrityDamaged, reasonLabel, sortedTableBytes,
    tableLabel, validateBrokerDays, type BackupInfo, type DbInfo, type ImportResult, type RetentionPreview,
  } from '../../lib/maintenance'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Check from '../../lib/ui/Check.svelte'
  import Field from '../../lib/ui/Field.svelte'
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
  let deleting = $state<BackupInfo | null>(null)
  let cleaning = $state(false)
  let retDays = $state<number | null>(0)
  let savedDays = $state(0)
  const daysValid = $derived(Number.isInteger(retDays) && retDays !== null && retDays >= 0 && retDays <= 3650)
  const cleanDays = $derived(daysValid && (retDays ?? 0) > 0 ? (retDays as number) : 0)

  const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

  // ---- spazio per tabella e conservazione per broker (1.6) ----
  const space = $derived(info ? sortedTableBytes(info) : [])
  let brokers = $state<{ id: string; name: string }[]>([])
  let brokerDays = $state<Record<string, number | null>>({})
  let generalDays = $state(90)
  let trDays = $state<number | null>(365)
  let preview = $state<RetentionPreview | null>(null)
  let retLoadError = $state('')
  const retentionValid = $derived(
    validateBrokerDays(trDays) === null
      && Object.values(brokerDays).every((d) => d == null || validateBrokerDays(d) === null),
  )

  function adoptRetention(s: AppSettings) {
    brokers = (s.mqtt_brokers ?? []).filter((b) => b.id).map((b) => ({ id: b.id as string, name: b.name || (b.id as string) }))
    const saved = s.retention_broker_days ?? {}
    brokerDays = Object.fromEntries(brokers.map((b) => [b.id, saved[b.id] ?? null]))
    generalDays = s.retention_messages_days ?? 90
    trDays = s.retention_traceroutes_days ?? 365
  }

  async function loadPreview() {
    try {
      preview = await getJSON<RetentionPreview>('/retention')
      retLoadError = ''
    } catch (e) {
      retLoadError = errMsg(e, t('retention.loadFailed'))
    }
  }

  async function saveRetentionRules() {
    if (!retentionValid) return
    error = ok = ''
    try {
      // input numerici svuotati: Svelte li porta a null (= regola generale)
      const map = Object.fromEntries(Object.entries(brokerDays).map(([k, v]) => [k, typeof v === 'number' ? v : null]))
      const s = await send<AppSettings>('PUT', '/settings', {
        retention_broker_days: buildBrokerRetention(map),
        retention_traceroutes_days: trDays,
      })
      adoptRetention(s)
      ok = t('retention.saved')
      await loadPreview()
    } catch (e) {
      error = errMsg(e, t('retention.saveFailed'))
    }
  }

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
    getJSON<AppSettings>('/settings')
      .then((s) => {
        retDays = savedDays = s.backup_retention_days ?? 0
        adoptRetention(s)
      })
      .catch(() => {})
    void loadPreview()
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

  async function removeBackup() {
    const b = deleting
    deleting = null
    if (!b) return
    error = ok = ''
    try {
      await send('DELETE', `/backups/${encodeURIComponent(b.name)}`, {})
      ok = t('settings.db.deleted')
    } catch (e) {
      error = errMsg(e, t('settings.db.deleteFailed'))
    }
    await loadBackups()
  }

  async function saveRetention() {
    if (!daysValid) return
    error = ok = ''
    try {
      await send('PUT', '/settings', { backup_retention_days: retDays })
      savedDays = retDays as number
      ok = t('settings.db.autoDeleteSaved')
    } catch (e) {
      error = errMsg(e, t('settings.db.autoDeleteFailed'))
    }
  }

  async function cleanOld() {
    const days = cleanDays
    cleaning = false
    if (!days) return
    error = ok = ''
    try {
      const r = await send<{ deleted: string[] }>('POST', '/backups/cleanup', { days })
      ok = t('settings.db.cleaned', { n: r.deleted.length })
    } catch (e) {
      error = errMsg(e, t('settings.db.deleteFailed'))
    }
    await loadBackups()
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
          <div><dt>{tableLabel(table)}</dt><dd class="ui-mono">{n.toLocaleString(locale())}</dd></div>
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
    {#if info && space.length > 0}
      <h3>{t('retention.space.title')}</h3>
      {#if info.table_bytes_method === 'estimate'}<p class="muted">{t('retention.space.estimate')}</p>{/if}
      <ul class="space">
        {#each space as s (s.name)}
          <li>
            <span class="sname">{tableLabel(s.name)}</span>
            <span class="bar" role="img" aria-label={t('retention.space.aria', { pct: Math.round(s.share * 100) })}><span style:width="{Math.max(1, s.share * 100)}%"></span></span>
            <span class="ui-mono">{bytes(s.bytes)}</span>
            {#if s.rows !== null}<span class="muted">{t('retention.space.rows', { n: s.rows.toLocaleString(locale()) })}</span>{/if}
          </li>
        {/each}
      </ul>
    {/if}
    <div class="row">
      <Button disabled={busy} onclick={() => (confirming = true)}>{t('settings.db.compact')}</Button>
    </div>
    <p class="muted">{t('settings.db.compactNote')}</p>
    <h3>{t('retention.broker.title')}</h3>
    <p class="muted">{t('retention.broker.intro')}</p>
    {#if retLoadError}<Banner kind="warn" title={retLoadError} />{/if}
    {#if brokers.length === 0}
      <p class="muted">{t('retention.broker.none')}</p>
    {:else}
      <ul class="brokers">
        {#each brokers as b (b.id)}
          {@const pv = preview?.brokers.find((x) => x.id === b.id)}
          {@const days = brokerDays[b.id]}
          <li>
            <Field label={t('retention.broker.days', { name: b.name })} for="ret-b-{b.id}"
              error={days != null && validateBrokerDays(days) ? t('retention.err.days') : undefined}>
              {#snippet children()}
                <input id="ret-b-{b.id}" class="ui-input ui-mono" type="number" min="1" max="3650" step="1"
                  placeholder={t('retention.broker.placeholder')} bind:value={brokerDays[b.id]} />
              {/snippet}
            </Field>
            <p class="muted">{t('retention.broker.effective', { n: effectiveBrokerDays(days ?? null, generalDays), g: generalDays })}</p>
            {#if pv}
              <p class="muted">{t('retention.broker.count', { n: pv.messages.toLocaleString(locale()) })} · {t('retention.broker.preview', { n: pv.would_delete.toLocaleString(locale()) })}</p>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}
    <p class="muted">{t('retention.broker.note')}</p>
    <div class="row auto">
      <Field label={t('retention.traceroutes')} for="ret-tr-days" error={validateBrokerDays(trDays) ? t('retention.err.days') : undefined}>
        {#snippet children()}<input id="ret-tr-days" class="ui-input ui-mono" type="number" min="1" max="3650" step="1" bind:value={trDays} />{/snippet}
      </Field>
    </div>
    {#if preview}
      <p class="muted">{t('retention.traceroutesPreview', { n: preview.traceroutes.would_delete.toLocaleString(locale()), total: preview.traceroutes.rows.toLocaleString(locale()) })}</p>
    {/if}
    <p class="muted">{t('retention.auto')}</p>
    <div class="row">
      <Button disabled={busy || !retentionValid} onclick={saveRetentionRules}>{t('retention.save')}</Button>
    </div>
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
            <span class="acts">
              <Button disabled={busy || restoreScheduled} onclick={() => (restoring = b)}>{t('settings.db.restore')}</Button>
              <Button iconOnly icon="trash" kind="danger" label={t('settings.db.deleteBackup')} disabled={busy} onclick={() => (deleting = b)} />
            </span>
          </li>
        {/each}
      </ul>
    {/if}
    <div class="row">
      <Button disabled={busy} onclick={createBackup}>{t('settings.db.create')}</Button>
      <Button disabled={busy || cleanDays === 0 || backups.length === 0} onclick={() => (cleaning = true)}>{t('settings.db.cleanNow', { n: cleanDays })}</Button>
    </div>
    <div class="row auto">
      <Field label={t('settings.db.autoDelete')} hint={t('settings.db.autoDeleteHint')} for="set-bk-days">
        {#snippet children()}<input id="set-bk-days" class="ui-input ui-mono" type="number" min="0" max="3650" step="1" bind:value={retDays} />{/snippet}
      </Field>
      <Button disabled={!daysValid || retDays === savedDays} onclick={saveRetention}>{t('settings.save')}</Button>
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
  open={deleting !== null}
  danger
  title={t('settings.db.deleteTitle')}
  confirmLabel={t('settings.db.deleteConfirm')}
  onconfirm={removeBackup}
  oncancel={() => (deleting = null)}
>
  <p>{t('settings.db.deleteBody', { when: deleting ? when(deleting.time) : '' })}</p>
</Modal>

<Modal
  open={cleaning}
  danger
  title={t('settings.db.cleanTitle')}
  confirmLabel={t('settings.db.cleanConfirm')}
  onconfirm={cleanOld}
  oncancel={() => (cleaning = false)}
>
  <p>{t('settings.db.cleanBody', { n: cleanDays })}</p>
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
  .acts { display: flex; gap: var(--space-2); align-items: center; }
  .auto { align-items: flex-end; }
  .auto :global(.ui-field) { flex: 1 1 260px; max-width: 360px; }
  .backups li { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); flex-wrap: wrap; font: 400 14px/20px var(--font-sans); }
  a.ui-btn { text-decoration: none; }
  .file input { display: none; }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  .space, .brokers { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .space li { display: grid; grid-template-columns: minmax(120px, 1fr) minmax(80px, 2fr) auto auto; gap: var(--space-2); align-items: center; font: 400 14px/20px var(--font-sans); }
  .bar { display: block; height: 8px; border-radius: 4px; background: var(--surface-sunken); overflow: hidden; }
  .bar span { display: block; height: 100%; background: var(--accent); }
  .brokers li { display: flex; flex-direction: column; gap: var(--space-1); }
  .brokers :global(.ui-field) { max-width: 360px; }
  :global(.vp-phone) .space li { grid-template-columns: 1fr auto; }
  :global(.vp-phone) .space .bar { grid-column: 1 / -1; }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
