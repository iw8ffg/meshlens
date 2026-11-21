<script lang="ts">
  import { chartTime, isolatedPoints, linePath, nearestIndex, niceRange, type Pt } from '../../lib/chart'
  import { num } from '../../lib/format'

  type Color = 'accent' | 'ok' | 'warn' | 'danger' | 'sky' | 'teal' | 'amber' | 'radio' | 'mqtt'
  interface Series {
    key: string
    label: string
    unit: string
    digits: number
    color: Color
    dash?: boolean
    axis?: 'left' | 'right'
    points: Pt[]
  }

  let {
    series,
    x0,
    x1,
    left,
    right,
    threshold,
    height = 120,
    label,
  }: {
    series: Series[]
    x0: number
    x1: number
    left?: [number, number]
    right?: [number, number]
    threshold?: { value: number; label: string }
    height?: number
    label: string
  } = $props()

  const COLORS: Record<Color, string> = {
    accent: 'var(--accent)',
    ok: 'var(--ok)',
    warn: 'var(--warn)',
    danger: 'var(--danger)',
    sky: 'var(--brand-sky)',
    teal: 'var(--brand-teal)',
    amber: 'var(--brand-amber)',
    radio: 'var(--src-radio)',
    mqtt: 'var(--src-mqtt)',
  }
  const W = 300

  const sideOf = (s: Series) => s.axis ?? 'left'
  const valuesOf = (side: 'left' | 'right') =>
    series.filter((s) => sideOf(s) === side).flatMap((s) => s.points.flatMap((p) => (p.v === null ? [] : [p.v])))
  const leftR = $derived(left ?? niceRange(valuesOf('left'), 0.1))
  const rightR = $derived(right ?? niceRange(valuesOf('right'), 0.1))
  const hasRight = $derived(series.some((s) => sideOf(s) === 'right'))
  const rangeOf = (s: Series): [number, number] => (sideOf(s) === 'right' ? rightR : leftR)
  const unitOf = (side: 'left' | 'right') => series.find((s) => sideOf(s) === side)?.unit ?? ''
  const axisText = (v: number, side: 'left' | 'right') => {
    const u = unitOf(side)
    return (u ? `${num(v, 1)} ${u}` : num(v, 1)).replace('-', '−')
  }

  const drawn = $derived(
    series.map((s) => {
      const [y0, y1] = rangeOf(s)
      return {
        s,
        d: linePath(s.points, x0, x1, y0, y1, W, height),
        dots: isolatedPoints(s.points, x0, x1, y0, y1, W, height),
      }
    }),
  )
  const thY = $derived(threshold ? height - ((threshold.value - leftR[0]) / (leftR[1] - leftR[0] || 1)) * height : 0)
  const spanHours = $derived(Math.max(0, x1 - x0) / 3600)

  /** Tempo del cursore (secondi), null = nascosto. */
  let cursor = $state<number | null>(null)
  let svgEl = $state<SVGSVGElement>()

  const readout = $derived.by(() => {
    if (cursor === null) return null
    const at = cursor
    const rows = series.flatMap((s) => {
      const i = nearestIndex(
        s.points.map((p) => p.t),
        at,
      )
      if (i < 0) return []
      const v = s.points[i].v
      return [{ s, t: s.points[i].t, text: v === null ? '−' : `${num(v, s.digits).replace('-', '−')}${s.unit ? ` ${s.unit}` : ''}` }]
    })
    if (rows.length === 0) return null
    const t = rows[0].t
    const frac = Math.min(1, Math.max(0, (t - x0) / (x1 - x0 || 1)))
    return { t, frac, rows }
  })

  function fromPointer(e: PointerEvent) {
    if (!svgEl) return
    const r = svgEl.getBoundingClientRect()
    if (r.width <= 0) return
    const frac = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width))
    cursor = x0 + frac * (x1 - x0)
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      cursor = null
      return
    }
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    const first = series.find((s) => s.points.some((p) => p.v !== null))
    if (!first) return
    const ts = first.points.filter((p) => p.v !== null).map((p) => p.t)
    const i = cursor === null ? ts.length - 1 : nearestIndex(ts, cursor)
    const step = cursor === null ? 0 : e.key === 'ArrowRight' ? 1 : -1
    cursor = ts[Math.min(ts.length - 1, Math.max(0, i + step))]
    e.preventDefault()
  }
</script>

<div class="lc">
  <div class="chart">
    <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
    <svg
      bind:this={svgEl}
      viewBox="0 0 {W} {height}"
      style:height="{height}px"
      role="img"
      aria-label={label}
      tabindex="0"
      preserveAspectRatio="none"
      onpointermove={fromPointer}
      onpointerdown={fromPointer}
      onpointerleave={() => (cursor = null)}
      onblur={() => (cursor = null)}
      onkeydown={onKey}
    >
      <rect x="0" y="0" width={W} height={height} class="bg" />
      {#if threshold}<line x1="0" x2={W} y1={thY} y2={thY} class="thr" />{/if}
      {#each drawn as g (g.s.key)}
        {#if g.d}<path d={g.d} class:dash={g.s.dash} style:stroke={COLORS[g.s.color]} />{/if}
        {#each g.dots as d, i (i)}<circle cx={d.x} cy={d.y} r="2.5" style:fill={COLORS[g.s.color]} />{/each}
      {/each}
      {#if readout}
        {@const x = readout.frac * W}
        <line x1={x} x2={x} y1="0" y2={height} class="cur" />
      {/if}
    </svg>
    <div class="axis left"><span>{axisText(leftR[1], 'left')}</span><span>{axisText(leftR[0], 'left')}</span></div>
    {#if hasRight}
      <div class="axis right"><span>{axisText(rightR[1], 'right')}</span><span>{axisText(rightR[0], 'right')}</span></div>
    {/if}
    {#if readout}
      <div class="tip" class:flip={readout.frac > 0.6} style:--f={readout.frac} role="status">
        <b>{chartTime(readout.t, spanHours)}</b>
        {#each readout.rows as r (r.s.key)}
          <span class="row"><i style:border-color={COLORS[r.s.color]} class:dash={r.s.dash}></i>{r.s.label}: {r.text}</span>
        {/each}
      </div>
    {/if}
  </div>
  <p class="legend">
    {#each series as s (s.key)}
      <span class="k"><i style:border-color={COLORS[s.color]} class:dash={s.dash}></i>{s.label}</span>
    {/each}
    {#if threshold}<span class="k"><i class="thr"></i>{threshold.label}</span>{/if}
  </p>
</div>

<style>
  .lc {
    margin-bottom: var(--space-2);
  }
  .chart {
    position: relative;
    --pad: 56px;
    padding: 0 var(--pad);
  }
  svg {
    width: 100%;
    display: block;
    border-radius: var(--radius-sm);
    touch-action: pan-y;
    cursor: crosshair;
  }
  svg:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .bg {
    fill: var(--surface-sunken);
  }
  path {
    fill: none;
    stroke-width: 2;
    vector-effect: non-scaling-stroke;
  }
  path.dash {
    stroke-dasharray: 6 3;
  }
  line.thr {
    stroke: var(--danger);
    stroke-width: 1;
    stroke-dasharray: 1 3;
    vector-effect: non-scaling-stroke;
  }
  line.cur {
    stroke: var(--ink-muted);
    stroke-width: 1;
    vector-effect: non-scaling-stroke;
  }
  .axis {
    position: absolute;
    top: 0;
    bottom: 0;
    width: 52px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    font: 400 12px/16px var(--font-mono);
    color: var(--ink-muted);
  }
  .axis.left {
    left: 0;
    text-align: right;
  }
  .axis.right {
    right: 0;
  }
  .tip {
    position: absolute;
    top: 4px;
    left: calc(var(--pad) + (100% - 2 * var(--pad)) * var(--f));
    transform: translateX(8px);
    pointer-events: none;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: var(--space-2);
    background: var(--surface-raised);
    border: 1px solid var(--line);
    border-radius: var(--radius-sm);
    box-shadow: var(--shadow-2);
    font-size: 13px;
    line-height: 18px;
    white-space: nowrap;
    z-index: 2;
  }
  .tip.flip {
    transform: translateX(calc(-100% - 8px));
  }
  .row,
  .k {
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  i {
    width: 18px;
    height: 0;
    border-top: 2px solid;
  }
  i.dash {
    border-top-style: dashed;
  }
  i.thr {
    border-color: var(--danger);
    border-top-style: dotted;
  }
  .legend {
    display: flex;
    gap: var(--space-3);
    flex-wrap: wrap;
    font-size: 12px;
    margin: var(--space-2) 0;
    color: var(--ink-muted);
  }
  :global(.vp-phone) .axis,
  :global(.vp-phone) .legend,
  :global(.vp-phone) .tip {
    font-size: 14px;
  }
  :global(.vp-phone) .chart {
    --pad: 48px;
  }
  :global(.vp-phone) .axis {
    width: 44px;
  }
</style>
