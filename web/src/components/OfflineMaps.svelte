<script lang="ts">
  import { locale } from '../lib/i18n/index.svelte'
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

  const MODES: [string, string][] = [
    ['auto', 'Automatica'],
    ['online', 'Solo online'],
    ['offline', 'Solo offline'],
  ]
  const LABEL: Record<MapKind, string> = { world: 'Mondo (base)', italy: 'Italia', area: 'Area' }

  let snap = $state<MapsState | null>(null)
  let loadError = $state('')
  let error = $state('')
  let info = $state('')
  let busy = $state(false)
  let mode = $state('auto')
  let sourceUrl = $state('')
  let areaName = $state('Area visibile')
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
      loadError = ''
    } catch {
      loadError = 'Mappe offline non disponibili'
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
    const t = setInterval(() => void load(), 5000)
    return () => clearInterval(t)
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
      info = 'Modalità salvata'
    } catch (e) {
      error = errMsg(e, 'Salvataggio non riuscito')
    }
  }

  async function saveSource() {
    error = info = ''
    try {
      await send('PUT', '/settings', { maps_source_url: sourceUrl.trim() })
      info = 'Fonte salvata'
    } catch (e) {
      error = errMsg(e, 'Salvataggio non riuscito')
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
      error = errMsg(e, 'Stima non riuscita')
    } finally {
      busy = false
    }
  }

  function askVisible() {
    error = info = ''
    const b = maps.bounds
    if (!b) {
      error = 'Area visibile non disponibile: apri la mappa'
      return
    }
    const name = areaName.trim()
    if (!name) {
      error = "Scrivi un nome per l'area"
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
      error = errMsg(e, 'Download non avviato')
    } finally {
      busy = false
    }
  }

  async function cancel() {
    if (!job) return
    try {
      await cancelMapJob(job.id)
    } catch (e) {
      error = errMsg(e, 'Annullamento non riuscito')
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
      error = errMsg(e, 'Eliminazione non riuscita')
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
    <h3>Mappe offline</h3>
    {#if loadError}
      <Banner kind="danger" title={loadError} />
    {:else if !snap}
      <Skeleton tall />
    {:else}
      <Field label="Modalità mappa" for="map-mode">
        {#snippet children()}
          <Select id="map-mode" bind:value={mode} onchange={saveMode}>
            {#each MODES as [v, l] (v)}<option value={v}>{l}</option>{/each}
          </Select>
        {/snippet}
      </Field>
      <p class="muted">Spazio libero: <span class="ui-mono">{formatBytes(snap.disk_free_bytes)}</span></p>

      {#if snap.maps.length === 0}
        <p class="muted">Nessuna mappa scaricata.</p>
      {:else}
        <ul class="maps">
          {#each snap.maps as m (m.id)}
            <li>
              <div>
                <b>{m.name}</b> · {LABEL[m.kind]} · <span class="ui-mono">{formatBytes(m.size_bytes)}</span>
                <div class="muted">Dati del {dataDate(m.source_date)} · scaricata il {when(m.created)}</div>
              </div>
              <Button icon="trash" disabled={running} onclick={() => (toDelete = m.id)}>Elimina</Button>
            </li>
          {/each}
        </ul>
      {/if}

      {#if running && job}
        <div class="job" role="status">
          <div>{job.name}: {job.step}</div>
          {#if percent !== null}
            <Progress value={percent} label="Avanzamento del download" text="{percent}% ({formatBytes(job.bytes_done)} di {formatBytes(job.bytes_total ?? 0)})" />
          {:else}
            <Progress value={100} label="Download in corso" text={formatBytes(job.bytes_done)} />
          {/if}
          <div><Button icon="x" onclick={cancel}>Annulla</Button></div>
        </div>
      {:else if job && job.status === 'failed'}
        <Banner kind="danger" title="Download non riuscito">{job.error ?? 'errore sconosciuto'}</Banner>
      {:else if job && job.status === 'cancelled'}
        <p class="muted">Download annullato.</p>
      {:else if job && job.status === 'done'}
        <Banner kind="ok" title="Download completato">{job.name}</Banner>
      {/if}

      {#if !running}
        <div class="row">
          <Button icon="download" disabled={busy || !!pending} onclick={() => ask('world')}>Scarica mondo (base)</Button>
          <Button icon="download" disabled={busy || !!pending} onclick={() => ask('italy')}>Scarica Italia</Button>
          <Button icon="map" disabled={busy || !!pending} onclick={() => (askArea = !askArea)}>Scarica area visibile</Button>
        </div>
        {#if askArea}
          <div class="row">
            <input class="ui-input grow" type="text" aria-label="Nome dell'area" maxlength="60" bind:value={areaName} />
            <Button kind="primary" disabled={busy} onclick={askVisible}>Continua</Button>
          </div>
        {/if}
      {/if}

      <details>
        <summary>Avanzate</summary>
        <Field label="Fonte personalizzata (URL .pmtiles)" for="map-src">
          {#snippet children()}
            <input id="map-src" class="ui-input" type="text" placeholder="https://…/mappa.pmtiles" bind:value={sourceUrl} />
          {/snippet}
        </Field>
        <div class="gap"><Button onclick={saveSource}>Salva fonte</Button></div>
      </details>
      <p class="muted">© OpenStreetMap contributors · Protomaps</p>
      {#if error}<Banner kind="danger" title={error} />{/if}
      {#if info}<Banner kind="ok" title={info} />{/if}
    {/if}
  </section>
</Card>

<Modal
  open={pending !== null}
  title="Conferma download"
  confirmLabel="Scarica"
  onconfirm={confirmDownload}
  oncancel={() => (pending = null)}
>
  {#if pending}
    <p class="wrapany">
      <b>{pending.kind === 'area' ? pending.name : LABEL[pending.kind]}</b>: circa <span class="ui-mono">{formatBytes(pending.est.estimate_bytes)}</span>.<br />
      Fonte: {pending.est.source_url}<br />
      Dati del {dataDate(pending.est.source_date)}.
    </p>
    {#if pending.est.needs_tool}
      <p>Verrà scaricato anche lo strumento ufficiale go-pmtiles (≈ {Math.round(pending.est.tool_size_bytes / 1_000_000)} MB) da GitHub.</p>
    {/if}
  {/if}
</Modal>
<Modal
  open={toDeleteMap !== null}
  title="Eliminare la mappa?"
  danger
  confirmLabel="Sì, elimina"
  cancelLabel="No"
  onconfirm={() => toDeleteMap && remove(toDeleteMap)}
  oncancel={() => (toDelete = null)}
>
  <p>Eliminare "{toDeleteMap?.name ?? ''}"? Dovrai scaricarla di nuovo per usarla offline.</p>
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
