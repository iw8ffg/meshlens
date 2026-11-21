<script lang="ts">
  import { getJSON, telemetry } from '../lib/api'
  import { batterySeries, isolatedPoints, linePath, niceRange, voltageSeries } from '../lib/chart'
  import type { AppSettings } from '../lib/settings'
  import type { TelemetryPoint } from '../lib/types'

  let { nodeId }: { nodeId: string } = $props()

  const PERIODS = [
    { label: '24 h', hours: 24 },
    { label: '7 g', hours: 168 },
    { label: '30 g', hours: 720 },
  ]
  const W = 300
  const H = 120

  let hours = $state(168)
  let points = $state<TelemetryPoint[]>([])
  let loading = $state(false)
  let error = $state('')
  let threshold = $state(20)

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
    points = []
    loading = true
    error = ''
    telemetry(id, h)
      .then((p) => {
        if (id === nodeId && h === hours) points = [...p].sort((a, b) => a.time - b.time)
      })
      .catch(() => {
        if (id === nodeId && h === hours) {
          points = []
          error = 'Telemetria non disponibile'
        }
      })
      .finally(() => {
        if (id === nodeId && h === hours) loading = false
      })
  })

  const x0 = $derived(points.length ? points[0].time : 0)
  const x1 = $derived(points.length ? points[points.length - 1].time : 1)
  const bat = $derived(batterySeries(points))
  const volt = $derived(voltageSeries(points))
  const hasBat = $derived(bat.some((p) => p.v !== null))
  const vVals = $derived(volt.flatMap((p) => (p.v === null ? [] : [p.v])))
  const vRange = $derived(niceRange(vVals, 0.1))
  const batPath = $derived(linePath(bat, x0, x1, 0, 100, W, H))
  const voltPath = $derived(linePath(volt, x0, x1, vRange[0], vRange[1], W, H))
  const batDots = $derived(isolatedPoints(bat, x0, x1, 0, 100, W, H))
  const voltDots = $derived(isolatedPoints(volt, x0, x1, vRange[0], vRange[1], W, H))
  const thY = $derived(H - (threshold / 100) * H)
  const fmtV = (v: number) => v.toFixed(1).replace('.', ',')
</script>

<h3>Telemetria</h3>
<div class="periods" role="group" aria-label="Periodo">
  {#each PERIODS as p (p.hours)}
    <button class:on={hours === p.hours} aria-pressed={hours === p.hours} onclick={() => (hours = p.hours)}>
      {p.label}
    </button>
  {/each}
</div>
{#if error}
  <p class="msg">{error}</p>
{:else if loading && points.length === 0}
  <p class="none">Caricamento…</p>
{:else if points.length === 0 || (!hasBat && vVals.length === 0)}
  <p class="none">Nessun dato di telemetria nel periodo</p>
{:else}
  <div class="chart">
    <svg viewBox="0 0 {W} {H}" role="img" aria-label="Grafico batteria e tensione" preserveAspectRatio="none">
      <rect x="0" y="0" width={W} height={H} class="bg" />
      <line x1="0" x2={W} y1={thY} y2={thY} class="thr" />
      {#if voltPath}<path d={voltPath} class="volt" />{/if}
      {#if batPath}<path d={batPath} class="bat" />{/if}
      {#each voltDots as d, i (i)}<circle cx={d.x} cy={d.y} r="2.5" class="dot volt" />{/each}
      {#each batDots as d, i (i)}<circle cx={d.x} cy={d.y} r="2.5" class="dot bat" />{/each}
    </svg>
    <div class="axis left"><span>100%</span><span>0%</span></div>
    <div class="axis right"><span>{fmtV(vRange[1])} V</span><span>{fmtV(vRange[0])} V</span></div>
  </div>
  <p class="legend">
    <span class="k bat">Batteria %</span>
    <span class="k volt">Tensione V</span>
    <span class="k thr">Soglia {threshold}%</span>
  </p>
{/if}

<style>
  h3 {
    font-size: 14px;
    margin: 10px 0 4px;
  }
  .periods {
    display: flex;
    gap: 4px;
    margin-bottom: 6px;
  }
  .periods button {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 2px 10px;
    cursor: pointer;
    font-size: 13px;
  }
  .periods button.on {
    background: #2563eb;
    border-color: #2563eb;
  }
  .chart {
    position: relative;
    padding: 0 44px;
  }
  svg {
    width: 100%;
    height: 120px;
    display: block;
  }
  .bg {
    fill: #111827;
  }
  path {
    fill: none;
    stroke-width: 1.5;
    vector-effect: non-scaling-stroke;
  }
  path.bat {
    stroke: #34d399;
  }
  path.volt {
    stroke: #60a5fa;
  }
  circle.dot.bat {
    fill: #34d399;
  }
  circle.dot.volt {
    fill: #60a5fa;
  }
  line.thr {
    stroke: #f87171;
    stroke-width: 1;
    stroke-dasharray: 4 3;
    vector-effect: non-scaling-stroke;
  }
  .axis {
    position: absolute;
    top: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    font-size: 11px;
    color: #9ca3af;
  }
  .axis.left {
    left: 0;
  }
  .axis.right {
    right: 0;
  }
  .legend {
    display: flex;
    gap: 10px;
    font-size: 12px;
    margin: 4px 0;
  }
  .k.bat {
    color: #34d399;
  }
  .k.volt {
    color: #60a5fa;
  }
  .k.thr {
    color: #f87171;
  }
  .none {
    margin: 0 0 8px;
    font-size: 13px;
    color: #9ca3af;
  }
  .msg {
    color: #fbbf24;
    font-size: 13px;
  }
</style>
