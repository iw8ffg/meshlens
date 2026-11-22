<script lang="ts">
  // Controlli della mappa: zoom e adatta ai nodi, poi gli strumenti (cerca, Dove sono, righello, raggruppa); 44 px su telefono.
  import Icon from '../ui/Icon.svelte'
  import { viewport } from '../viewport.svelte'
  import { t } from '../i18n/index.svelte'

  interface Props {
    onzoomin: () => void
    onzoomout: () => void
    onfit: () => void
    ruler: boolean
    cluster: boolean
    waypoints: boolean
    onwaypoints: () => void
    onruler: () => void
    oncluster: () => void
    onsearch: () => void
    onlocate: () => void
    locating: boolean
  }
  let toolsOpen = $state(false) // su telefono gli strumenti stanno dietro un solo pulsante
  const showTools = $derived(!viewport.phone || toolsOpen)
  let { onzoomin, onzoomout, onfit, ruler, cluster, waypoints, onwaypoints, onruler, oncluster, onsearch, onlocate, locating }: Props = $props()
</script>

<div class="stack">
  <div class="controls" role="group" aria-label={t('map.controls.group')}>
    <button type="button" aria-label={t('map.controls.zoomIn')} title={t('map.controls.zoomIn')} onclick={onzoomin}><Icon name="plus" size={18} /></button>
    <button type="button" aria-label={t('map.controls.zoomOut')} title={t('map.controls.zoomOut')} onclick={onzoomout}><Icon name="minus" size={18} /></button>
    <button type="button" aria-label={t('map.controls.fit')} title={t('map.controls.fit')} onclick={onfit}><Icon name="globe" size={18} /></button>
  </div>
  <div class="controls" role="group" aria-label={t('map.controls.tools')}>
    {#if viewport.phone}
      <button type="button" class:on={toolsOpen} aria-expanded={toolsOpen} aria-label={t('map.controls.toolsShort')} title={t('map.controls.toolsShort')} onclick={() => (toolsOpen = !toolsOpen)}><Icon name="more" size={18} /></button>
    {/if}
    {#if showTools}
    <button type="button" aria-label={t('map.controls.search')} title={t('map.controls.search')} onclick={onsearch}><Icon name="search" size={18} /></button>
    <button type="button" aria-label={t('map.controls.locate')} title={t('map.controls.locate')} aria-busy={locating} disabled={locating} onclick={onlocate}><Icon name={locating ? 'spinner' : 'locate'} size={18} /></button>
    <button type="button" class:on={ruler} aria-pressed={ruler} aria-label={t('map.controls.ruler')} title={t('map.controls.ruler')} onclick={onruler}><Icon name="ruler" size={18} /></button>
    <button type="button" class:on={cluster} aria-pressed={cluster} aria-label={t('map.controls.cluster')} title={t('map.controls.cluster')} onclick={oncluster}><Icon name="cluster" size={18} /></button>
    <button type="button" class:on={waypoints} aria-pressed={waypoints} aria-label={t('waypoints.layerToggleAria')} title={t('waypoints.layerToggleAria')} onclick={onwaypoints}><Icon name="flag" size={18} /></button>
    {/if}
  </div>
</div>

<style>
  .stack {
    position: absolute;
    top: var(--space-3);
    right: var(--space-3);
    z-index: var(--z-map-ui);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .controls {
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    box-shadow: var(--shadow-2);
    overflow: hidden;
  }
  button {
    display: grid;
    place-items: center;
    width: var(--control-h-desktop);
    height: var(--control-h-desktop);
    border: 0;
    border-bottom: 1px solid var(--line);
    background: none;
    color: var(--ink);
    cursor: pointer;
  }
  button:last-child {
    border-bottom: 0;
  }
  button:hover {
    background: var(--surface-sunken);
  }
  button.on {
    background: var(--accent-soft);
    color: var(--accent-ink);
  }
  :global(.vp-phone) button {
    width: var(--touch-min);
    height: var(--touch-min);
  }
</style>
