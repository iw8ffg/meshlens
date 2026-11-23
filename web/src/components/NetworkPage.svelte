<script lang="ts">
import { safeStorage } from '../lib/storage'
  import { loadView, saveView, type NetView } from '../lib/viewstate'
  import { t, type MsgKey } from '../lib/i18n/index.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import Network from './Network.svelte'
  import NetworkStats from './NetworkStats.svelte'
  import PacketInspector from './PacketInspector.svelte'
  import HealthView, { ready as healthReady } from './network/HealthView.svelte'
  import TopologyView, { ready as topologyReady } from './network/TopologyView.svelte'
  import type { Node } from '../lib/types'

  let { nodes, now, onpick }: { nodes: Node[]; now: number; onpick: (n: Node) => void } = $props()

  // health/topology compaiono solo quando il loro pacchetto di lavoro le dichiara pronte
  const VIEWS = $derived<{ value: NetView; label: string }[]>([
    { value: 'nodes', label: t('network.view.nodes') },
    { value: 'stats', label: t('network.view.stats') },
    { value: 'packets', label: t('network.view.packets') },
    ...(healthReady ? [{ value: 'health' as NetView, label: t('health.view' as MsgKey) }] : []),
    ...(topologyReady ? [{ value: 'topology' as NetView, label: t('topology.view' as MsgKey) }] : []),
  ])

  const available = (v: NetView): boolean =>
    (v !== 'health' || healthReady) && (v !== 'topology' || topologyReady)
  const saved = loadView(safeStorage()).netView
  // una vista salvata non disponibile ricade su nodes
  let view = $state<NetView>(available(saved) ? saved : 'nodes')

  const pickId = (id: string) => {
    const n = nodes.find((x) => x.id === id)
    if (n) onpick(n)
  }
</script>

<div class="page">
  <div class="views">
    <Segmented items={VIEWS} bind:value={view} label={t('network.viewAria')} onchange={(v) => saveView(safeStorage(), { netView: v })} />
  </div>
  {#if view === 'stats'}
    <NetworkStats onpick={pickId} />
  {:else if view === 'packets'}
    <PacketInspector {nodes} onpick={pickId} />
  {:else if view === 'health'}
    <HealthView />
  {:else if view === 'topology'}
    <TopologyView />
  {:else}
    <Network {nodes} {now} {onpick} />
  {/if}
</div>

<style>
  .views {
    padding: var(--space-3) var(--space-3) 0;
  }
</style>
