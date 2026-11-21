<script lang="ts">
  import { app } from '../lib/stores.svelte'
  import { timeAgo } from '../lib/format'
  import { batteryLabel, sortNodes, type SortKey } from '../lib/network'
  import type { Node } from '../lib/types'

  let { nodes, now, onpick }: { nodes: Node[]; now: number; onpick: (n: Node) => void } = $props()

  const COLS: [SortKey, string][] = [
    ['name', 'Nome'],
    ['last_heard', 'Ultimo'],
    ['role', 'Ruolo'],
    ['firmware', 'Firmware'],
    ['battery', 'Batt.'],
    ['voltage', 'Volt'],
    ['snr', 'SNR'],
    ['hops', 'Salti'],
    ['channel_util', 'Can. %'],
    ['air_util_tx', 'Tx %'],
  ]

  const hasMine = $derived(nodes.some((n) => n.is_mine))
  // Scelta dell'utente; finche' non tocca l'interruttore vale "acceso se esiste un nodo mio"
  let mineChoice = $state<boolean | null>(null)
  const onlyMine = $derived(mineChoice ?? hasMine)
  let key = $state<SortKey>('last_heard')
  let dir = $state<'asc' | 'desc'>('desc')

  const rows = $derived(sortNodes(onlyMine ? nodes.filter((n) => n.is_mine) : nodes, key, dir))

  function sortBy(k: SortKey) {
    if (k === key) dir = dir === 'asc' ? 'desc' : 'asc'
    else {
      key = k
      dir = k === 'name' || k === 'role' || k === 'firmware' ? 'asc' : 'desc'
    }
  }

  const num = (v: number | null, d = 1) => (v === null ? '—' : v.toFixed(d).replace('.', ','))
  const cell = (n: Node, k: SortKey): string => {
    switch (k) {
      case 'name':
        return n.long_name || n.short_name || n.id
      case 'last_heard':
        return timeAgo(n.last_heard, now)
      case 'role':
        return n.role ?? '—'
      case 'firmware':
        return n.firmware ?? '—'
      case 'battery':
        return batteryLabel(n.battery)
      case 'voltage':
        return n.voltage === null ? '—' : `${num(n.voltage, 2)} V`
      case 'snr':
        return n.last_snr === null ? '—' : `${num(n.last_snr)} dB`
      case 'hops':
        return n.hops === null ? '—' : String(n.hops)
      case 'channel_util':
        return num(n.channel_util)
      case 'air_util_tx':
        return num(n.air_util_tx)
    }
  }
</script>

<div class="bar">
  <label class="inline">
    <input type="checkbox" checked={onlyMine} onchange={(e) => (mineChoice = e.currentTarget.checked)} />
    Solo i miei nodi
  </label>
</div>
{#if onlyMine && !hasMine}
  <p class="empty">Nessun nodo segnato come tuo: aprilo e premi ☆</p>
{:else}
  <div class="scroll">
    <table>
      <thead>
        <tr>
          {#each COLS as [k, label] (k)}
            <th aria-sort={key === k ? (dir === 'asc' ? 'ascending' : 'descending') : 'none'}>
              <button onclick={() => sortBy(k)}>{label}{key === k ? (dir === 'asc' ? ' ▲' : ' ▼') : ''}</button>
            </th>
          {/each}
        </tr>
      </thead>
      <tbody>
        {#each rows as n (n.id)}
          <tr class:sel={app.selectedId === n.id} onclick={() => onpick(n)}>
            {#each COLS as [k] (k)}
              <td class:first={k === 'name'}>{cell(n, k)}</td>
            {/each}
          </tr>
        {:else}
          <tr><td class="empty" colspan={COLS.length}>Nessun nodo</td></tr>
        {/each}
      </tbody>
    </table>
  </div>
{/if}

<style>
  .bar {
    padding: 8px;
    border-bottom: 1px solid #1f2937;
    font-size: 13px;
  }
  .inline {
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .scroll {
    overflow-x: auto;
  }
  table {
    border-collapse: separate;
    border-spacing: 0;
    width: 100%;
    font-size: 12px;
    white-space: nowrap;
  }
  th,
  td {
    padding: 6px 8px;
    text-align: left;
    border-bottom: 1px solid #1f2937;
    background: #111827;
  }
  th button {
    background: none;
    border: 0;
    color: #9ca3af;
    font: inherit;
    cursor: pointer;
    padding: 0;
  }
  tbody tr {
    cursor: pointer;
  }
  tbody tr:hover td,
  tr.sel td {
    background: #1f2937;
  }
  /* Prima colonna ferma nello scorrimento orizzontale */
  th:first-child,
  td.first {
    position: sticky;
    left: 0;
    z-index: 1;
    max-width: 140px;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .empty {
    padding: 16px;
    color: #9ca3af;
    margin: 0;
  }
  @media (max-width: 767px) {
    table {
      font-size: 13px;
    }
    th button {
      min-height: 40px;
      padding: 0 4px;
    }
    .inline {
      min-height: 40px;
    }
  }
</style>
