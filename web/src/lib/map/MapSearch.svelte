<script lang="ts">
  // Ricerca di un nodo sulla mappa: trova anche i nodi nascosti dai filtri.
  import { onMount } from 'svelte'
  import { app } from '../stores.svelte'
  import { matchNode } from '../filters'
  import { nodeName } from '../nodes'
  import { searchNodes } from './search'
  import Icon from '../ui/Icon.svelte'

  interface Props {
    onpick: (id: string) => void
    onclose: () => void
  }
  let { onpick, onclose }: Props = $props()

  let q = $state('')
  let active = $state(0)
  let input: HTMLInputElement
  let root: HTMLDivElement
  let now = $state(Math.floor(Date.now() / 1000))
  const results = $derived(searchNodes(app.nodes.values(), q))

  onMount(() => {
    input.focus()
    const t = setInterval(() => (now = Math.floor(Date.now() / 1000)), 30_000)
    return () => clearInterval(t)
  })

  // Focus altrove con la ricerca vuota: si chiude (i controlli mappa gestiscono da soli il proprio pulsante)
  function onfocusout(e: FocusEvent) {
    const next = e.relatedTarget as HTMLElement | null
    if (q.trim() || root.contains(next) || next?.closest('.stack')) return
    onclose()
  }

  $effect(() => {
    void q
    active = 0
  })

  function onkey(e: KeyboardEvent) {
    if (e.key === 'Escape') {
      e.preventDefault()
      onclose()
    } else if (e.key === 'ArrowDown' && results.length) {
      e.preventDefault()
      active = (active + 1) % results.length
    } else if (e.key === 'ArrowUp' && results.length) {
      e.preventDefault()
      active = (active - 1 + results.length) % results.length
    } else if (e.key === 'Enter' && results[active]) {
      e.preventDefault()
      onpick(results[active].id)
    }
  }
</script>

<div class="search" bind:this={root} onfocusout={onfocusout}>
  <div class="top">
  <input
    bind:this={input}
    bind:value={q}
    type="search"
    placeholder="Cerca un nodo sulla mappa…"
    aria-label="Cerca un nodo sulla mappa"
    aria-controls="map-search-list"
    aria-activedescendant={results[active] ? `map-search-${active}` : undefined}
    autocomplete="off"
    onkeydown={onkey}
  />
  <button type="button" class="close" aria-label="Chiudi ricerca" title="Chiudi ricerca" onclick={onclose}><Icon name="x" size={18} /></button>
  </div>
  {#if q.trim()}
    {#if results.length}
      <ul id="map-search-list" role="listbox" aria-label="Risultati">
        {#each results as n, i (n.id)}
          <li role="presentation">
            <button type="button" id="map-search-{i}" role="option" aria-selected={i === active} class:act={i === active} tabindex="-1" onclick={() => onpick(n.id)}>
              <span class="name">{nodeName(n)}</span>
              <span class="id">{n.id}</span>
              {#if !matchNode(n, app.filter, now)}<span class="hid" title="Nascosto dai filtri"><Icon name="filter" size={16} /></span>{/if}
            </button>
          </li>
        {/each}
      </ul>
    {:else}
      <p class="none" role="status">Nessun nodo con posizione trovato</p>
    {/if}
  {/if}
</div>

<style>
  .search {
    pointer-events: auto;
    width: 280px;
    max-width: 100%;
    padding: var(--space-2);
    border-radius: var(--radius-lg);
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-2);
    font-size: 14px;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  :global(.vp-phone) .search {
    /* lascia libera la colonna dei controlli mappa a destra */
    width: calc(100vw - var(--space-3) * 2 - var(--touch-min) - var(--space-2));
  }
  .top {
    display: flex;
    gap: var(--space-2);
    align-items: center;
  }
  .top input {
    flex: 1;
    min-width: 0;
  }
  button.close {
    flex: none;
    width: var(--control-h-desktop);
    min-height: var(--control-h-desktop);
    justify-content: center;
    padding: 0;
  }
  :global(.vp-phone) button.close {
    width: var(--touch-min);
    min-height: var(--touch-min);
  }
  input {
    box-sizing: border-box;
    height: var(--control-h-desktop);
    padding: 0 var(--space-3);
    border: 1px solid var(--line);
    border-radius: var(--radius-md);
    background: var(--surface-sunken);
    color: var(--ink);
    font: inherit;
  }
  :global(.vp-phone) input {
    height: var(--touch-min);
  }
  ul {
    margin: 0;
    padding: 0;
    list-style: none;
    display: flex;
    flex-direction: column;
  }
  button {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    width: 100%;
    min-height: var(--control-h-desktop);
    padding: var(--space-1) var(--space-2);
    border: 0;
    border-radius: var(--radius-md);
    background: none;
    color: var(--ink);
    font: inherit;
    text-align: left;
    cursor: pointer;
  }
  :global(.vp-phone) button {
    min-height: var(--touch-min);
  }
  button:hover,
  button.act {
    background: var(--accent-soft);
    color: var(--accent-ink);
  }
  .name {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .id {
    color: var(--ink-muted);
    font-size: 13px;
  }
  :global(.vp-phone) .id {
    font-size: 14px;
  }
  .hid {
    display: inline-flex;
    color: var(--ink-muted);
  }
  .none {
    margin: 0;
    padding: var(--space-2);
    color: var(--ink-muted);
  }
</style>
