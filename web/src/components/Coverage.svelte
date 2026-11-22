<script lang="ts">
  import { coverageSession, deleteCoverage, patchCoverage, stopCoverage } from '../lib/api'
  import { formatLoss } from '../lib/coverage'
  import { downloadText } from '../lib/download'
  import { coverageCsv, coverageGeoJSONFile, coverageKml, slug, snrColorsFromTokens } from '../lib/export'
  import { formatDate } from '../lib/format'
  import { formatMeters } from '../lib/geo'
  import { t } from '../lib/i18n/index.svelte'
  import { applyCoverage, coverage } from '../lib/stores.svelte'
  import type { CoverageSession } from '../lib/types'
  import Prediction from './Prediction.svelte'
  import CoverageSetup from './CoverageSetup.svelte'
  import CoverageRestoreBox from './CoverageRestoreBox.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Modal from '../lib/ui/Modal.svelte'

  let { now }: { now: number } = $props()

  const active = $derived(coverage.sessions.find((s) => s.ended === null) ?? null)
  let prepared = $state(0) // cresce a ogni preparazione terminata: ricarica il riquadro di ripristino
  let creating = $state(false)
  let error = $state('')
  let name = $state('')
  let notes = $state('')
  let confirmDelete = $state(false)

  const duration = (s: CoverageSession) => {
    const m = Math.max(0, Math.round(((s.ended ?? now) - s.started) / 60))
    return m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`
  }
  const dist = (s: CoverageSession) => (s.max_distance_m === null ? '—' : formatMeters(s.max_distance_m))
  const msg = (e: unknown) => (e instanceof Error ? e.message : t('coverage.error'))

  // Chiude il modulo di avvio quando parte una sessione
  $effect(() => {
    if (active) creating = false
  })

  async function stop(s: CoverageSession) {
    error = ''
    try {
      applyCoverage(await stopCoverage(s.id), null)
    } catch (e) {
      error = msg(e)
    }
  }

  async function open(s: CoverageSession) {
    coverage.openId = s.id
    confirmDelete = false
    name = s.name
    notes = s.notes
    error = ''
    try {
      const d = await coverageSession(s.id)
      if (coverage.openId === s.id) coverage.detail = d
    } catch (e) {
      error = msg(e)
    }
  }

  // Esportazione del dettaglio aperto: nome file meshlens-copertura-<id>-<nome>.<estensione>
  function exportDetail(kind: 'geojson' | 'kml' | 'csv') {
    const d = coverage.detail
    if (!d) return
    const base = `meshlens-copertura-${d.id}-${slug(d.name)}`
    if (kind === 'geojson') downloadText(`${base}.geojson`, 'application/geo+json', coverageGeoJSONFile(d))
    else if (kind === 'kml') downloadText(`${base}.kml`, 'application/vnd.google-earth.kml+xml', coverageKml(d, snrColorsFromTokens()))
    else downloadText(`${base}.csv`, 'text/csv', coverageCsv(d))
  }

  function closeDetail() {
    coverage.openId = null
    coverage.detail = null
  }

  async function save() {
    const id = coverage.openId
    if (id === null) return
    error = ''
    try {
      const s = await patchCoverage(id, { name: name.trim() || undefined, notes })
      const i = coverage.sessions.findIndex((x) => x.id === id)
      if (i >= 0) coverage.sessions[i] = s
      if (coverage.detail?.id === id) coverage.detail = { ...coverage.detail, ...s }
    } catch (e) {
      error = msg(e)
    }
  }

  async function remove() {
    const id = coverage.openId
    if (id === null) return
    error = ''
    try {
      await deleteCoverage(id)
      coverage.sessions = coverage.sessions.filter((s) => s.id !== id)
      closeDetail()
      confirmDelete = false
    } catch (e) {
      error = msg(e)
    }
  }

  const opened = $derived(coverage.sessions.find((s) => s.id === coverage.openId) ?? null)
</script>

<div class="cov">
  {#if active}
    {@const last = coverage.last?.id === active.id ? coverage.last : null}
    <Banner kind="ok" title={t('coverage.active.title', { name: active.name })}>
      {t('coverage.active.points', { n: active.received })}{#if active.missing !== null}{t('coverage.active.missing', { n: active.missing, loss: formatLoss(active) })}{/if}{#if last && last.snr !== null}{t('coverage.active.lastSnr')} <span class="ui-mono">{last.snr}</span> dB{/if}{t('coverage.active.since', { d: duration(active) })}
      {#snippet action()}
        <Button kind="danger" icon="x" onclick={() => stop(active)}>{t('coverage.stop')}</Button>
      {/snippet}
    </Banner>
  {/if}
  <CoverageRestoreBox reloadKey={coverage.sessions.filter((s) => s.ended !== null).length + (active ? 1000 : 0) + prepared * 10000} />
  <div class="bar">
    <Button kind="primary" icon="plus" disabled={!!active} onclick={() => (creating = !creating)}>{t('coverage.new')}</Button>
  </div>
  {#if creating && !active}
    <CoverageSetup onprepared={() => prepared++} />
  {/if}
  {#if error}<Banner kind="danger" title={error} />{/if}

  {#if opened}
    <Card>
      <section class="detail">
        <div><Button kind="ghost" icon="back" onclick={closeDetail}>{t('coverage.history')}</Button></div>
        <Field label={t('coverage.name')} for="cov-name">
          {#snippet children()}<input id="cov-name" class="ui-input" bind:value={name} />{/snippet}
        </Field>
        <Field label={t('coverage.notes')} for="cov-notes">
          {#snippet children()}<textarea id="cov-notes" class="ui-input area" rows="3" bind:value={notes}></textarea>{/snippet}
        </Field>
        <p class="meta">
          {t('coverage.meta', { date: formatDate(opened.started), dur: duration(opened), n: opened.received, loss: formatLoss(opened), dist: dist(opened) })}
        </p>
        <div class="row" role="group" aria-label={t('coverage.export')}>
          <Button icon="download" disabled={!coverage.detail} onclick={() => exportDetail('geojson')}>GeoJSON</Button>
          <Button icon="download" disabled={!coverage.detail} onclick={() => exportDetail('kml')}>KML</Button>
          <Button icon="download" disabled={!coverage.detail} onclick={() => exportDetail('csv')}>CSV</Button>
        </div>
        <div class="row">
          <Button kind="primary" onclick={save}>{t('coverage.save')}</Button>
          {#if opened.ended !== null}
            <Button kind="danger" icon="trash" onclick={() => (confirmDelete = true)}>{t('coverage.delete')}</Button>
          {/if}
        </div>
      </section>
    </Card>
    <Modal open={confirmDelete} title={t('coverage.delete.title')} danger confirmLabel={t('coverage.delete')} onconfirm={remove} oncancel={() => (confirmDelete = false)}>
      <p>{t('coverage.delete.body')}</p>
    </Modal>
  {:else}
    <h3>{t('coverage.history')}</h3>
    {#if coverage.sessions.length === 0}
      <Empty icon="coverage" title={t('coverage.empty.title')}>{t('coverage.empty.body')}</Empty>
    {:else}
      <ul class="hist">
        {#each coverage.sessions as s (s.id)}
          <li>
            <button onclick={() => open(s)}>
              <b>{s.name}</b>
              <small>
                {t('coverage.item.meta', { date: formatDate(s.started), dur: duration(s), n: s.received, loss: formatLoss(s), dist: dist(s), running: s.ended === null ? ` ${t('coverage.item.running')}` : '' })}
              </small>
            </button>
          </li>
        {/each}
      </ul>
    {/if}
  {/if}
  <Prediction />
</div>

<style>
  .cov { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  .hist { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .hist button { width: 100%; min-height: var(--touch-min); text-align: left; padding: var(--space-3); border: 1px solid var(--line); border-radius: var(--radius-md); background: var(--surface-raised); color: var(--ink); font: 400 14px/20px var(--font-sans); cursor: pointer; display: flex; flex-direction: column; gap: 2px; }
  .hist button:hover { border-color: var(--line-strong); }
  .hist small { color: var(--ink-muted); font-size: 13px; }
  .detail { display: flex; flex-direction: column; gap: var(--space-3); }
  .area { height: auto; padding: var(--space-2) var(--space-3); resize: vertical; }
  .meta { margin: 0; font: 400 13px/18px var(--font-sans); color: var(--ink-muted); }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  :global(.vp-phone) .hist small, :global(.vp-phone) .meta { font-size: 14px; line-height: 20px; }
</style>
