<script lang="ts">
  import { locale, t, type MsgKey } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
  import { onMount, untrack } from 'svelte'
  import { ApiError, cancelMapJob, deleteMap, downloadMap, estimateMap, getJSON, mapsState, send } from '../lib/api'
  import { bboxFromBounds, formatBytes, isStaleSnapshot, jobPercent } from '../lib/maps'
  import { app, bumpMaps, maps, setMapJob } from '../lib/stores.svelte'
  import type { AppSettings } from '../lib/settings'
  import type { Bbox, MapEstimate, MapKind, MapsState, OfflineMap } from '../lib/types'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import Progress from '../lib/ui/Progress.svelte'
  import Select from '../lib/ui/Select.svelte'
  import Skeleton from '../lib/ui/Skeleton.svelte'

  const MODE_KEYS: [string, MsgKey][] = [
    ['auto', 'maps.mode.auto'],
    ['online', 'maps.mode.online'],
    ['offline', 'maps.mode.offline'],
  ]
  const KIND_KEYS: Record<MapKind, MsgKey> = { world: 'maps.kind.world', italy: 'maps.kind.italy', area: 'maps.kind.area' }

  let snap = $state<MapsState | null>(null)
  let loadFailed = $state(false)
  let error = $state('')
  let info = $state('')
  let busy = $state(false)
  let mode = $state('auto')
  let sourceUrl = $state('')
  let areaName = $state(t('maps.defaultArea'))
  // Download in attesa di conferma (stima gia' ricevuta)
  let pending = $state<{ kind: MapKind; bbox?: Bbox; name?: string; est: MapEstimate } | null>(null)
  let askArea = $state(false)
  let toDelete = $state<string | null>(null)

  const toDeleteMap = $derived(snap?.maps.find((m) => m.id === toDelete) ?? null)
  const job = $derived(maps.job ?? snap?.job ?? null)
  const running = $derived(job?.status === 'running')
  const percent = $derived(job ? jobPercent(job) : null)

  async function load() {
    try {
      snap = await mapsState()
      mode = snap.mode
      const j = snap.job
      // il lavoro dell'istantanea e' piu' recente se id o stato differiscono (WS perso)
      if (j && !isStaleSnapshot(maps.job, j)
          && (maps.job?.id !== j.id || maps.job?.status !== j.status)) setMapJob(j)
      loadFailed = false
    } catch {
      loadFailed = true
    }
  }

  onMount(async () => {
    void load()
    try {
      const s = await getJSON<AppSettings>('/settings')
      sourceUrl = s.maps_source_url ?? ''
    } catch {
      /* campo avanzato lasciato vuoto */
    }
  })

  // Riconnessione del WebSocket: lo stato puo' essere vecchio
  let seenReconnects = app.reconnects
  $effect(() => {
    const r = app.reconnects
    untrack(() => {
      if (r === seenReconnects) return
      seenReconnects = r
      void load()
    })
  })

  // Con un lavoro in corso rilegge lo stato ogni 5 s (rete di sicurezza se il WS non arriva)
  $effect(() => {
    if (!running) return
    const timer = setInterval(() => void load(), 5000)
    return () => clearInterval(timer)
  })

  // Fine download o eliminazione da altrove: rilegge l'elenco (nessuna scrittura su stati letti qui)
  let seen = maps.version
  $effect(() => {
    const v = maps.version
    untrack(() => {
      if (v === seen) return
      seen = v
      void load()
    })
  })

  const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

  async function saveMode(e: Event) {
    error = info = ''
    const value = (e.currentTarget as HTMLSelectElement).value
    try {
      await send('PUT', '/settings', { map_mode: value })
      bumpMaps()
      info = t('maps.modeSaved')
    } catch (e) {
      error = errMsg(e, t('maps.saveFailed'))
    }
  }

  async function saveSource() {
    error = info = ''
    try {
      await send('PUT', '/settings', { maps_source_url: sourceUrl.trim() })
      info = t('maps.sourceSaved')
    } catch (e) {
      error = errMsg(e, t('maps.saveFailed'))
    }
  }

  async function ask(kind: MapKind, bbox?: Bbox, name?: string) {
    error = info = ''
    busy = true
    try {
      const est = await estimateMap(kind, bbox)
      pending = { kind, bbox, name, est }
      askArea = false
    } catch (e) {
      error = errMsg(e, t('maps.estimateFailed'))
    } finally {
      busy = false
    }
  }

  function askVisible() {
    error = info = ''
    const b = maps.bounds
    if (!b) {
      error = t('maps.noBounds')
      return
    }
    const name = areaName.trim()
    if (!name) {
      error = t('maps.needName')
      return
    }
    void ask('area', bboxFromBounds(b), name)
  }

  async function confirmDownload() {
    if (!pending) return
    const p = pending
    error = info = ''
    busy = true
    try {
      maps.job = await downloadMap(p.kind, p.bbox, p.name)
      pending = null
    } catch (e) {
      error = errMsg(e, t('maps.downloadNotStarted'))
    } finally {
      busy = false
    }
  }

  async function cancel() {
    if (!job) return
    try {
      await cancelMapJob(job.id)
    } catch (e) {
      error = errMsg(e, t('maps.cancelFailed'))
    }
  }

  async function remove(m: OfflineMap) {
    error = info = ''
    try {
      await deleteMap(m.id)
      toDelete = null
      bumpMaps()
      await load()
    } catch (e) {
      error = errMsg(e, t('maps.deleteFailed'))
    }
  }

  const when = (c: number | string) => {
    const d = typeof c === 'number' ? new Date(c * 1000) : new Date(c)
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString(locale())
  }
  const dataDate = (s: string | null) => (s && /^\d{8}$/.test(s) ? `${s.slice(6, 8)}/${s.slice(4, 6)}/${s.slice(0, 4)}` : '—')
</script>

<Card>
  <section class="sec">
    <h3>{t('maps.title')}</h3>
    {#if loadFailed}
      <Banner kind="danger" title={t('maps.loadFailed')} />
    {:else if !snap}
      <Skeleton tall />
    {:else}
      <Field label={t('maps.mapMode')} for="map-mode">
        {#snippet children()}
          <Select id="map-mode" bind:value={mode} onchange={saveMode}>
            {#each MODE_KEYS as [v, k] (v)}<option value={v}>{t(k)}</option>{/each}
          </Select>
        {/snippet}
      </Field>
      <p class="muted">{t('maps.free')} <span class="ui-mono">{formatBytes(snap.disk_free_bytes)}</span></p>

      {#if snap.maps.length === 0}
        <p class="muted">{t('maps.none')}</p>
      {:else}
        <ul class="maps">
          {#each snap.maps as m (m.id)}
            <li>
              <div>
                <b>{m.name}</b> · {t(KIND_KEYS[m.kind])} · <span class="ui-mono">{formatBytes(m.size_bytes)}</span>
                <div class="muted">{t('maps.dataFrom', { date: dataDate(m.source_date), when: when(m.created) })}</div>
              </div>
              <Button icon="trash" disabled={running} onclick={() => (toDelete = m.id)}>{t('maps.delete')}</Button>
            </li>
          {/each}
        </ul>
      {/if}

      {#if running && job}
        <div class="job" role="status">
          <div>{job.name}: {translateServer(job.step ?? '')}</div>
          {#if percent !== null}
            <Progress value={percent} label={t('maps.progress')} text={t('maps.progressText', { pct: percent, done: formatBytes(job.bytes_done), total: formatBytes(job.bytes_total ?? 0) })} />
          {:else}
            <Progress value={100} label={t('maps.inProgress')} text={formatBytes(job.bytes_done)} />
          {/if}
          <div><Button icon="x" onclick={cancel}>{t('common.cancel')}</Button></div>
        </div>
      {:else if job && job.status === 'failed'}
        <Banner kind="danger" title={t('maps.failed')}>{job.error ? translateServer(job.error) : t('maps.unknownError')}</Banner>
      {:else if job && job.status === 'cancelled'}
        <p class="muted">{t('maps.cancelled')}</p>
      {:else if job && job.status === 'done'}
        <Banner kind="ok" title={t('maps.done')}>{job.name}</Banner>
      {/if}

      {#if !running}
        <div class="row">
          <Button icon="download" disabled={busy || !!pending} onclick={() => ask('world')}>{t('maps.getWorld')}</Button>
          <Button icon="download" disabled={busy || !!pending} onclick={() => ask('italy')}>{t('maps.getItaly')}</Button>
          <Button icon="map" disabled={busy || !!pending} onclick={() => (askArea = !askArea)}>{t('maps.getArea')}</Button>
        </div>
        {#if askArea}
          <div class="row">
            <input class="ui-input grow" type="text" aria-label={t('maps.areaNameAria')} maxlength="60" bind:value={areaName} />
            <Button kind="primary" disabled={busy} onclick={askVisible}>{t('maps.continue')}</Button>
          </div>
        {/if}
      {/if}

      <details>
        <summary>{t('maps.advanced')}</summary>
        <Field label={t('maps.source')} for="map-src">
          {#snippet children()}
            <input id="map-src" class="ui-input" type="text" placeholder="https://…/mappa.pmtiles" bind:value={sourceUrl} />
          {/snippet}
        </Field>
        <div class="gap"><Button onclick={saveSource}>{t('maps.saveSource')}</Button></div>
      </details>
      <p class="muted">© OpenStreetMap contributors · Protomaps</p>
      {#if error}<Banner kind="danger" title={error} />{/if}
      {#if info}<Banner kind="ok" title={info} />{/if}
    {/if}
  </section>
</Card>

<Modal
  open={pending !== null}
  title={t('maps.confirm.title')}
  confirmLabel={t('maps.confirm.get')}
  onconfirm={confirmDownload}
  oncancel={() => (pending = null)}
>
  {#if pending}
    <p class="wrapany">
      <b>{pending.kind === 'area' ? pending.name : t(KIND_KEYS[pending.kind])}</b>: {t('maps.confirm.about')} <span class="ui-mono">{formatBytes(pending.est.estimate_bytes)}</span>.<br />
      {t('maps.confirm.source', { url: pending.est.source_url })}<br />
      {t('maps.confirm.data', { date: dataDate(pending.est.source_date) })}
    </p>
    {#if pending.est.needs_tool}
      <p>{t('maps.confirm.tool', { mb: Math.round(pending.est.tool_size_bytes / 1_000_000) })}</p>
    {/if}
  {/if}
</Modal>
<Modal
  open={toDeleteMap !== null}
  title={t('maps.del.title')}
  danger
  confirmLabel={t('maps.del.yes')}
  cancelLabel={t('maps.del.no')}
  onconfirm={() => toDeleteMap && remove(toDeleteMap)}
  oncancel={() => (toDelete = null)}
>
  <p>{t('maps.del.body', { name: toDeleteMap?.name ?? '' })}</p>
</Modal>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  .maps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); font: 400 14px/20px var(--font-sans); }
  .maps li { display: flex; justify-content: space-between; align-items: center; gap: var(--space-2); padding-bottom: var(--space-2); border-bottom: 1px solid var(--line); }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .grow { flex: 1; min-width: 160px; }
  .job { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--line); border-radius: var(--radius-md); font: 400 14px/20px var(--font-sans); }
  .wrapany { overflow-wrap: anywhere; }
  details { font: 400 14px/20px var(--font-sans); }
  summary { cursor: pointer; min-height: var(--touch-min); display: flex; align-items: center; }
  summary:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .gap { margin-top: var(--space-2); }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
