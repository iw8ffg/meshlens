<script lang="ts">
  import { onMount } from 'svelte'
  import { networkStats } from '../lib/api'
  import { num } from '../lib/format'
  import { kindLabel, kindTotals, packetsPerHour, snrBinLabel } from '../lib/netstats'
  import type { NetworkStats } from '../lib/types'
  import { chartTime } from '../lib/chart'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Table, { type Column } from '../lib/ui/Table.svelte'
  import BarChart from './charts/BarChart.svelte'
  import LineChart from './charts/LineChart.svelte'

  let { onpick }: { onpick: (id: string) => void } = $props()

  const PERIODS = [
    { label: '24 h', hours: 24 },
    { label: '7 g', hours: 168 },
    { label: '30 g', hours: 720 },
  ]
  const REFRESH_MS = 60_000
  const TOP_COLS: Column[] = [
    { key: 'name', label: 'Nodo', fix: true },
    { key: 'packets', label: 'Pacchetti', num: true },
    { key: 'per_hour', label: "All'ora", num: true },
  ]

  let hours = $state(24)
  let data = $state<NetworkStats | null>(null)
  let loading = $state(false)
  let error = $state('')
  /** Incrementato da «Aggiorna» e dal timer: l'effetto ricarica. */
  let tick = $state(0)

  $effect(() => {
    const h = hours
    void tick
    loading = true
    error = ''
    let stale = false
    networkStats(h)
      .then((s) => {
        if (!stale) data = s
      })
      .catch(() => {
        if (!stale) error = 'Statistiche non disponibili'
      })
      .finally(() => {
        if (!stale) loading = false
      })
    return () => {
      stale = true
    }
  })

  onMount(() => {
    const id = setInterval(() => tick++, REFRESH_MS)
    return () => clearInterval(id)
  })

  const perHour = $derived(data ? packetsPerHour(data.packets) : [])
  const kinds = $derived(data ? kindTotals(data.packets) : [])
  const onlineSeries = $derived(
    data
      ? [{ key: 'online', label: 'Nodi online', unit: '', digits: 0, color: 'accent' as const, points: data.online.map((p) => ({ t: p.time, v: p.nodes })) }]
      : [],
  )
  const onlineMax = $derived(Math.max(1, ...(data?.online.map((p) => p.nodes) ?? [1])))
  const maxHardware = $derived(Math.max(1, ...(data?.hardware.map((h) => h.nodes) ?? [1])))
  const maxRole = $derived(Math.max(1, ...(data?.roles.map((r) => r.nodes) ?? [1])))
  const pct = (share: number) => `${num(share * 100, 0)}%`
</script>

<div class="stats">
  <div class="bar">
    <div class="periods" role="group" aria-label="Periodo">
      {#each PERIODS as p (p.hours)}
        <button type="button" class="ui-chip" aria-pressed={hours === p.hours} onclick={() => (hours = p.hours)}>{p.label}</button>
      {/each}
    </div>
    <Button icon="refresh" disabled={loading} onclick={() => tick++}>Aggiorna</Button>
  </div>
  <p class="ui-muted note">Le statistiche riguardano i nodi archiviati: nazioni salvate, nodi miei e preferiti, nodi sentiti via radio.</p>
  <p class="ui-muted note">I pacchetti all'ora comprendono tutto il traffico ricevuto.</p>

  {#if error}
    <Banner kind="danger" title={error} />
  {/if}

  {#if data && data.totals.packets === 0}
    <Empty icon="network" title="Ancora nessun dato" />
  {:else if data}
    <Card>
      <h3>Nodi online nel tempo</h3>
      {#if data.online.length === 0}
        <p class="ui-muted">Nessun dato nel periodo</p>
      {:else}
        <LineChart
          label="Grafico dei nodi online nel tempo"
          x0={data.since}
          x1={Math.max(data.since + 1, data.online[data.online.length - 1].time)}
          left={[0, onlineMax]}
          series={onlineSeries}
        />
      {/if}
    </Card>

    <Card>
      <h3>Pacchetti all'ora</h3>
      <BarChart
        label="Grafico dei pacchetti all'ora"
        bars={perHour.map((p) => ({ label: chartTime(p.time, data!.hours), values: [p.packets] }))}
        series={[{ label: 'Pacchetti', color: 'accent' }]}
      />
      <ul class="plain">
        {#each kinds as k (k.kind)}
          <li>{kindLabel(k.kind)}: {num(k.packets, 0)} ({pct(k.share)})</li>
        {/each}
      </ul>
    </Card>

    <Card>
      <h3>Distribuzione dell'SNR</h3>
      <BarChart
        label="Grafico della distribuzione dell'SNR"
        bars={data.snr.bins.map((lo, i) => ({ label: snrBinLabel(lo), values: [data!.snr.rf[i] ?? 0, data!.snr.mqtt[i] ?? 0] }))}
        series={[
          { label: 'Radio', color: 'radio' },
          { label: 'MQTT', color: 'mqtt' },
        ]}
      />
    </Card>

    <Card>
      <h3>Salti</h3>
      <BarChart
        label="Grafico dei nodi per numero di salti"
        bars={data.hops.map((h) => ({ label: h.hops === null ? 'sconosciuti' : String(h.hops), values: [h.nodes] }))}
        series={[{ label: 'Nodi', color: 'accent' }]}
      />
    </Card>

    <Card>
      <h3>Nodi più attivi</h3>
      <Table columns={TOP_COLS} rows={data.top} rowKey={(t) => t.id} onrowclick={(t) => onpick(t.id)} caption="Nodi più attivi">
        {#snippet cell(t, c)}
          {#if c.key === 'name'}
            <b>{t.name}</b>
          {:else if c.key === 'packets'}
            {num(t.packets, 0)}
          {:else}
            {num(t.per_hour, 1)}
          {/if}
        {/snippet}
      </Table>
    </Card>

    <Card>
      <h3>Modelli</h3>
      <ul class="hbars">
        {#each data.hardware as h (h.value)}
          <li><span class="lbl">{h.value}</span><span class="track"><span class="fill" style:width="{(h.nodes / maxHardware) * 100}%"></span></span><span class="n">{num(h.nodes, 0)}</span></li>
        {/each}
      </ul>
      {#if data.other_hardware > 0}<p class="ui-muted">Altri: {num(data.other_hardware, 0)}</p>{/if}
    </Card>

    <Card>
      <h3>Ruoli</h3>
      <ul class="hbars">
        {#each data.roles as r (r.value)}
          <li><span class="lbl">{r.value}</span><span class="track"><span class="fill" style:width="{(r.nodes / maxRole) * 100}%"></span></span><span class="n">{num(r.nodes, 0)}</span></li>
        {/each}
      </ul>
    </Card>
  {:else if loading}
    <p class="ui-muted">Caricamento…</p>
  {/if}
</div>

<style>
  .stats {
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
  .periods {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .note {
    margin: 0;
    font-size: 14px;
  }
  h3 {
    margin: 0 0 var(--space-2);
  }
  .plain {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-4);
    font-size: 14px;
  }
  .hbars {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .hbars li {
    display: grid;
    grid-template-columns: minmax(80px, 160px) 1fr auto;
    align-items: center;
    gap: var(--space-2);
    font-size: 14px;
  }
  .lbl {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .track {
    height: 10px;
    background: var(--surface-sunken);
    border-radius: var(--radius-sm);
    overflow: hidden;
  }
  .fill {
    display: block;
    height: 100%;
    background: var(--accent);
  }
  .n {
    font-family: var(--font-mono);
    text-align: right;
  }
  :global(.vp-phone) .stats :global(.ui-tblwrap) {
    overflow-x: auto;
  }
</style>
