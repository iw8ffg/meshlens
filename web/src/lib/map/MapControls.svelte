<script lang="ts">
  // Controlli della mappa (zoom, adatta ai nodi): 44 px su telefono.
  import Icon from '../ui/Icon.svelte'

  interface Props {
    onzoomin: () => void
    onzoomout: () => void
    onfit: () => void
  }
  let { onzoomin, onzoomout, onfit }: Props = $props()
</script>

<div class="controls" role="group" aria-label="Controlli mappa">
  <button type="button" aria-label="Ingrandisci" title="Ingrandisci" onclick={onzoomin}><Icon name="plus" size={18} /></button>
  <button type="button" aria-label="Riduci" title="Riduci" onclick={onzoomout}><Icon name="minus" size={18} /></button>
  <button type="button" aria-label="Mostra tutti i nodi" title="Mostra tutti i nodi" onclick={onfit}><Icon name="globe" size={18} /></button>
</div>

<style>
  .controls {
    position: absolute;
    top: var(--space-3);
    right: var(--space-3);
    z-index: var(--z-map-ui);
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
  :global(.vp-phone) button {
    width: var(--touch-min);
    height: var(--touch-min);
  }
</style>
