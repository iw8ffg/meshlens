<script lang="ts">
  import { getJSON, telemetry } from '../lib/api'
  import { num } from '../lib/format'
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
  const fmtV = (v: number) => num(v, 1)
</script>

<h3>Telemetria</h3>
<div class="periods" role="group" aria-label="Periodo">
  {#each PERIODS as p (p.hours)}
    <button type="button" class="ui-chip" aria-pressed={hours === p.hours} onclick={() => (hours = p.hours)}>{p.label}</button>
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
    <span class="k bat"><i></i>Batteria %</span>
    <span class="k volt"><i></i>Tensione V</span>
    <span class="k thr"><i></i>Soglia {threshold}%</span>
  </p>
{/if}

<style>
  h3 {
    font: 600 14px/20px var(--font-sans);
    margin: var(--space-4) 0 var(--space-2);
  }
  .periods {
    display: flex;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
  }
  .chart {
    position: relative;
    padding: 0 48px;
  }
  svg {
    width: 100%;
    height: 120px;
    display: block;
    border-radius: var(--radius-sm);
  }
  .bg {
    fill: var(--surface-sunken);
  }
  path {
    fill: none;
    stroke-width: 2;
    vector-effect: non-scaling-stroke;
  }
  path.bat {
    stroke: var(--ok);
  }
  path.volt {
    stroke: var(--accent);
    stroke-dasharray: 6 3;
  }
  circle.dot.bat {
    fill: var(--ok);
  }
  circle.dot.volt {
    fill: var(--accent);
  }
  line.thr {
    stroke: var(--danger);
    stroke-width: 1;
    stroke-dasharray: 1 3;
    vector-effect: non-scaling-stroke;
  }
  .axis {
    position: absolute;
    top: 0;
    bottom: 0;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    font: 400 12px/16px var(--font-mono);
    color: var(--ink-muted);
  }
  .axis.left {
    left: 0;
  }
  .axis.right {
    right: 0;
  }
  .legend {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
    font-size: 12px;
    margin: var(--space-2) 0;
    color: var(--ink-muted);
  }
  .k {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .k i {
    width: 18px;
    height: 0;
    border-top: 2px solid;
  }
  .k.bat i {
    border-color: var(--ok);
  }
  .k.volt i {
    border-color: var(--accent);
    border-top-style: dashed;
  }
  .k.thr i {
    border-color: var(--danger);
    border-top-style: dotted;
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
  :global(.vp-phone) .axis,
  :global(.vp-phone) .legend,
  :global(.vp-phone) .none,
  :global(.vp-phone) .msg {
    font-size: 14px;
  }
</style>
