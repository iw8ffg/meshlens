<script lang="ts">
  import { loadView, saveView, type NetView } from '../lib/viewstate'
  import Segmented from '../lib/ui/Segmented.svelte'
  import Network from './Network.svelte'
  import NetworkStats from './NetworkStats.svelte'
  import type { Node } from '../lib/types'

  let { nodes, now, onpick }: { nodes: Node[]; now: number; onpick: (n: Node) => void } = $props()

  const VIEWS: { value: NetView; label: string }[] = [
    { value: 'nodes', label: 'Nodi' },
    { value: 'stats', label: 'Statistiche' },
  ]

  const saved = loadView(localStorage).netView
  // La voce «Pacchetti» arriva con l'ispettore: finché manca, vale «Nodi»
  let view = $state<NetView>(saved === 'stats' ? 'stats' : 'nodes')

  const pickId = (id: string) => {
    const n = nodes.find((x) => x.id === id)
    if (n) onpick(n)
  }
</script>

<div class="page">
  <div class="views">
    <Segmented items={VIEWS} bind:value={view} label="Vista della rete" onchange={(v) => saveView(localStorage, { netView: v })} />
  </div>
  {#if view === 'stats'}
    <NetworkStats onpick={pickId} />
  {:else}
    <Network {nodes} {now} {onpick} />
  {/if}
</div>

<style>
  .views {
    padding: var(--space-3) var(--space-3) 0;
  }
</style>
