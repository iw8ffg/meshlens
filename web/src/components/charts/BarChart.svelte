<script lang="ts">
  import { barRects } from '../../lib/netstats'
  import { num } from '../../lib/format'

  type Color = 'radio' | 'mqtt' | 'accent'

  let {
    bars,
    series,
    label,
    height = 120,
  }: {
    bars: { label: string; values: number[] }[]
    series: { label: string; color: Color }[]
    label: string
    height?: number
  } = $props()

  const COLORS: Record<Color, string> = { accent: 'var(--accent)', radio: 'var(--src-radio)', mqtt: 'var(--src-mqtt)' }
  const W = 300
  const GAP = 2

  const max = $derived(Math.max(0, ...bars.flatMap((b) => b.values)))
  const n = $derived(series.length || 1)
  // Una colonna per gruppo; dentro, una barra per serie, tutte sulla stessa scala
  const groups = $derived(
    barRects(
      bars.map(() => 1),
      W,
      height,
      GAP * 2,
    ).map((slot, i) =>
      bars[i].values.map((v, k) => {
        const h = max > 0 ? (Math.max(0, v) / max) * height : 0
        return { x: slot.x + k * (slot.w / n), y: height - h, w: slot.w / n, h }
      }),
    ),
  )

  let active = $state<number | null>(null)
  let svgEl = $state<SVGSVGElement>()

  function fromPointer(e: PointerEvent) {
    if (!svgEl || bars.length === 0) return
    const r = svgEl.getBoundingClientRect()
    if (r.width <= 0) return
    const frac = Math.min(0.999, Math.max(0, (e.clientX - r.left) / r.width))
    active = Math.floor(frac * bars.length)
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      active = null
      return
    }
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return
    const step = e.key === 'ArrowRight' ? 1 : -1
    active = active === null ? (step > 0 ? 0 : bars.length - 1) : Math.min(bars.length - 1, Math.max(0, active + step))
    e.preventDefault()
  }

  const readout = $derived(active === null || !bars[active] ? null : { bar: bars[active], frac: (active + 0.5) / bars.length })
</script>

<div class="bc">
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
      onpointerleave={() => (active = null)}
      onblur={() => (active = null)}
      onkeydown={onKey}
    >
      <rect x="0" y="0" width={W} height={height} class="bg" />
      {#each groups as g, i (i)}
        {#each g as r, k (k)}
          {#if r.h > 0}<rect x={r.x} y={r.y} width={r.w} height={r.h} class:on={active === i} style:fill={COLORS[series[k]?.color ?? 'accent']} />{/if}
        {/each}
      {/each}
      {#if readout}
        <rect x={(active ?? 0) * (W / bars.length)} y="0" width={W / bars.length} height={height} class="cur" />
      {/if}
    </svg>
    <div class="axis"><span>{num(max, 0)}</span><span>0</span></div>
    {#if readout}
      <div class="tip" class:flip={readout.frac > 0.6} style:--f={readout.frac} role="status">
        <b>{readout.bar.label}</b>
        {#each readout.bar.values as v, k (k)}
          <span class="row">
            <i style:background={COLORS[series[k]?.color ?? 'accent']}></i>{series[k]?.label ?? ''}: {num(v, 0)}
          </span>
        {/each}
      </div>
    {/if}
  </div>
  {#if series.length > 1}
    <p class="legend">
      {#each series as s (s.label)}<span class="k"><i style:background={COLORS[s.color]}></i>{s.label}</span>{/each}
    </p>
  {/if}
</div>

<style>
  .bc {
    margin-bottom: var(--space-2);
  }
  .chart {
    position: relative;
    --pad: 40px;
    padding: 0 0 0 var(--pad);
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
  .cur {
    fill: var(--ink-muted);
    opacity: 0.18;
  }
  .axis {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    width: 36px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
    text-align: right;
    font: 400 12px/16px var(--font-mono);
    color: var(--ink-muted);
  }
  .tip {
    position: absolute;
    top: 4px;
    left: calc(var(--pad) + (100% - var(--pad)) * var(--f));
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
    width: 12px;
    height: 12px;
    border-radius: 2px;
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
    --pad: 44px;
  }
  :global(.vp-phone) .axis {
    width: 40px;
  }
</style>
