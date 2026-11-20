<script lang="ts">
  import { app } from '../lib/stores.svelte'
  import { compareLastHeard, flag, timeAgo } from '../lib/format'
  import type { Node } from '../lib/types'

  let { nodes, now, onpick }: { nodes: Node[]; now: number; onpick: (n: Node) => void } = $props()
  const sorted = $derived([...nodes].sort((a, b) => compareLastHeard(a.last_heard, b.last_heard)))
</script>

<ul>
  {#each sorted as n (n.id)}
    <li>
      <button class:sel={app.selectedId === n.id} onclick={() => onpick(n)}>
        <span>{n.country ? flag(n.country) : '❔'}</span>
        <span class="name">{n.long_name || n.short_name || n.id}</span>
        <span class="dim">{timeAgo(n.last_heard, now)}</span>
        <span class="dim">{n.battery !== null ? `${n.battery}%` : ''}</span>
      </button>
    </li>
  {:else}
    <li class="empty">Nessun nodo con questi filtri</li>
  {/each}
</ul>

<style>
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  button {
    display: grid;
    grid-template-columns: 24px 1fr auto 44px;
    gap: 6px;
    width: 100%;
    text-align: left;
    background: none;
    color: inherit;
    border: 0;
    border-bottom: 1px solid #1f2937;
    padding: 8px;
    cursor: pointer;
    font: inherit;
  }
  button:hover,
  button.sel {
    background: #1f2937;
  }
  .name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .dim {
    color: #9ca3af;
    font-size: 12px;
    text-align: right;
  }
  .empty {
    padding: 16px;
    color: #9ca3af;
  }
</style>
