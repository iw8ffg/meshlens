<script lang="ts">
  import { getJSON, metrics, snr, telemetry } from '../lib/api'
  import { ago, num } from '../lib/format'
  import { batterySeries, pctRange, voltageSeries, type Pt } from '../lib/chart'
  import { dupeRatio, formatMetric, metricInfo, orderMetrics } from '../lib/metrics'
  import type { AppSettings } from '../lib/settings'
  import type { MetricsResponse, SnrPoint, TelemetryPoint } from '../lib/types'
  import LineChart from './charts/LineChart.svelte'

  let { nodeId }: { nodeId: string } = $props()

  const PERIODS = [
    { label: '24 h', hours: 24 },
    { label: '7 g', hours: 168 },
    { label: '30 g', hours: 720 },
    { label: '90 g', hours: 2160 },
  ]
  const MAX_SENSOR_CHARTS = 8

  let hours = $state(168)
  let tel = $state<TelemetryPoint[]>([])
  let met = $state<MetricsResponse>({ latest: {}, series: {} })
  let snrPts = $state<SnrPoint[]>([])
  let loading = $state(false)
  let error = $state('')
  let threshold = $state(20)
  let loadedAt = $state(0)

  $effect(() => {
    getJSON<AppSettings>('/settings')
      .then((s) => {
        if (typeof s.battery_alert_pct === 'number') threshold = s.battery_alert_pct
      })
      .catch(() => {
        /* resta il default */
      })
  })

  $effect(() => {
    const id = nodeId
    const h = hours
    tel = []
    met = { latest: {}, series: {} }
    snrPts = []
    loading = true
    error = ''
    const current = () => id === nodeId && h === hours
    Promise.all([telemetry(id, h), metrics(id, h), snr(id, h)])
      .then(([t, m, s]) => {
        if (!current()) return
        tel = [...t].sort((a, b) => a.time - b.time)
        met = m
        snrPts = [...s].sort((a, b) => a.time - b.time)
        loadedAt = Date.now() / 1000
      })
      .catch(() => {
        if (current()) error = 'Dati non disponibili'
      })
      .finally(() => {
        if (current()) loading = false
      })
  })

  function extent(lists: Pt[][]): [number, number] {
    const ts = lists.flatMap((l) => l.filter((p) => p.v !== null).map((p) => p.t))
    if (ts.length === 0) return [0, 1]
    return [Math.min(...ts), Math.max(...ts)]
  }
  const vals = (l: Pt[]) => l.flatMap((p) => (p.v === null ? [] : [p.v]))
  const col = (key: 'channel_util' | 'air_util_tx'): Pt[] => tel.map((p) => ({ t: p.time, v: p[key] }))

  const bat = $derived(batterySeries(tel))
  const volt = $derived(voltageSeries(tel))
  const batExt = $derived(extent([bat, volt]))
  const hasBat = $derived(vals(bat).length > 0 || vals(volt).length > 0)

  const chan = $derived(col('channel_util'))
  const air = $derived(col('air_util_tx'))
  const chanExt = $derived(extent([chan, air]))
  const chanRange = $derived(pctRange([...vals(chan), ...vals(air)]))
  const hasChan = $derived(vals(chan).length > 0 || vals(air).length > 0)

  const snrRf = $derived<Pt[]>(snrPts.filter((p) => p.source === 'rf').map((p) => ({ t: p.time, v: p.snr_avg })))
  const snrMq = $derived<Pt[]>(snrPts.filter((p) => p.source === 'mqtt').map((p) => ({ t: p.time, v: p.snr_avg })))
  const snrExt = $derived(extent([snrRf, snrMq]))
  const hasSnr = $derived(vals(snrRf).length > 0 || vals(snrMq).length > 0)

  const latestKeys = $derived(orderMetrics(Object.keys(met.latest)))
  const dupe = $derived(dupeRatio(met.latest))
  const sensorCharts = $derived(
    orderMetrics(Object.keys(met.series))
      .filter((k) => metricInfo(k).chart !== false && met.series[k].length > 0)
      .slice(0, MAX_SENSOR_CHARTS)
      .map((k) => {
        const pts: Pt[] = met.series[k].map(([t, v]) => ({ t, v }))
        return { key: k, info: metricInfo(k), pts, ext: extent([pts]) }
      }),
  )
  const hasSensors = $derived(latestKeys.length > 0 || sensorCharts.length > 0)
  const empty = $derived(!hasBat && !hasChan && !hasSnr && !hasSensors)
</script>

<h3>Telemetria</h3>
<div class="periods" role="group" aria-label="Periodo">
  {#each PERIODS as p (p.hours)}
    <button type="button" class="ui-chip" aria-pressed={hours === p.hours} onclick={() => (hours = p.hours)}>{p.label}</button>
  {/each}
</div>
{#if error}
  <p class="msg">{error}</p>
{:else if loading && empty}
  <p class="none">Caricamento…</p>
{:else if empty}
  <p class="none">Nessun dato nel periodo</p>
{:else}
  {#if hasBat}
    <h4>Batteria e tensione</h4>
    <LineChart
      label="Grafico batteria e tensione"
      x0={batExt[0]}
      x1={batExt[1]}
      left={[0, 100]}
      threshold={{ value: threshold, label: `Soglia ${threshold}%` }}
      series={[
        { key: 'battery', label: 'Batteria', unit: '%', digits: 0, color: 'ok', axis: 'left', points: bat },
        { key: 'voltage', label: 'Tensione', unit: 'V', digits: 2, color: 'accent', dash: true, axis: 'right', points: volt },
      ]}
    />
  {/if}
  {#if hasChan}
    <h4>Uso del canale e trasmissione</h4>
    <LineChart
      label="Grafico uso del canale e trasmissione"
      x0={chanExt[0]}
      x1={chanExt[1]}
      left={chanRange}
      series={[
        { key: 'channel_util', label: 'Uso del canale', unit: '%', digits: 1, color: 'accent', points: chan },
        { key: 'air_util_tx', label: 'Trasmissione', unit: '%', digits: 1, color: 'amber', dash: true, points: air },
      ]}
    />
  {/if}
  {#if hasSnr}
    <h4>Segnale (SNR)</h4>
    <LineChart
      label="Grafico del segnale SNR"
      x0={snrExt[0]}
      x1={snrExt[1]}
      series={[
        { key: 'snr_rf', label: 'Radio', unit: 'dB', digits: 1, color: 'radio', points: snrRf },
        { key: 'snr_mqtt', label: 'MQTT', unit: 'dB', digits: 1, color: 'mqtt', dash: true, points: snrMq },
      ]}
    />
  {/if}
  {#if hasSensors}
    <h4>Sensori</h4>
    {#if latestKeys.length > 0}
      <p class="sub">Ultimi valori</p>
      <dl class="latest">
        {#each latestKeys as k (k)}
          <dt>{metricInfo(k).label}</dt>
          <dd>
            {formatMetric(k, met.latest[k].value)}
            <span class="ui-muted">{ago(Math.max(0, (loadedAt - met.latest[k].time) / 60))}</span>
          </dd>
        {/each}
      </dl>
      {#if dupe !== null}<p class="sub">Duplicati ricevuti: {num(dupe * 100, 0)} %</p>{/if}
    {/if}
    {#each sensorCharts as c (c.key)}
      <p class="sub">{c.info.label}</p>
      <LineChart
        label={`Grafico: ${c.info.label}`}
        x0={c.ext[0]}
        x1={c.ext[1]}
        series={[{ key: c.key, label: c.info.label, unit: c.info.unit, digits: c.info.digits, color: 'accent', points: c.pts }]}
      />
    {/each}
  {/if}
{/if}

<style>
  h3 {
    font: 600 14px/20px var(--font-sans);
    margin: var(--space-4) 0 var(--space-2);
  }
  h4 {
    font: 600 13px/18px var(--font-sans);
    margin: var(--space-3) 0 var(--space-2);
  }
  .periods {
    display: flex;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
    flex-wrap: wrap;
  }
  .sub {
    margin: var(--space-2) 0 var(--space-1);
    font-size: 13px;
    color: var(--ink-muted);
  }
  .latest {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--space-1) var(--space-3);
    margin: 0 0 var(--space-2);
    font-size: 13px;
  }
  .latest dt {
    color: var(--ink-muted);
  }
  .latest dd {
    margin: 0;
  }
  .none {
    margin: 0 0 var(--space-2);
    font-size: 13px;
    color: var(--ink-muted);
  }
  .msg {
    color: var(--warn);
    font-size: 13px;
  }
  :global(.vp-phone) .periods :global(.ui-chip) {
    min-height: 44px;
  }
  :global(.vp-phone) .none,
  :global(.vp-phone) .msg,
  :global(.vp-phone) .sub,
  :global(.vp-phone) .latest {
    font-size: 14px;
  }
</style>
