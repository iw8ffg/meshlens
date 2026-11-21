<script lang="ts">
  import { app } from '../lib/stores.svelte'
  import { ago } from '../lib/format'
  import { sortNodes, type SortKey } from '../lib/network'
  import { alertText, alertsByNode, batteryView, contactMinutes, fmtOpt, nodeName } from '../lib/nodes'
  import Banner from '../lib/ui/Banner.svelte'
  import BatteryBadge from '../lib/ui/BatteryBadge.svelte'
  import Badge from '../lib/ui/Badge.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import SnrBadge from '../lib/ui/SnrBadge.svelte'
  import Switch from '../lib/ui/Switch.svelte'
  import Table, { type Column } from '../lib/ui/Table.svelte'
  import type { Node } from '../lib/types'

  let { nodes, now, onpick }: { nodes: Node[]; now: number; onpick: (n: Node) => void } = $props()

  const COLS: (Column & { key: SortKey })[] = [
    { key: 'name', label: 'Nodo', fix: true, sortable: true },
    { key: 'last_heard', label: 'Ultimo', sortable: true },
    { key: 'role', label: 'Ruolo', sortable: true },
    { key: 'firmware', label: 'Firmware', sortable: true },
    { key: 'battery', label: 'Batteria', sortable: true },
    { key: 'voltage', label: 'Volt', num: true, sortable: true },
    { key: 'snr', label: 'SNR', sortable: true },
    { key: 'hops', label: 'Salti', num: true, sortable: true },
    { key: 'channel_util', label: 'Can. %', num: true, sortable: true },
    { key: 'air_util_tx', label: 'Tx %', num: true, sortable: true },
  ]

  const hasMine = $derived(nodes.some((n) => n.is_mine))
  // Scelta dell'utente; finche' non tocca l'interruttore vale "acceso se esiste un nodo mio"
  let mineChoice = $state<boolean | null>(null)
  const onlyMine = $derived(mineChoice ?? hasMine)
  let key = $state<SortKey>('last_heard')
  let dir = $state<'asc' | 'desc'>('desc')

  const rows = $derived(sortNodes(onlyMine ? nodes.filter((n) => n.is_mine) : nodes, key, dir))
  const alerts = $derived(alertsByNode(app.alerts))
  const alertRows = $derived(rows.filter((n) => alerts.has(n.id)))

  function sortBy(k: string) {
    const sk = k as SortKey
    if (sk === key) dir = dir === 'asc' ? 'desc' : 'asc'
    else {
      key = sk
      dir = sk === 'name' || sk === 'role' || sk === 'firmware' ? 'asc' : 'desc'
    }
  }
</script>

<div class="net">
  <div class="bar">
    <Switch checked={onlyMine} label="Solo i miei nodi" onchange={(v) => (mineChoice = v)} />
    <span class="ui-muted">{rows.length} {rows.length === 1 ? 'nodo' : 'nodi'}</span>
  </div>

  {#if alertRows.length > 0}
    <div class="alerts">
      {#each alertRows as n (n.id)}
        {#each alerts.get(n.id) ?? [] as a (a.key)}
          <Banner kind="warn" title={nodeName(n)}>{alertText(a)}</Banner>
        {/each}
      {/each}
    </div>
  {/if}

  {#if onlyMine && !hasMine}
    <Empty icon="star" title="Nessun nodo seguito">Apri un nodo e premi la stella per seguirlo qui.</Empty>
  {:else if rows.length === 0}
    <Empty icon="network" title="Nessun nodo" />
  {:else}
    <Table columns={COLS} {rows} rowKey={(n) => n.id} sortKey={key} sortDir={dir} onsort={sortBy} selectedKey={app.selectedId} onrowclick={onpick} caption="Nodi della rete">
      {#snippet cell(n, c)}
        {#if c.key === 'name'}
          <b>{nodeName(n)}</b>
        {:else if c.key === 'last_heard'}
          {ago(contactMinutes(n.last_heard, now))}
        {:else if c.key === 'role'}
          {#if n.role}<Badge>{n.role}</Badge>{:else}–{/if}
        {:else if c.key === 'firmware'}
          {n.firmware ?? '–'}
        {:else if c.key === 'battery'}
          {@const b = batteryView(n.battery)}
          {#if b}<BatteryBadge pct={b.pct} usb={b.usb} />{:else}–{/if}
        {:else if c.key === 'voltage'}
          {fmtOpt(n.voltage, 2)}
        {:else if c.key === 'snr'}
          <SnrBadge value={n.last_snr} />
        {:else if c.key === 'hops'}
          {n.hops ?? '–'}
        {:else if c.key === 'channel_util'}
          {fmtOpt(n.channel_util)}
        {:else if c.key === 'air_util_tx'}
          {fmtOpt(n.air_util_tx)}
        {/if}
      {/snippet}
    </Table>
  {/if}
</div>

<style>
  .net {
    padding: var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .bar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-3);
    flex-wrap: wrap;
  }
  .alerts {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
</style>
