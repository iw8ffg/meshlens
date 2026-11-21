<script lang="ts">
  import { onMount, untrack } from 'svelte'
  import { ApiError, cancelMapJob, deleteMap, downloadMap, estimateMap, getJSON, mapsState, send } from '../lib/api'
  import { bboxFromBounds, formatBytes, jobPercent } from '../lib/maps'
  import { app, bumpMaps, maps, setMapJob } from '../lib/stores.svelte'
  import type { AppSettings } from '../lib/settings'
  import type { Bbox, MapEstimate, MapKind, MapsState, OfflineMap } from '../lib/types'

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

  const job = $derived(maps.job ?? snap?.job ?? null)
  const running = $derived(job?.status === 'running')
  const percent = $derived(job ? jobPercent(job) : null)

  async function load() {
    try {
      snap = await mapsState()
      mode = snap.mode
      const j = snap.job
      // il lavoro dell'istantanea e' piu' recente se id o stato differiscono (WS perso)
      if (j && (maps.job?.id !== j.id || maps.job?.status !== j.status)) setMapJob(j)
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
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('it-IT')
  }
  const dataDate = (s: string | null) => (s && /^\d{8}$/.test(s) ? `${s.slice(6, 8)}/${s.slice(4, 6)}/${s.slice(0, 4)}` : '—')
</script>

<fieldset>
  <legend>Mappe offline</legend>
  {#if loadError}
    <p class="err">{loadError}</p>
  {:else if !snap}
    <p class="muted">Caricamento…</p>
  {:else}
    <label>
      Modalità mappa
      <select bind:value={mode} onchange={saveMode}>
        {#each MODES as [v, l] (v)}<option value={v}>{l}</option>{/each}
      </select>
    </label>
    <p class="muted">Spazio libero: {formatBytes(snap.disk_free_bytes)}</p>

    {#if snap.maps.length === 0}
      <p class="muted">Nessuna mappa scaricata.</p>
    {:else}
      <ul class="maps">
        {#each snap.maps as m (m.id)}
          <li>
            <div>
              <b>{m.name}</b> · {LABEL[m.kind]} · {formatBytes(m.size_bytes)}
              <div class="muted">Dati del {dataDate(m.source_date)} · scaricata il {when(m.created)}</div>
            </div>
            {#if toDelete === m.id}
              <span class="row">
                <span>Eliminare "{m.name}"?</span>
                <button type="button" class="danger" onclick={() => remove(m)}>Sì, elimina</button>
                <button type="button" onclick={() => (toDelete = null)}>No</button>
              </span>
            {:else}
              <button type="button" disabled={running} onclick={() => (toDelete = m.id)}>Elimina</button>
            {/if}
          </li>
        {/each}
      </ul>
    {/if}

    {#if running && job}
      <div class="job" role="status">
        <div>{job.name}: {job.step}</div>
        {#if percent !== null}
          <progress max="100" value={percent}></progress>
          <span>{percent}% ({formatBytes(job.bytes_done)} di {formatBytes(job.bytes_total ?? 0)})</span>
        {:else}
          <progress></progress>
          <span>{formatBytes(job.bytes_done)}</span>
        {/if}
        <button type="button" onclick={cancel}>Annulla</button>
      </div>
    {:else if job && job.status === 'failed'}
      <p class="err" role="alert">Download non riuscito: {job.error ?? 'errore sconosciuto'}</p>
    {:else if job && job.status === 'cancelled'}
      <p class="muted">Download annullato.</p>
    {:else if job && job.status === 'done'}
      <p class="ok">Download completato: {job.name}.</p>
    {/if}

    {#if pending}
      <div class="confirm" role="dialog" aria-label="Conferma download">
        <p>
          <b>{pending.kind === 'area' ? pending.name : LABEL[pending.kind]}</b>: circa {formatBytes(pending.est.estimate_bytes)}.<br />
          Fonte: {pending.est.source_url}<br />
          Dati del {dataDate(pending.est.source_date)}.
        </p>
        {#if pending.est.needs_tool}
          <p>Verrà scaricato anche lo strumento ufficiale go-pmtiles (≈ {Math.round(pending.est.tool_size_bytes / 1_000_000)} MB) da GitHub.</p>
        {/if}
        <span class="row">
          <button type="button" class="primary" disabled={busy} onclick={confirmDownload}>Scarica</button>
          <button type="button" onclick={() => (pending = null)}>Annulla</button>
        </span>
      </div>
    {:else if !running}
      <div class="row wrap">
        <button type="button" disabled={busy} onclick={() => ask('world')}>Scarica mondo (base)</button>
        <button type="button" disabled={busy} onclick={() => ask('italy')}>Scarica Italia</button>
        <button type="button" disabled={busy} onclick={() => (askArea = !askArea)}>Scarica area visibile</button>
      </div>
      {#if askArea}
        <div class="row wrap">
          <input type="text" aria-label="Nome dell'area" maxlength="60" bind:value={areaName} />
          <button type="button" disabled={busy} onclick={askVisible}>Continua</button>
        </div>
      {/if}
    {/if}

    <details>
      <summary>Avanzate</summary>
      <label>
        Fonte personalizzata (URL .pmtiles)
        <input type="text" placeholder="https://…/mappa.pmtiles" bind:value={sourceUrl} />
      </label>
      <button type="button" onclick={saveSource}>Salva fonte</button>
    </details>
    <p class="muted">© OpenStreetMap contributors · Protomaps</p>
    {#if error}<p class="err" role="alert">{error}</p>{/if}
    {#if info}<p class="ok" role="status">{info}</p>{/if}
  {/if}
</fieldset>

<style>
  fieldset {
    border: 1px solid #374151;
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 13px;
  }
  .maps {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
  }
  .maps li {
    display: flex;
    justify-content: space-between;
    align-items: center;
    gap: 8px;
  }
  .row {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .wrap {
    flex-wrap: wrap;
  }
  .job,
  .confirm {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    border: 1px solid #374151;
    border-radius: 6px;
    font-size: 13px;
  }
  .confirm p {
    margin: 0;
    overflow-wrap: anywhere;
  }
  progress {
    width: 100%;
  }
  input[type='text'],
  select {
    padding: 5px 8px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    font: inherit;
  }
  button {
    padding: 6px 12px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    cursor: pointer;
    font: inherit;
  }
  button.primary {
    background: #2563eb;
    border-color: #2563eb;
  }
  button.danger {
    background: #b91c1c;
    border-color: #b91c1c;
  }
  .muted {
    color: #9ca3af;
    margin: 0;
    font-size: 12px;
  }
  @media (max-width: 767px) {
    .muted {
      font-size: 13px;
    }
  }
  .err {
    color: #f87171;
    margin: 0;
  }
  .ok {
    color: #34d399;
    margin: 0;
  }
</style>
