<script lang="ts">
  // Confronto di 2–3 nodi sullo stesso grafico: una grandezza e un periodo scelti, una linea per nodo.
  import { untrack } from 'svelte'
  import { snr, telemetry } from '../lib/api'
  import type { Pt } from '../lib/chart'
  import {
    COMPARE_COLORS,
    COMPARE_METRICS,
    compareMeta,
    compareSeries,
    extentOf,
  } from '../lib/health'
  import { t, type MsgKey } from '../lib/i18n/index.svelte'
  import type { CompareMetric, SnrPoint, TelemetryPoint } from '../lib/types'
  import Segmented from '../lib/ui/Segmented.svelte'
  import LineChart from './charts/LineChart.svelte'

  let { nodeIds, nodes }: { nodeIds: string[]; nodes: Map<string, string> } = $props()

  const PERIODS: { labelKey: MsgKey; hours: number }[] = [
    { labelKey: 'nodes.age24h', hours: 24 },
    { labelKey: 'nodes.age7d', hours: 168 },
    { labelKey: 'nodes.period30d', hours: 720 },
  ]

  let metric = $state<CompareMetric>('battery')
  let hours = $state(168)
  let data = $state<Record<string, { tel: TelemetryPoint[]; snr: SnrPoint[] } | null>>({})
  let loading = $state(false)
  let seq = 0

  const metricItems = $derived(COMPARE_METRICS.map((m) => ({ value: m, label: t(compareMeta(m).labelKey) })))
  const meta = $derived(compareMeta(metric))

  $effect(() => {
    const ids = [...nodeIds]
    const h = hours
    untrack(() => {
      const mine = ++seq
      loading = true
      Promise.all(
        ids.map(async (id) => {
          const [tl, s] = await Promise.allSettled([telemetry(id, h), snr(id, h)])
          if (tl.status === 'rejected' && s.status === 'rejected') return [id, null] as const
          const sort = <T extends { time: number }>(l: T[]) => [...l].sort((a, b) => a.time - b.time)
          return [id, { tel: tl.status === 'fulfilled' ? sort(tl.value) : [], snr: s.status === 'fulfilled' ? sort(s.value) : [] }] as const
        }),
      ).then((rows) => {
        if (mine !== seq) return // risposta superata da una scelta più recente
        data = Object.fromEntries(rows)
        loading = false
      })
    })
  })

  const lines = $derived(
    nodeIds.map((id, i) => {
      const d = data[id]
      const points: Pt[] = d ? compareSeries(metric, d.tel, d.snr) : []
      return {
        key: id,
        label: nodes.get(id) ?? id,
        unit: meta.unit,
        digits: meta.digits,
        color: COMPARE_COLORS[i % COMPARE_COLORS.length],
        dash: i % 2 === 1,
        points,
      }
    }),
  )
  const ext = $derived(extentOf(lines.map((l) => l.points)))
  const empty = $derived(lines.filter((l) => l.points.some((p) => p.v !== null)))
  const missing = $derived(lines.filter((l) => !l.points.some((p) => p.v !== null)))
</script>

<div class="cmp">
  <Segmented items={metricItems} bind:value={metric} label={t('health.compare.metricAria')} />
  <div class="periods" role="group" aria-label={t('health.compare.periodAria')}>
    {#each PERIODS as p (p.hours)}
      <button type="button" class="ui-chip" aria-pressed={hours === p.hours} onclick={() => (hours = p.hours)}>{t(p.labelKey)}</button>
    {/each}
  </div>
  {#if loading && empty.length === 0}
    <p class="ui-hint">{t('shell.loading')}</p>
  {:else}
    {#if empty.length > 0}
      <LineChart label={t('health.compare.aria')} x0={ext[0]} x1={ext[1]} left={meta.fixedRange} series={lines} />
    {/if}
    {#each missing as l (l.key)}
      <p class="ui-hint">{t('health.noData', { name: l.label })}</p>
    {/each}
  {/if}
</div>

<style>
  .cmp { display: flex; flex-direction: column; gap: var(--space-2); }
  .periods { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  p { margin: 0; }
  :global(.vp-phone) .periods :global(.ui-chip) { min-height: 44px; }
  :global(.vp-phone) .ui-hint { font-size: 14px; line-height: 20px; }
</style>
