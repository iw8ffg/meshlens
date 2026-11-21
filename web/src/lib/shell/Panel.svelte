<script lang="ts">
  import type { Snippet } from 'svelte'
  import { PANEL_MAX, PANEL_MIN, clampPanelWidth, loadPanelWidth, savePanelWidth } from './nav'

  let { children }: { children: Snippet } = $props()

  let width = $state(loadPanelWidth(typeof localStorage === 'undefined' ? null : localStorage))
  let startX = 0
  let startW = 0
  let dragging = $state(false)

  const store = () => (typeof localStorage === 'undefined' ? null : localStorage)

  function down(e: PointerEvent) {
    startX = e.clientX
    startW = width
    dragging = true
    ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  }
  function move(e: PointerEvent) {
    if (dragging) width = clampPanelWidth(startW + e.clientX - startX)
  }
  function up() {
    if (!dragging) return
    dragging = false
    savePanelWidth(store(), width)
  }
  function key(e: KeyboardEvent) {
    const d = e.key === 'ArrowRight' ? 16 : e.key === 'ArrowLeft' ? -16 : 0
    if (!d) return
    e.preventDefault()
    width = clampPanelWidth(width + d)
    savePanelWidth(store(), width)
  }
</script>

<aside class="panel" style="width: {width}px">
  <div class="content">{@render children()}</div>
  <!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
  <div
    class="grip"
    class:on={dragging}
    role="separator"
    aria-orientation="vertical"
    aria-label="Ridimensiona il pannello"
    aria-valuemin={PANEL_MIN}
    aria-valuemax={PANEL_MAX}
    aria-valuenow={width}
    tabindex="0"
    onpointerdown={down}
    onpointermove={move}
    onpointerup={up}
    onpointercancel={up}
    onkeydown={key}
  ></div>
</aside>

<style>
  .panel { position: relative; flex: none; display: flex; flex-direction: column; min-width: 0; background: var(--surface); border-right: 1px solid var(--line-strong); z-index: var(--z-panel); }
  .content { flex: 1; min-height: 0; overflow: auto; }
  .grip { position: absolute; top: 0; bottom: 0; right: -6px; width: 12px; cursor: col-resize; touch-action: none; z-index: 1; }
  .grip::after { content: ''; position: absolute; top: 50%; left: 4px; width: 4px; height: 40px; margin-top: -20px; border-radius: 2px; background: var(--line-strong); }
  .grip:hover::after, .grip.on::after { background: var(--accent); }
</style>
