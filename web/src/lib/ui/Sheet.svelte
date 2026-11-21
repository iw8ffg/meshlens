<script lang="ts">
  import type { Snippet } from 'svelte'
  import Button from './Button.svelte'
  import { SHEET_SNAPS, clampSnap, fractionFromDrag, nearestSnap, stepSnap, type SheetSnap } from './sheetSnap'

  interface Props {
    /** Fermo corrente: 0 chiuso, 1 = 40%, 2 = 78%. */
    snap?: SheetSnap
    label?: string
    children: Snippet
  }
  let { snap = $bindable(1), label = 'Pannello', children }: Props = $props()

  let el: HTMLElement | undefined = $state()
  let dragFraction = $state<number | null>(null)
  let startY = 0
  let startFraction = 0
  let height = 0

  const fraction = $derived(dragFraction ?? SHEET_SNAPS[clampSnap(snap)])
  const closed = $derived(dragFraction === null && snap === 0)

  function down(e: PointerEvent) {
    const parent = el?.offsetParent as HTMLElement | null
    height = parent?.clientHeight ?? window.innerHeight
    startY = e.clientY
    startFraction = SHEET_SNAPS[clampSnap(snap)]
    dragFraction = startFraction
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }
  function move(e: PointerEvent) {
    if (dragFraction === null) return
    dragFraction = fractionFromDrag(startFraction, e.clientY - startY, height)
  }
  function up() {
    if (dragFraction === null) return
    snap = nearestSnap(dragFraction)
    dragFraction = null
  }
  function key(e: KeyboardEvent) {
    if (e.key === 'ArrowUp') snap = stepSnap(snap, 1)
    else if (e.key === 'ArrowDown') snap = stepSnap(snap, -1)
    else return
    e.preventDefault()
  }
</script>

<section bind:this={el} class="ui-sheet" class:dragging={dragFraction !== null} aria-label={label} style="height: {closed ? 'auto' : `${fraction * 100}%`}">
  <div class="hd">
    <button
      type="button"
      class="gr"
      aria-label="Trascina per ridimensionare il pannello"
      onpointerdown={down}
      onpointermove={move}
      onpointerup={up}
      onpointercancel={up}
      onkeydown={key}
    ><i></i></button>
    <Button kind="ghost" iconOnly icon="chevU" label="Espandi il pannello" disabled={snap === 2} onclick={() => (snap = stepSnap(snap, 1))} />
    <Button kind="ghost" iconOnly icon="chevD" label={snap === 1 ? 'Chiudi il pannello' : 'Riduci il pannello'} disabled={snap === 0} onclick={() => (snap = stepSnap(snap, -1))} />
  </div>
  {#if !closed}<div class="body">{@render children()}</div>{/if}
</section>
