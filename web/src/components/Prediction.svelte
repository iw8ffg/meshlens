<script lang="ts">
  import { visibleNodes } from '../lib/filters'
  import { locale, t } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
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
    visibleNodes(app.nodes.values()).filter((n) => (n.is_mine || n.is_local_radio) && n.lat !== null && n.lon !== null),
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
  const mb = $derived(estimate ? (estimate.download_bytes / 1_000_000).toLocaleString(locale(), { maximumFractionDigits: 1 }) : '')

  const msg = (e: unknown) => (e instanceof ApiError ? e.message : t('prediction.error'))

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
  const pct = (n: number | null) => (n === null ? '—' : `${n.toLocaleString(locale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`)
  const db = (n: number | null) => (n === null ? '—' : `${signed(n, 1)} dB`)
</script>

<Card>
  <section class="pred">
    <h3>{t('prediction.title')}</h3>

    <Field label={t('prediction.site')} for="pred-site">
      {#snippet children()}
        <Select id="pred-site" bind:value={siteSel} disabled={running}>
          {#each sites as n (n.id)}
            <option value={n.id}>{n.long_name || n.short_name || n.id}</option>
          {/each}
          <option value={MANUAL}>{t('prediction.manual')}</option>
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
      <Field label={t('prediction.preset')} for="pred-preset">
        {#snippet children()}
          <Select id="pred-preset" bind:value={params.preset} disabled={running}>
            {#each PRESET_OPTIONS as p (p)}<option value={p}>{p}</option>{/each}
          </Select>
        {/snippet}
      </Field>
      <Field label={t('prediction.name')} for="pred-name">
        {#snippet children()}
          <input id="pred-name" class="ui-input" maxlength="80" bind:value={name} disabled={running} />
        {/snippet}
      </Field>
    </div>

    <p class="meta">{t('prediction.eirp', { v: signed(eirpDbm(params), 1) })}</p>
    {#if legal}<Banner kind="warn" title={t('prediction.legal')} />{/if}
    {#if invalid}<p class="err" role="alert">{invalid}</p>{/if}
    {#if error}<Banner kind="danger" title={error} />{/if}

    <div class="row">
      <Button kind="primary" icon="coverage" disabled={busy || running || !!invalid} onclick={calc}>{t('prediction.calc')}</Button>
    </div>

    {#if job && running}
      <div class="job" role="status">
        <Progress value={percent} label={t('prediction.progress')} text="{job.step ? translateServer(job.step) : ''} · {job.done}/{job.total}" />
        <div><Button icon="x" onclick={cancel}>{t('common.cancel')}</Button></div>
      </div>
    {:else if job && job.status === 'failed'}
      <Banner kind="danger" title={job.error ? translateServer(job.error) : t('prediction.failed')} />
    {:else if job && job.status === 'cancelled'}
      <Banner kind="info" title={t('prediction.cancelled')} />
    {/if}

    <h4>{t('prediction.saved')}</h4>
    {#if prediction.list.length === 0}
      <p class="meta">{t('prediction.none')}</p>
    {:else}
      <ul class="list">
        {#each prediction.list as p (p.id)}
          {@const on = prediction.shown?.id === p.id}
          <li>
            <div class="info">
              <b>{label(p)}</b>
              <small>{t('prediction.item.meta', { date: formatDate(p.created), preset: p.params.preset, radius: p.params.radius_km, area: p.covered_km2.toLocaleString(locale(), { maximumFractionDigits: 1 }) })}</small>
            </div>
            <div class="row">
              {#if on}
                <Button onclick={() => (prediction.shown = null)}>{t('prediction.hide')}</Button>
              {:else}
                <Button onclick={() => show(p.id)}>{t('prediction.show')}</Button>
              {/if}
              <Button kind="danger" icon="trash" onclick={() => (confirmDeleteId = p.id)}>{t('prediction.delete')}</Button>
            </div>
          </li>
        {/each}
      </ul>
    {/if}

    <div class="legend" role="group" aria-label={t('prediction.legend')}>
      <span class="chip good"><i></i>{t('prediction.legend.good')}</span>
      <span class="chip mid"><i></i>{t('prediction.legend.mid')}</span>
      <span class="chip weak"><i></i>{t('prediction.legend.weak')}</span>
    </div>

    {#if prediction.shown}
      <h4>{t('prediction.cmp.title')}</h4>
      <div class="row">
        <Select aria-label={t('prediction.cmp.pickAria')} bind:value={sessionSel}>
          <option value="">{t('prediction.cmp.pick')}</option>
          {#each finished as s (s.id)}<option value={String(s.id)}>{s.name}</option>{/each}
        </Select>
        <Button disabled={busy || sessionSel === ''} onclick={runCompare}>{t('prediction.cmp.run')}</Button>
      </div>
      {#if compare && compareFor === prediction.shown.id}
        <dl class="cmp">
          <dt>{t('prediction.cmp.agreement')}</dt><dd>{pct(compare.agreement_pct)}</dd>
          <dt>{t('prediction.cmp.received')}</dt><dd>{compare.received_covered} / {compare.received_uncovered}</dd>
          <dt>{t('prediction.cmp.missing')}</dt><dd>{compare.missing_covered} / {compare.missing_uncovered}</dd>
          <dt>{t('prediction.cmp.bias')}</dt><dd>{db(compare.rssi_bias_db)}</dd>
          <dt>{t('prediction.cmp.rmse')}</dt><dd>{db(compare.rssi_rmse_db)}</dd>
        </dl>
      {/if}
    {/if}

    <p class="attr">{t('prediction.attr')}</p>
  </section>
</Card>

<Modal open={estimate !== null} title={t('prediction.dl.title')} confirmLabel={t('prediction.dl.confirm')} cancelLabel={t('common.cancel')}
  onconfirm={() => start(true)} oncancel={() => (estimate = null)}>
  {#if estimate}
    <p>{t('prediction.dl.body', { n: estimate.tiles_missing, mb })}</p>
  {/if}
</Modal>

<Modal open={confirmDeleteId !== null} title={t('prediction.del.title')} danger confirmLabel={t('prediction.delete')} onconfirm={remove}
  oncancel={() => (confirmDeleteId = null)}>
  <p>{t('prediction.del.body')}</p>
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
