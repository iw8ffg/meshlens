<script lang="ts">
  import { app } from '../lib/stores.svelte'
  import { ago, compareLastHeard } from '../lib/format'
  import { hopsLabel, batteryView, contactMinutes, nodeName, sourceKind } from '../lib/nodes'
  import { contactClass } from '../lib/ui/logic'
  import BatteryBadge from '../lib/ui/BatteryBadge.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import Icon from '../lib/ui/Icon.svelte'
  import Flag from '../lib/ui/Flag.svelte'
  import SnrBadge from '../lib/ui/SnrBadge.svelte'
  import SourceMark from '../lib/ui/SourceMark.svelte'
  import type { Node } from '../lib/types'

  let { nodes, now, onpick }: { nodes: Node[]; now: number; onpick: (n: Node) => void } = $props()
  const sorted = $derived([...nodes].sort((a, b) => compareLastHeard(a.last_heard, b.last_heard)))
</script>

{#if sorted.length === 0}
  <Empty icon="search" title="Nessun nodo con questi filtri">Allarga l'ultimo contatto o togli qualche nazione.</Empty>
{:else}
  <ul class="nl">
    {#each sorted as n (n.id)}
      {@const mins = contactMinutes(n.last_heard, now)}
      {@const src = sourceKind(n)}
      {@const bat = batteryView(n.battery)}
      <li>
        <button type="button" class:sel={app.selectedId === n.id} onclick={() => onpick(n)}>
          <Flag code={n.country} />
          <span class="id">
            <span class="name">{nodeName(n)}{#if n.is_mine || n.is_local_radio}<span class="mk house" title="Mio nodo"><Icon name="house" size={14} /></span>{/if}{#if n.is_favorite}<span class="mk fav" title="Preferito"><Icon name="star" size={14} /></span>{/if}</span>
            <span class="sub ui-mono">{n.id}</span>
          </span>
          {#if src}<SourceMark source={src} />{/if}
          <span class="vals">
            <span class="age {mins === null ? 'old' : contactClass(mins)}"><i aria-hidden="true"></i>{ago(mins)}</span>
            <span class="meas">
              {#if n.last_snr !== null}<SnrBadge value={n.last_snr} />{/if}
              {#if bat}<BatteryBadge pct={bat.pct} usb={bat.usb} />{/if}
              <span class="hops" title="Salti">{hopsLabel(n.hops, n.hops_min)}</span>
            </span>
          </span>
        </button>
      </li>
    {/each}
  </ul>
{/if}

<style>
  .nl {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  button {
    display: grid;
    grid-template-columns: auto 1fr auto auto;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    min-height: 56px;
    text-align: left;
    background: none;
    color: var(--ink);
    border: 0;
    border-bottom: 1px solid var(--line);
    padding: var(--space-2) var(--space-3);
    cursor: pointer;
    font: 400 14px/20px var(--font-sans);
  }
  button:hover {
    background: var(--accent-soft);
  }
  button.sel {
    background: var(--accent-soft);
    box-shadow: inset 3px 0 0 var(--accent);
  }
  .id {
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .name {
    font-weight: 600;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .mk {
    display: inline-flex;
    vertical-align: -2px;
    margin-left: var(--space-1);
  }
  .mk.house {
    color: var(--accent);
  }
  .mk.fav {
    color: var(--brand-amber);
  }
  .hops {
    color: var(--ink-muted);
  }
  .sub {
    color: var(--ink-muted);
    font-size: 12px;
  }
  .vals {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 2px;
    font-size: 12px;
  }
  .meas {
    display: flex;
    gap: var(--space-2);
    font-size: 12px;
  }
  .age {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    color: var(--ink-muted);
  }
  .age i {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: var(--contact-old);
  }
  .age.fresh i {
    background: var(--contact-fresh);
  }
  .age.recent i {
    background: var(--contact-recent);
  }
  :global(.vp-phone) button {
    min-height: 64px;
  }
  :global(.vp-phone) .sub,
  :global(.vp-phone) .vals,
  :global(.vp-phone) .meas {
    font-size: 14px;
  }
</style>
