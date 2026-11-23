<script lang="ts">
  import { onDestroy, onMount, untrack } from 'svelte'
  import {
    ApiError,
    applyConfig,
    configBackups,
    configJob,
    configSchema,
    previewConfig,
    previewRestore,
    radioAdminKey,
    readConfig,
    rebootNode,
    revealPsk,
    savedConfig,
    setFixedPosition,
  } from '../lib/api'
  import {
    CHANNEL_LABELS,
    MASK,
    SIMPLE_TABS,
    backupReasonLabel,
    cloneConfig,
    enumLabel,
    formChanges,
    getPath,
    jobText,
    schemaField,
    setPath,
  } from '../lib/config'
  import { formatDate, timeAgo } from '../lib/format'
  import { t } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
  import { app, configJobs, setConfigJob } from '../lib/stores.svelte'
  import type {
    ConfigBackup,
    ConfigChannelKeyed,
    ConfigDict,
    ConfigPreview,
    ConfigSaved,
    ConfigSchema,
    ConfigValue,
  } from '../lib/types'
  import ConfigAdvanced from './ConfigAdvanced.svelte'
  import ConfigProfiles from './ConfigProfiles.svelte'
  import ChannelShare from './ChannelShare.svelte'
  import PrivacyBanner from './PrivacyBanner.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import { generatePsk, isWeak, keyKind, type KeyKind } from '../lib/psk'
  import ConfigDiff from './ConfigDiff.svelte'
  import ConfigField from './ConfigField.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Modal from '../lib/ui/Modal.svelte'

  let {
    nodeId,
    radioId = null,
    initialTab = null,
    now,
    onclose,
  }: {
    nodeId: string
    radioId?: string | null
    initialTab?: string | null
    now: number
    onclose: () => void
  } = $props()

  const TABS = $derived<[string, string][]>([
    ...SIMPLE_TABS.slice(0, 4).map((st): [string, string] => [st.id, st.label]),
    ['channels', t('config.tab.channels')],
    ['modules', t('config.tab.modules')],
    ['advanced', t('config.tab.advanced')],
    ['backups', t('config.tab.backups')],
    ['profiles', t('config.tab.profiles')],
    ['adminkey', t('config.tab.adminkey')],
  ])
  // schede senza il form di modifica (niente «Rivedi e applica»)
  const NO_FORM = new Set(['adminkey', 'backups', 'profiles', 'admin'])

  const node = $derived(app.nodes.get(nodeId) ?? null)
  const nodeName = $derived(node?.long_name || node?.short_name || nodeId)
  const radios = $derived(app.radios.filter((r) => r.state === 'connected'))

  let tab = $state(untrack(() => initialTab) ?? 'general')
  let radioSel = $state<string>(
    untrack(
      () =>
        radioId ??
        app.radios.find((r) => r.state === 'connected' && r.my_node_id === nodeId)?.id ??
        app.radios.find((r) => r.state === 'connected')?.id ??
        '',
    ),
  )
  let schema = $state<ConfigSchema | null>(null)
  let saved = $state<ConfigSaved | null>(null)
  let edited = $state<ConfigDict>({})
  let backups = $state<ConfigBackup[]>([])
  let preview = $state<ConfigPreview | null>(null)
  // 'external': anteprima costruita dal server (profilo, privacy), non legata al form
  let previewFrom = $state<{ kind: 'form'; key: string } | { kind: 'restore' } | { kind: 'external' } | null>(null)
  let skipped = $state<string[]>([])
  let copyTimer: ReturnType<typeof setTimeout> | null = null
  let jobId = $state<number | null>(null)
  let err = $state('')
  let busy = $state(false)
  let pending = $state<'reboot' | 'fixed' | 'remove' | null>(null)
  let adminKey = $state('')
  let copied = $state(false)
  let revealed = $state<Record<number, string>>({})
  let lat = $state(untrack(() => (app.nodes.get(nodeId)?.lat ?? '').toString()))
  let lon = $state(untrack(() => (app.nodes.get(nodeId)?.lon ?? '').toString()))
  let alt = $state('')

  // se la radio scelta si scollega si passa alla prima connessa
  const radio = $derived(radios.some((r) => r.id === radioSel) ? radioSel : (radios[0]?.id ?? ''))
  const job = $derived(jobId === null ? null : (configJobs.get(jobId) ?? null))
  const running = $derived(job?.status === 'running')
  const lock = $derived(running || busy)
  // anteprima del form: vale solo finche' il form non cambia
  const formKey = $derived(saved ? JSON.stringify(formChanges(saved.config, edited)) : '')
  const activePreview = $derived(
    preview && previewFrom && (previewFrom.kind !== 'form' || previewFrom.key === formKey) ? preview : null,
  )
  const local = $derived(app.radios.find((r) => r.id === radio)?.my_node_id === nodeId)
  const keyMissing = $derived(job?.error_code === 'unauthorized' || (!!job?.error && !job.error_code && /chiave admin/i.test(job.error)))

  function msg(e: unknown): string {
    return e instanceof ApiError ? e.message : t('config.failed')
  }

  function takeSaved(s: ConfigSaved | null, keepEdits = false) {
    saved = s
    if (!keepEdits) {
      edited = s ? cloneConfig(s.config) : {}
      revealed = {}
    }
  }

  async function loadSaved(keepEdits = false) {
    try {
      takeSaved(await savedConfig(nodeId), keepEdits)
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) takeSaved(null)
      else err = msg(e)
    }
  }
  async function loadBackups() {
    try {
      backups = await configBackups(nodeId)
    } catch {
      /* elenco non disponibile */
    }
  }
  async function loadKey() {
    if (!radio) return
    try {
      adminKey = (await radioAdminKey(radio)).public_key_b64
    } catch {
      adminKey = ''
    }
  }

  onMount(() => {
    configSchema()
      .then((s) => (schema = s))
      .catch((e) => (err = msg(e)))
    loadSaved()
    loadBackups()
    loadKey()
  })

  onDestroy(() => {
    if (copyTimer) clearTimeout(copyTimer)
  })

  // Un lavoro concluso: rilegge la lettura salvata e le copie (una sola volta per lavoro)
  const handled = new Set<number>()
  const finished = $derived(job && job.status !== 'running' ? job.id : null)
  $effect(() => {
    const id = finished
    if (id === null || handled.has(id)) return
    handled.add(id)
    untrack(() => {
      // le modifiche non salvate dell'utente non vengono mai sovrascritte in silenzio
      loadSaved(dirty > 0)
      loadBackups()
    })
  })

  // Rete di sicurezza se il WebSocket perde un aggiornamento: interroga il lavoro finche' gira
  $effect(() => {
    if (!running || jobId === null) return
    const id = jobId
    const t = setInterval(() => {
      configJob(id)
        .then(setConfigJob)
        .catch(() => {})
    }, 2000)
    return () => clearInterval(t)
  })

  // Dopo una riconnessione del WebSocket un lavoro potrebbe essere finito senza che lo sapessimo
  $effect(() => {
    void app.reconnects
    untrack(() => {
      if (jobId !== null) {
        configJob(jobId)
          .then(setConfigJob)
          .catch(() => {})
      }
    })
  })

  async function run(fn: () => Promise<{ id: number } & Parameters<typeof setConfigJob>[0]>) {
    busy = true
    err = ''
    try {
      const j = await fn()
      setConfigJob(j)
      jobId = j.id
    } catch (e) {
      err = msg(e)
    } finally {
      busy = false
      pending = null
    }
  }

  const read = () => {
    preview = null
    run(() => readConfig(nodeId, radio ? { radio_id: radio } : {}))
  }

  async function review() {
    if (!saved) return
    preview = null
    previewFrom = null
    busy = true
    err = ''
    try {
      const changes = formChanges(saved.config, edited)
      if (Object.keys(changes).length === 0) {
        err = t('config.noChanges')
        return
      }
      const p = await previewConfig(nodeId, changes)
      preview = p
      previewFrom = { kind: 'form', key: JSON.stringify(changes) }
    } catch (e) {
      err = msg(e)
    } finally {
      busy = false
    }
  }

  async function restore(b: ConfigBackup) {
    preview = null
    previewFrom = null
    busy = true
    err = ''
    try {
      preview = await previewRestore(b.id)
      previewFrom = { kind: 'restore' }
    } catch (e) {
      err = msg(e)
    } finally {
      busy = false
    }
  }

  function showExternal(p: ConfigPreview, skippedPaths: string[] = []) {
    preview = p
    previewFrom = { kind: 'external' }
    skipped = skippedPaths
    err = ''
  }

  function apply(confirmRisky: boolean) {
    if (!activePreview) return
    const id = activePreview.preview_id
    preview = null
    previewFrom = null
    run(() => applyConfig(nodeId, id, confirmRisky))
  }

  const reboot = () => run(() => rebootNode(nodeId, radio || undefined))

  function fixed() {
    const la = Number(lat)
    const lo = Number(lon)
    if (lat === '' || lon === '' || !Number.isFinite(la) || !Number.isFinite(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) {
      err = t('config.badCoords')
      pending = null
      return
    }
    if (alt !== '' && !Number.isFinite(Number(alt))) {
      err = t('config.badAlt')
      pending = null
      return
    }
    run(() => setFixedPosition(nodeId, alt === '' ? { lat: la, lon: lo } : { lat: la, lon: lo, alt: Number(alt) }))
  }

  async function reveal(i: number) {
    err = ''
    try {
      revealed[i] = (await revealPsk(nodeId, i)).psk
    } catch (e) {
      err = msg(e)
    }
  }

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(adminKey)
      copied = true
      if (copyTimer) clearTimeout(copyTimer)
      copyTimer = setTimeout(() => (copied = false), 2000)
    } catch {
      err = t('config.copyFailed')
    }
  }

  const set = (path: string, v: ConfigValue) => setPath(edited, path, v)

  // WP4: chiavi deboli, lunghezza della chiave generata, condivisione dei canali
  let pskBits = $state<'256' | '128'>('256')
  let sharing = $state(false)
  const SESSION_MAX_AGE = 240 // s: oltre, il server vuole una nuova lettura del nodo remoto
  const canShare = $derived(!!radio && (local || (!!saved && now - saved.time < SESSION_MAX_AGE)))
  function weakKind(c: ConfigChannelKeyed): KeyKind | null {
    if (c.role === 'DISABLED') return null
    const pending = typeof c.psk === 'string' && c.psk !== MASK
    const kind: KeyKind | undefined = pending ? keyKind(c.psk as string) : c.key_kind
    return isWeak(kind) ? (kind as KeyKind) : null
  }
  const channels = $derived((edited.channels ?? []).slice().sort((a, b) => a.index - b.index))
  const dirty = $derived(saved ? Object.keys(formChanges(saved.config, edited)).length : 0)
  const outcome = $derived.by(() => {
    if (!job || job.status === 'running') return ''
    if (job.status === 'failed') return job.error ? translateServer(job.error) : t('config.failed')
    if (job.kind === 'apply')
      return job.verify === 'verified'
        ? t('config.out.verified')
        : job.verify === 'mismatch'
          ? t('config.out.mismatch')
          : t('config.out.applied')
    return job.kind === 'read' ? t('config.out.read') : t('config.out.done')
  })
</script>

<svelte:window onkeydown={(e) => e.key === 'Escape' && onclose()} />

<div class="overlay" role="dialog" aria-modal="true" aria-label={t('config.dialogAria')}>
  <div class="box">
    <header>
      <h2>{t('config.title', { name: nodeName })}</h2>
      <Button kind="ghost" iconOnly icon="x" label={t('common.close')} onclick={onclose} />
    </header>
    <p class="muted"><span class="ui-mono">{nodeId}</span>{local ? ` ${t('config.localNode')}` : ''}</p>

    <div class="row">
      <Field label={t('config.radio')} for="cfg-radio">
        {#snippet children()}
          <select id="cfg-radio" class="ui-select" value={radio} disabled={lock} onchange={(e) => { radioSel = e.currentTarget.value; loadKey() }}>
            {#if radios.length === 0}<option value="">{t('config.noRadio')}</option>{/if}
            {#each radios as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
          </select>
        {/snippet}
      </Field>
      <Button kind="primary" icon="download" disabled={lock || !radio} onclick={read}>{t('config.read')}</Button>
    </div>
    <p class="muted">
      {saved ? t('config.lastRead', { ago: timeAgo(saved.time, now), date: formatDate(saved.time) }) : t('config.noRead')}
    </p>

    {#if err}<Banner kind="danger" title={err} />{/if}

    {#if job}
      <div class="job">
        {#if running}
          <Banner kind="info" title={t('config.running')}>
            {jobText(job.step, job.progress)}
          </Banner>
        {:else}
          <Banner kind={job.status === 'failed' ? 'danger' : job.verify === 'mismatch' ? 'warn' : 'ok'} title={outcome}>
            {#if keyMissing}
              <div class="keyhelp">
                <Button kind="ghost" icon="key" onclick={() => (tab = 'adminkey')}>{t('config.keyHelp')}</Button>
                {#if adminKey}
                  <code class="key">{adminKey}</code>
                  <Button icon="copy" onclick={copyKey}>{copied ? t('config.copied') : t('config.copy')}</Button>
                {/if}
              </div>
            {/if}
          </Banner>
          <div><Button kind="ghost" onclick={() => (jobId = null)}>{t('config.closeOutcome')}</Button></div>
        {/if}
      </div>
    {/if}

    <div class="tabs" role="tablist" aria-label={t('config.sectionsAria')}>
      {#each TABS as [id, label] (id)}
        <button type="button" role="tab" aria-selected={tab === id} class:on={tab === id} onclick={() => (tab = id)}>{label}</button>
      {/each}
    </div>

    {#if activePreview}
      {#key activePreview.preview_id}
        {#if previewFrom?.kind === 'external' && skipped.length}
          <Banner kind="warn" title={t('profiles.skipped')}>{skipped.join(', ')}</Banner>
        {/if}
        <ConfigDiff preview={activePreview} {busy} onapply={apply} oncancel={() => (preview = null)} />
      {/key}
    {/if}

    {#if tab === 'adminkey'}
      <h3>{t('config.admin.title')}</h3>
      <p class="muted">
        {t('config.admin.body')}
      </p>
      {#if adminKey}
        <code class="key">{adminKey}</code>
        <div><Button icon="copy" onclick={copyKey}>{copied ? t('config.copied') : t('config.copy')}</Button></div>
      {:else}
        <p class="muted">{t('config.admin.unavailable')}</p>
      {/if}
      <ol class="steps">
        <li>{t('config.admin.step1')}</li>
        <li>{t('config.admin.step2')}</li>
        <li>{t('config.admin.step3')}</li>
      </ol>
    {:else if tab === 'backups'}
      <h3>{t('config.backups.title')}</h3>
      {#each backups as b (b.id)}
        <div class="bk">
          <span>
            {formatDate(b.time)} · {backupReasonLabel(b.reason)}{b.label ? ` · ${b.label}` : ''}
            <small class="muted">({b.sections.join(', ')})</small>
          </span>
          <Button disabled={lock || !!activePreview} onclick={() => restore(b)}>{t('config.backups.restore')}</Button>
        </div>
      {:else}
        <p class="muted">{t('config.backups.none')}</p>
      {/each}
    {:else if tab === 'profiles'}
      <ConfigProfiles {nodeId} radioId={radio || null} {saved} {lock} onpreview={showExternal} />
    {:else if !saved || !schema}
      <p class="muted">{schema ? t('config.readFirst') : t('config.loading')}</p>
    {:else if tab === 'advanced'}
      <ConfigAdvanced {schema} {edited} disabled={lock} />
    {:else if tab === 'channels'}
      <PrivacyBanner {nodeId} onfix={(p) => showExternal(p)} />
      <div class="row">
        <Segmented
          items={[{ value: '256', label: t('channels.bits256') }, { value: '128', label: t('channels.bits128') }]}
          bind:value={pskBits}
          label={t('channels.bitsLabel')}
        />
        <Button icon="copy" disabled={lock || !canShare} title={canShare ? '' : t('channels.share.needRead')} onclick={() => (sharing = true)}>{t('channels.share.open')}</Button>
      </div>
      {#each channels as c (c.index)}
        {@const weak = weakKind(c as ConfigChannelKeyed)}
        <details open={c.index === 0}>
          <summary>
            {c.name ? t('config.channelNamed', { n: c.index, name: c.name }) : t('config.channel', { n: c.index })} <small class="muted">{enumLabel('channel.role', String(c.role ?? ''))}</small>
          </summary>
          {#if c.index === 0}<Banner kind="warn" title={t('config.ch0.title')}>{t('config.ch0.body')}</Banner>{/if}
          {#each ['role', 'name', 'position_precision', 'uplink_enabled', 'downlink_enabled'] as f (f)}
            {#if schema.channel[f]}
              <ConfigField
                path={f === 'role' ? 'channel.role' : `channels.${c.index}.${f}`}
                field={schema.channel[f]}
                label={CHANNEL_LABELS[f]}
                value={getPath(edited, `channels.${c.index}.${f}`)}
                disabled={lock}
                onchange={(v) => set(`channels.${c.index}.${f}`, v)}
              />
            {/if}
          {/each}
          <div class="psk">
            <span class="ui-lbl">{CHANNEL_LABELS.psk}</span>
            <code>{c.psk !== MASK && c.psk ? t('config.psk.pending') : (revealed[c.index] ?? MASK)}</code>
            <Button icon="eye" disabled={lock} onclick={() => reveal(c.index)}>{t('config.psk.show')}</Button>
            <Button icon="refresh" disabled={lock} onclick={() => set(`channels.${c.index}.psk`, generatePsk(pskBits === '128' ? 16 : 32))}>{t('config.psk.generate')}</Button>
            {#if c.psk !== MASK}
              <Button kind="ghost" disabled={lock} onclick={() => set(`channels.${c.index}.psk`, MASK)}>{t('common.cancel')}</Button>
            {/if}
          </div>
          {#if weak}
            <Banner kind="warn" title={weak === 'none' ? t('channels.weak.none') : t('channels.weak.default')}>{t('channels.weak.body')}</Banner>
          {/if}
          {#if c.index === 0 && c.psk !== MASK}<Banner kind="warn" title={t('config.psk.newTitle')}>{t('config.psk.newBody')}</Banner>{/if}
        </details>
      {/each}
    {:else}
      {#each SIMPLE_TABS.filter((st) => st.id === tab) as st (st.id)}
        {#each st.fields as f (f.path)}
          {@const sf = schemaField(schema, f.path)}
          {#if sf}
            <ConfigField
              path={f.path}
              field={sf}
              label={f.label}
              help={f.help}
              value={getPath(edited, f.path)}
              disabled={lock}
              onchange={(v) => set(f.path, v)}
            />
          {/if}
        {/each}
      {/each}
      {#if tab === 'position'}
        <h3>{t('config.fixed.title')}</h3>
        <div class="row">
          <Field label={t('config.lat')} for="cfg-lat">{#snippet children()}<input id="cfg-lat" class="ui-input ui-mono" bind:value={lat} inputmode="decimal" />{/snippet}</Field>
          <Field label={t('config.lon')} for="cfg-lon">{#snippet children()}<input id="cfg-lon" class="ui-input ui-mono" bind:value={lon} inputmode="decimal" />{/snippet}</Field>
          <Field label={t('config.alt')} for="cfg-alt">{#snippet children()}<input id="cfg-alt" class="ui-input ui-mono" bind:value={alt} inputmode="decimal" placeholder={t('config.optional')} />{/snippet}</Field>
        </div>
        <div class="row">
          <Button disabled={lock || !radio} onclick={() => (pending = 'fixed')}>{t('config.fixed.set')}</Button>
          <Button disabled={lock || !radio} onclick={() => (pending = 'remove')}>{t('config.fixed.remove')}</Button>
        </div>
      {/if}
    {/if}

    {#if saved && schema && !NO_FORM.has(tab)}
      <div class="foot">
        <Button kind="primary" disabled={lock || dirty === 0 || !!activePreview} onclick={review}>{t('config.review')}{dirty ? ` (${dirty})` : ''}</Button>
        <Button kind="danger" icon="power" disabled={lock || !radio} onclick={() => (pending = 'reboot')}>{t('config.reboot')}</Button>
      </div>
    {/if}
  </div>
</div>

<ChannelShare {nodeId} open={sharing} onclose={() => (sharing = false)} />

<Modal
  open={pending === 'reboot'}
  title={t('config.reboot.title')}
  danger
  confirmLabel={t('config.reboot.confirm')}
  onconfirm={reboot}
  oncancel={() => (pending = null)}
>
  <p>{t('config.reboot.body')}</p>
</Modal>
<Modal
  open={pending === 'fixed' || pending === 'remove'}
  title={pending === 'remove' ? t('config.fixed.removeTitle') : t('config.fixed.setTitle')}
  confirmLabel={t('common.confirm')}
  onconfirm={() => (pending === 'remove' ? run(() => setFixedPosition(nodeId, { remove: true })) : fixed())}
  oncancel={() => (pending = null)}
>
  <p>{t('config.fixed.body')}</p>
</Modal>

<style>
  .overlay { position: fixed; inset: 0; background: var(--scrim); z-index: var(--z-modal); display: flex; align-items: center; justify-content: center; }
  .box { background: var(--surface-raised); color: var(--ink); border: 1px solid var(--line-strong); border-radius: var(--radius-xl); box-shadow: var(--shadow-3); width: min(720px, 96vw); max-height: 92dvh; overflow: auto; padding: var(--space-3) var(--space-4) var(--space-4); box-sizing: border-box; }
  header { display: flex; align-items: center; gap: var(--space-2); }
  h2 { flex: 1; font: 600 18px/24px var(--font-sans); margin: 0; }
  h3 { font: 600 15px/20px var(--font-sans); margin: var(--space-4) 0 var(--space-1); }
  p { margin: var(--space-1) 0; }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  .row { display: flex; gap: var(--space-2); align-items: flex-end; flex-wrap: wrap; margin: var(--space-2) 0; }
  .job { display: flex; flex-direction: column; gap: var(--space-2); margin: var(--space-2) 0; }
  .keyhelp { display: flex; flex-direction: column; gap: var(--space-2); align-items: flex-start; }
  .tabs { display: flex; overflow-x: auto; border-bottom: 1px solid var(--line); margin: var(--space-3) 0; }
  .tabs button { flex: none; background: none; border: 0; border-bottom: 2px solid transparent; color: var(--ink-muted); min-height: var(--touch-min); padding: 0 var(--space-3); cursor: pointer; font: 500 14px/20px var(--font-sans); }
  .tabs button.on { border-bottom-color: var(--accent); color: var(--accent-ink); }
  .tabs button:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: -2px; }
  .key { display: block; word-break: break-all; background: var(--surface-sunken); padding: var(--space-2); border-radius: var(--radius-sm); margin: var(--space-2) 0; font: 400 13px/18px var(--font-mono); }
  .steps { padding-left: 20px; font: 400 14px/20px var(--font-sans); }
  .bk { display: flex; justify-content: space-between; gap: var(--space-2); align-items: center; padding: var(--space-2) 0; border-bottom: 1px solid var(--line); font: 400 14px/20px var(--font-sans); }
  details { border: 1px solid var(--line); border-radius: var(--radius-md); padding: 0 var(--space-3) var(--space-2); margin: var(--space-2) 0; background: var(--surface); }
  summary { cursor: pointer; min-height: var(--touch-min); display: flex; align-items: center; gap: var(--space-2); font: 500 14px/20px var(--font-sans); }
  summary:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .psk { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; margin: var(--space-3) 0; }
  .psk code { word-break: break-all; font: 400 13px/18px var(--font-mono); }
  .foot { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; margin-top: var(--space-4); padding-top: var(--space-3); border-top: 1px solid var(--line); }
  :global(.vp-phone) .box { width: 100vw; max-height: 100dvh; height: 100dvh; border-radius: 0; border: 0; }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
