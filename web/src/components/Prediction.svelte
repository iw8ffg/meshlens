<script lang="ts">
  import { untrack } from 'svelte'
  import { ApiError } from '../lib/api'
  import { formatDate, signed } from '../lib/format'
  import { readDocumentTokens } from '../lib/map/tokens'
  import {
    PARAM_FIELDS, PRESET_OPTIONS, cancelPrediction, comparePrediction, decodeValues, defaultParams, deletePrediction,
    eirpDbm, estimatePrediction, getPrediction, gridToRgba, imageCoordinates, overLegalLimit, startPrediction,
    validateParams, type PredictionCompare, type PredictionEstimate, type PredictionMeta,
  } from '../lib/prediction'
  import { claimJobResult, prediction, reloadPredictions } from '../lib/prediction.svelte'
  import { getTheme } from '../lib/theme'
  import { app, coverage } from '../lib/stores.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import Progress from '../lib/ui/Progress.svelte'
  import Select from '../lib/ui/Select.svelte'

  const MANUAL = '__manual'

  // Siti proposti: i miei nodi e le radio locali che hanno una posizione
  const sites = $derived(
    [...app.nodes.values()].filter((n) => (n.is_mine || n.is_local_radio) && n.lat !== null && n.lon !== null),
  )
  let siteSel = $state(MANUAL)
  let params = $state(defaultParams())
  let name = $state('')
  let busy = $state(false)
  let error = $state('')
  let estimate = $state<PredictionEstimate | null>(null)
  let confirmDeleteId = $state<string | null>(null)
  let sessionSel = $state('')
  let compare = $state<PredictionCompare | null>(null)
  let compareFor = $state<string | null>(null)

  const job = $derived(prediction.job)
  const running = $derived(job !== null && job.status === 'running')
  const invalid = $derived(validateParams(params))
  const legal = $derived(overLegalLimit(params))
  const percent = $derived(job && job.total > 0 ? (job.done / job.total) * 100 : 0)
  const finished = $derived(coverage.sessions.filter((s) => s.ended !== null))
  const mb = $derived(estimate ? (estimate.download_bytes / 1_000_000).toLocaleString('it-IT', { maximumFractionDigits: 1 }) : '')

  const msg = (e: unknown) => (e instanceof ApiError ? e.message : 'Operazione non riuscita')

  // Scegliere un sito copia la sua posizione nei parametri; scrive solo `params`
  $effect(() => {
    const sel = siteSel
    if (sel === MANUAL) return
    const n = app.nodes.get(sel)
    if (n && n.lat !== null && n.lon !== null) {
      params.lat = Number(n.lat.toFixed(5))
      params.lon = Number(n.lon.toFixed(5))
    }
  })

  $effect(() => {
    void reloadPredictions()
  })

  // A calcolo concluso la previsione nuova si mostra da sola (una volta per lavoro)
  $effect(() => {
    const j = prediction.job
    if (j && j.status === 'done' && j.result_id && claimJobResult(j.id)) {
      void show(j.result_id)
    }
  })

  async function calc() {
    if (busy || running || invalid) return
    busy = true
    error = ''
    try {
      const est = await estimatePrediction(params)
      if (est.tiles_missing > 0) estimate = est
      else await start(false)
    } catch (e) {
      error = msg(e)
    } finally {
      busy = false
    }
  }

  async function start(download: boolean) {
    estimate = null
    try {
      prediction.job = await startPrediction(params, name.trim() || null, download)
    } catch (e) {
      error = msg(e)
    }
  }

  async function cancel() {
    if (!job) return
    try {
      prediction.job = await cancelPrediction(job.id)
    } catch (e) {
      error = msg(e)
    }
  }

  // Il raster usa i colori dei token: va ridisegnato quando cambia il tema (anche mentre il pannello era chiuso)
  $effect(() => {
    const ctl = getTheme()
    const redraw = () => {
      const s = prediction.shown
      if (!s || s.theme === ctl.theme()) return
      prediction.shown = { ...s, url: drawUrl(s.values, s.width, s.height), theme: ctl.theme() }
    }
    untrack(redraw)
    return ctl.subscribe(redraw)
  })

  function drawUrl(values: Int8Array, w: number, h: number): string {
    const c = document.createElement('canvas')
    c.width = w
    c.height = h
    const rgba = gridToRgba(values, readDocumentTokens())
    c.getContext('2d')!.putImageData(new ImageData(rgba as unknown as Uint8ClampedArray<ArrayBuffer>, w, h), 0, 0)
    return c.toDataURL()
  }

  async function show(id: string) {
    error = ''
    try {
      const g = await getPrediction(id)
      const values = decodeValues(g.values)
      prediction.shown = {
        id, url: drawUrl(values, g.width, g.height), coords: imageCoordinates(g.bbox),
        values, width: g.width, height: g.height, theme: getTheme().theme(),
      }
    } catch (e) {
      error = msg(e)
    }
  }

  async function remove() {
    const id = confirmDeleteId
    confirmDeleteId = null
    if (!id) return
    try {
      await deletePrediction(id)
      if (prediction.shown?.id === id) prediction.shown = null
      if (compareFor === id) {
        compare = null
        compareFor = null
      }
      await reloadPredictions()
    } catch (e) {
      error = msg(e)
    }
  }

  async function runCompare() {
    const id = prediction.shown?.id
    if (!id || sessionSel === '' || busy) return
    busy = true
    error = ''
    try {
      compare = await comparePrediction(id, Number(sessionSel))
      compareFor = id
    } catch (e) {
      error = msg(e)
    } finally {
      busy = false
    }
  }

  const label = (p: PredictionMeta) => p.name || formatDate(p.created)
  const pct = (n: number | null) => (n === null ? '—' : `${n.toLocaleString('it-IT', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`)
  const db = (n: number | null) => (n === null ? '—' : `${signed(n, 1)} dB`)
</script>

<Card>
  <section class="pred">
    <h3>Copertura prevista</h3>

    <Field label="Sito" for="pred-site">
      {#snippet children()}
        <Select id="pred-site" bind:value={siteSel} disabled={running}>
          {#each sites as n (n.id)}
            <option value={n.id}>{n.long_name || n.short_name || n.id}</option>
          {/each}
          <option value={MANUAL}>Coordinate manuali</option>
        </Select>
      {/snippet}
    </Field>

    <div class="grid">
      {#each PARAM_FIELDS as f (f.key)}
        {#if siteSel === MANUAL || (f.key !== 'lat' && f.key !== 'lon')}
          <Field label="{f.label} ({f.unit})" for="pred-{f.key}">
            {#snippet children()}
              <input id="pred-{f.key}" class="ui-input ui-mono" type="number" inputmode="decimal" min={f.min} max={f.max} step={f.step}
                bind:value={params[f.key]} disabled={running} />
            {/snippet}
          </Field>
        {/if}
      {/each}
      <Field label="Preset" for="pred-preset">
        {#snippet children()}
          <Select id="pred-preset" bind:value={params.preset} disabled={running}>
            {#each PRESET_OPTIONS as p (p)}<option value={p}>{p}</option>{/each}
          </Select>
        {/snippet}
      </Field>
      <Field label="Nome (facoltativo)" for="pred-name">
        {#snippet children()}
          <input id="pred-name" class="ui-input" maxlength="80" bind:value={name} disabled={running} />
        {/snippet}
      </Field>
    </div>

    <p class="meta">EIRP: {signed(eirpDbm(params), 1)} dBm</p>
    {#if legal}<Banner kind="warn" title="Oltre il limite di legge EU 868 (500 mW ERP)" />{/if}
    {#if invalid}<p class="err" role="alert">{invalid}</p>{/if}
    {#if error}<Banner kind="danger" title={error} />{/if}

    <div class="row">
      <Button kind="primary" icon="coverage" disabled={busy || running || !!invalid} onclick={calc}>Calcola</Button>
    </div>

    {#if job && running}
      <div class="job" role="status">
        <Progress value={percent} label="Avanzamento del calcolo" text="{job.step ?? ''} · {job.done}/{job.total}" />
        <div><Button icon="x" onclick={cancel}>Annulla</Button></div>
      </div>
    {:else if job && job.status === 'failed'}
      <Banner kind="danger" title={job.error || 'Calcolo non riuscito'} />
    {:else if job && job.status === 'cancelled'}
      <Banner kind="info" title="Calcolo annullato" />
    {/if}

    <h4>Previsioni salvate</h4>
    {#if prediction.list.length === 0}
      <p class="meta">Nessuna previsione salvata.</p>
    {:else}
      <ul class="list">
        {#each prediction.list as p (p.id)}
          {@const on = prediction.shown?.id === p.id}
          <li>
            <div class="info">
              <b>{label(p)}</b>
              <small>{formatDate(p.created)} · {p.params.preset} · {p.params.radius_km} km · {p.covered_km2.toLocaleString('it-IT', { maximumFractionDigits: 1 })} km²</small>
            </div>
            <div class="row">
              {#if on}
                <Button onclick={() => (prediction.shown = null)}>Nascondi</Button>
              {:else}
                <Button onclick={() => show(p.id)}>Mostra</Button>
              {/if}
              <Button kind="danger" icon="trash" onclick={() => (confirmDeleteId = p.id)}>Elimina</Button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}

    <div class="legend" role="group" aria-label="Legenda">
      <span class="chip good"><i></i>Buono (≥ 10 dB di margine)</span>
      <span class="chip mid"><i></i>Al limite (0–10 dB)</span>
      <span class="chip weak"><i></i>Debole (fino a −10 dB)</span>
    </div>

    {#if prediction.shown}
      <h4>Confronto con una prova</h4>
      <div class="row">
        <Select aria-label="Prova da confrontare" bind:value={sessionSel}>
          <option value="">Scegli una prova…</option>
          {#each finished as s (s.id)}<option value={String(s.id)}>{s.name}</option>{/each}
        </Select>
        <Button disabled={busy || sessionSel === ''} onclick={runCompare}>Confronta</Button>
      </div>
      {#if compare && compareFor === prediction.shown.id}
        <dl class="cmp">
          <dt>Accordo</dt><dd>{pct(compare.agreement_pct)}</dd>
          <dt>Ricevuti dentro / fuori</dt><dd>{compare.received_covered} / {compare.received_uncovered}</dd>
          <dt>Persi dentro / fuori</dt><dd>{compare.missing_covered} / {compare.missing_uncovered}</dd>
          <dt>Scarto medio RSSI</dt><dd>{db(compare.rssi_bias_db)}</dd>
          <dt>RMSE</dt><dd>{db(compare.rssi_rmse_db)}</dd>
        </dl>
      {/if}
    {/if}

    <p class="attr">Altitudine: AWS Terrain Tiles (SRTM, EU-DEM © Copernicus, GMTED2010, ETOPO1). Modello ITM © NTIA.</p>
  </section>
</Card>

<Modal open={estimate !== null} title="Scaricare i dati di altitudine?" confirmLabel="Scarica e calcola" cancelLabel="Annulla"
  onconfirm={() => start(true)} oncancel={() => (estimate = null)}>
  {#if estimate}
    <p>Servono {estimate.tiles_missing} riquadri di altitudine (circa {mb} MB) da AWS Terrain Tiles. Verranno conservati per l'uso offline.</p>
  {/if}
</Modal>

<Modal open={confirmDeleteId !== null} title="Eliminare la previsione?" danger confirmLabel="Elimina" onconfirm={remove}
  oncancel={() => (confirmDeleteId = null)}>
  <p>Eliminare definitivamente questa previsione? L'operazione non si può annullare.</p>
</Modal>

<style>
  .pred { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  h4 { margin: var(--space-2) 0 0; font: 600 14px/20px var(--font-sans); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: var(--space-3); }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .meta { margin: 0; color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  .err { margin: 0; color: var(--danger); font: 500 14px/20px var(--font-sans); }
  .job { display: flex; flex-direction: column; gap: var(--space-2); }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .list li { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-raised); }
  .info { display: flex; flex-direction: column; gap: 2px; font: 400 14px/20px var(--font-sans); }
  .info small { color: var(--ink-muted); font-size: 13px; }
  .legend { display: flex; flex-wrap: wrap; gap: var(--space-2); }
  .chip { display: inline-flex; align-items: center; gap: var(--space-2); min-height: 28px; padding: 0 var(--space-3); border: 1px solid var(--line-strong); border-radius: 999px; background: var(--surface-sunken); font: 400 13px/18px var(--font-sans); }
  .chip i { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }
  .chip.good i { background: var(--snr-good); }
  .chip.mid i { background: var(--snr-mid); }
  .chip.weak i { background: var(--snr-bad); }
  .cmp { display: grid; grid-template-columns: 1fr auto; gap: var(--space-1) var(--space-3); margin: 0; font: 400 14px/20px var(--font-sans); }
  .cmp dt { color: var(--ink-muted); }
  .cmp dd { margin: 0; text-align: right; font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
  .attr { margin: 0; color: var(--ink-muted); font: 400 12px/16px var(--font-sans); }
  :global(.vp-phone) .meta, :global(.vp-phone) .info small, :global(.vp-phone) .chip, :global(.vp-phone) .attr { font-size: 14px; line-height: 20px; }
</style>
