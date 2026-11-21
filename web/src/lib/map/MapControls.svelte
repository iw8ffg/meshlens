<script lang="ts">
  // Controlli della mappa: zoom e adatta ai nodi, poi gli strumenti (cerca, Dove sono, righello, raggruppa); 44 px su telefono.
  import Icon from '../ui/Icon.svelte'
  import { viewport } from '../viewport.svelte'

  interface Props {
    onzoomin: () => void
    onzoomout: () => void
    onfit: () => void
    ruler: boolean
    cluster: boolean
    onruler: () => void
    oncluster: () => void
    onsearch: () => void
    onlocate: () => void
    locating: boolean
  }
  let toolsOpen = $state(false) // su telefono gli strumenti stanno dietro un solo pulsante
  const showTools = $derived(!viewport.phone || toolsOpen)
  let { onzoomin, onzoomout, onfit, ruler, cluster, onruler, oncluster, onsearch, onlocate, locating }: Props = $props()
</script>

<div class="stack">
  <div class="controls" role="group" aria-label="Controlli mappa">
    <button type="button" aria-label="Ingrandisci" title="Ingrandisci" onclick={onzoomin}><Icon name="plus" size={18} /></button>
    <button type="button" aria-label="Riduci" title="Riduci" onclick={onzoomout}><Icon name="minus" size={18} /></button>
    <button type="button" aria-label="Mostra tutti i nodi" title="Mostra tutti i nodi" onclick={onfit}><Icon name="globe" size={18} /></button>
  </div>
  <div class="controls" role="group" aria-label="Strumenti mappa">
    {#if viewport.phone}
      <button type="button" class:on={toolsOpen} aria-expanded={toolsOpen} aria-label="Strumenti" title="Strumenti" onclick={() => (toolsOpen = !toolsOpen)}><Icon name="more" size={18} /></button>
    {/if}
    {#if showTools}
    <button type="button" aria-label="Cerca nodo" title="Cerca nodo" onclick={onsearch}><Icon name="search" size={18} /></button>
    <button type="button" aria-label="Dove sono" title="Dove sono" aria-busy={locating} disabled={locating} onclick={onlocate}><Icon name={locating ? 'spinner' : 'locate'} size={18} /></button>
    <button type="button" class:on={ruler} aria-pressed={ruler} aria-label="Righello" title="Righello" onclick={onruler}><Icon name="ruler" size={18} /></button>
    <button type="button" class:on={cluster} aria-pressed={cluster} aria-label="Raggruppa nodi" title="Raggruppa nodi" onclick={oncluster}><Icon name="cluster" size={18} /></button>
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
