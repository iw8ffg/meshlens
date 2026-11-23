<script lang="ts">
  import { getJSON, metrics, snr, telemetry } from '../lib/api'
  import { ago, num } from '../lib/format'
  import { t, type MsgKey } from '../lib/i18n/index.svelte'
  import { batterySeries, pctRange, voltageSeries, type Pt } from '../lib/chart'
  import { dupeRatio, formatMetric, metricInfo, orderMetrics } from '../lib/metrics'
  import { hasPax, paxSeries } from '../lib/sensors'
  import type { AppSettings } from '../lib/settings'
  import type { MetricsResponse, SnrPoint, TelemetryPoint } from '../lib/types'
  import LineChart from './charts/LineChart.svelte'

  let { nodeId }: { nodeId: string } = $props()

  const PERIODS: { labelKey: MsgKey; hours: number }[] = [
    { labelKey: 'nodes.age24h', hours: 24 },
    { labelKey: 'nodes.age7d', hours: 168 },
    { labelKey: 'nodes.period30d', hours: 720 },
    { labelKey: 'nodes.period90d', hours: 2160 },
  ]
  const MAX_SENSOR_CHARTS = 8

  let hours = $state(168)
  let tel = $state<TelemetryPoint[]>([])
  let met = $state<MetricsResponse>({ latest: {}, series: {} })
  let snrPts = $state<SnrPoint[]>([])
  let loading = $state(false)
  let error = $state(false)
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
    error = false
    const current = () => id === nodeId && h === hours
    // Una richiesta fallita (es. telemetria 404 di un nodo non in memoria) non nasconde le altre
    Promise.allSettled([telemetry(id, h), metrics(id, h), snr(id, h)])
      .then(([tl, m, s]) => {
        if (!current()) return
        if (tl.status === 'fulfilled') tel = [...tl.value].sort((a, b) => a.time - b.time)
        if (m.status === 'fulfilled') met = m.value
        if (s.status === 'fulfilled') snrPts = [...s.value].sort((a, b) => a.time - b.time)
        if (tl.status === 'rejected' && m.status === 'rejected' && s.status === 'rejected') error = true
        loadedAt = Date.now() / 1000
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
      .filter((k) => !k.startsWith('paxcounter.') && metricInfo(k).chart !== false && met.series[k].length > 0)
      .slice(0, MAX_SENSOR_CHARTS)
      .map((k) => {
        const pts: Pt[] = met.series[k].map(([time, v]) => ({ t: time, v }))
        return { key: k, info: metricInfo(k), pts, ext: extent([pts]) }
      }),
  )
  const pax = $derived(paxSeries(met.series))
  const paxExt = $derived(extent([pax.wifi, pax.ble]))
  const hasPaxChart = $derived(hasPax(met.series))
  const hasSensors = $derived(latestKeys.length > 0 || sensorCharts.length > 0 || hasPaxChart)
  const empty = $derived(!hasBat && !hasChan && !hasSnr && !hasSensors)
</script>

<h3>{t('nodes.charts.title')}</h3>
<div class="periods" role="group" aria-label={t('nodes.charts.period')}>
  {#each PERIODS as p (p.hours)}
    <button type="button" class="ui-chip" aria-pressed={hours === p.hours} onclick={() => (hours = p.hours)}>{t(p.labelKey)}</button>
  {/each}
</div>
{#if error}
  <p class="msg">{t('nodes.charts.unavailable')}</p>
{:else if loading && empty}
  <p class="none">{t('shell.loading')}</p>
{:else if empty}
  <p class="none">{t('nodes.charts.noData')}</p>
{:else}
  {#if hasBat}
    <h4>{t('nodes.charts.batteryVoltage')}</h4>
    <LineChart
      label={t('nodes.charts.batteryVoltageAria')}
      x0={batExt[0]}
      x1={batExt[1]}
      left={[0, 100]}
      threshold={{ value: threshold, label: t('nodes.charts.threshold', { n: threshold }) }}
      series={[
        { key: 'battery', label: t('nodes.charts.battery'), unit: '%', digits: 0, color: 'ok', axis: 'left', points: bat },
        { key: 'voltage', label: t('nodes.charts.voltage'), unit: 'V', digits: 2, color: 'accent', dash: true, axis: 'right', points: volt },
      ]}
    />
  {/if}
  {#if hasChan}
    <h4>{t('nodes.charts.channelAir')}</h4>
    <LineChart
      label={t('nodes.charts.channelAirAria')}
      x0={chanExt[0]}
      x1={chanExt[1]}
      left={chanRange}
      series={[
        { key: 'channel_util', label: t('nodes.charts.channelUtil'), unit: '%', digits: 1, color: 'accent', points: chan },
        { key: 'air_util_tx', label: t('nodes.charts.airTx'), unit: '%', digits: 1, color: 'amber', dash: true, points: air },
      ]}
    />
  {/if}
  {#if hasSnr}
    <h4>{t('nodes.charts.signal')}</h4>
    <LineChart
      label={t('nodes.charts.signalAria')}
      x0={snrExt[0]}
      x1={snrExt[1]}
      series={[
        { key: 'snr_rf', label: t('nodes.sourceRadio'), unit: 'dB', digits: 1, color: 'radio', points: snrRf },
        { key: 'snr_mqtt', label: 'MQTT', unit: 'dB', digits: 1, color: 'mqtt', dash: true, points: snrMq },
      ]}
    />
  {/if}
  {#if hasSensors}
    <h4>{t('nodes.charts.sensors')}</h4>
    {#if latestKeys.length > 0}
      <p class="sub">{t('nodes.charts.latest')}</p>
      <dl class="latest">
        {#each latestKeys as k (k)}
          <dt>{metricInfo(k).label}</dt>
          <dd>
            {formatMetric(k, met.latest[k].value)}
            <span class="ui-muted">{ago(Math.max(0, (loadedAt - met.latest[k].time) / 60))}</span>
          </dd>
        {/each}
      </dl>
      {#if dupe !== null}<p class="sub">{t('nodes.charts.dupes', { pct: num(dupe * 100, 0) })}</p>{/if}
    {/if}
    {#if hasPaxChart}
      <p class="sub">{t('sensors.pax.title')}</p>
      <LineChart
        label={t('sensors.pax.aria')}
        x0={paxExt[0]}
        x1={paxExt[1]}
        series={[
          { key: 'pax_wifi', label: t('sensors.pax.wifi'), unit: '', digits: 0, color: 'accent', points: pax.wifi },
          { key: 'pax_ble', label: t('sensors.pax.ble'), unit: '', digits: 0, color: 'amber', dash: true, points: pax.ble },
        ]}
      />
    {/if}
    {#each sensorCharts as c (c.key)}
      <p class="sub">{c.info.label}</p>
      <LineChart
        label={t('nodes.charts.chartOf', { name: c.info.label })}
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
