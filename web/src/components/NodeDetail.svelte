<script lang="ts">
  import { getJSON, setMine } from '../lib/api'
  import { flag, formatDate, timeAgo } from '../lib/format'
  import { app, upsertNodes } from '../lib/stores.svelte'
  import TelemetryChart from './TelemetryChart.svelte'
  import Traceroute from './Traceroute.svelte'
  import { formatPrecision } from '../lib/geo'
  import type { Node } from '../lib/types'

  type Pos = { time: number; lat: number; lon: number; precision_bits: number | null; source: string }
  let {
    node,
    now,
    ontrack,
    onclose,
    onchat,
  }: {
    node: Node
    now: number
    ontrack: (pts: [number, number][] | null) => void
    onclose: () => void
    onchat: () => void
  } = $props()

  const heard = $derived(
    Object.entries(node.heard_by ?? {})
      .map(([rid, h]) => ({ ...h, rid, name: app.radios.find((r) => r.id === rid)?.name ?? 'Radio rimossa' }))
      .sort((a, b) => b.time - a.time),
  )
  const showMqtt = $derived(node.mqtt_gateways > 0 || node.sources.includes('mqtt'))
  const firstRadio = $derived(app.radios.find((r) => r.state === 'connected') ?? null)

  function directMessage() {
    if (!firstRadio) return
    app.chatConv = `dm:${firstRadio.id}:${node.id}`
    onchat()
  }

  let mineBusy = $state(false)
  async function toggleMine() {
    mineBusy = true
    msg = ''
    try {
      upsertNodes([await setMine(node.id, !node.is_mine)])
    } catch {
      msg = 'Impossibile aggiornare "Mio nodo"'
    } finally {
      mineBusy = false
    }
  }

  let loading = $state(false)
  let msg = $state('')
  let shown = $state(false)

  // Cambiando nodo il percorso precedente non e' piu' pertinente
  const nodeId = $derived(node.id)
  $effect(() => {
    void nodeId
    shown = false
    msg = ''
    ontrack(null)
  })

  async function toggleTrack() {
    if (shown) {
      shown = false
      ontrack(null)
      return
    }
    loading = true
    msg = ''
    const id = node.id
    try {
      const pos = await getJSON<Pos[]>(`/nodes/${encodeURIComponent(id)}/positions?hours=24`)
      if (id !== node.id) return
      if (pos.length < 2) msg = 'Nessun percorso nelle ultime 24 h'
      else {
        ontrack([...pos].sort((a, b) => a.time - b.time).map((p) => [p.lon, p.lat]))
        shown = true
      }
    } catch {
      msg = 'Percorso non disponibile'
    } finally {
      loading = false
    }
  }

  const fmt = (v: number | null, unit = '', d = 1) => (v === null ? '–' : `${v.toFixed(d).replace('.', ',')}${unit}`)
  const precision = $derived(formatPrecision(node.precision_bits))
  const rows = $derived<[string, string][]>([
    ['Id', node.id],
    ['Nome breve', node.short_name ?? '–'],
    ['Modello', node.hw_model ?? '–'],
    ['Ruolo', node.role ?? '–'],
    ['Firmware', node.firmware ?? '–'],
    ['Nazione', node.country ? `${flag(node.country)} ${node.country}` : 'Sconosciuta'],
    ['Posizione', node.lat !== null && node.lon !== null ? `${node.lat.toFixed(5)}, ${node.lon.toFixed(5)}` : '–'],
    ['Precisione posizione', precision ?? (node.precision_bits === null ? '–' : 'esatta')],
    ['Fonte posizione', node.position_source ?? '–'],
    ['Ultimo contatto', formatDate(node.last_heard)],
    ['Batteria', node.battery === null ? '–' : `${node.battery}%`],
    ['Tensione', fmt(node.voltage, ' V', 2)],
    ['Uso canale', fmt(node.channel_util, '%')],
    ['Uso aria TX', fmt(node.air_util_tx, '%')],
    ['Gateway MQTT', String(node.mqtt_gateways)],
    ['SNR', fmt(node.last_snr, ' dB')],
    ['Salti', node.hops === null ? '–' : String(node.hops)],
    ['Sorgenti', node.sources.join(', ') || '–'],
  ])
</script>

<section>
  <header>
    <h2>{node.long_name || node.short_name || node.id}</h2>
    <button class="star" disabled={mineBusy} title="Mio nodo" aria-label="Mio nodo" aria-pressed={!!node.is_mine} onclick={toggleMine}>
      {node.is_mine ? '★' : '☆'}
    </button>
    <button class="x" aria-label="Chiudi dettaglio" onclick={onclose}>✕</button>
  </header>
  <dl>
    {#each rows as [k, v] (k)}
      <dt>{k}</dt>
      <dd>{v}</dd>
    {/each}
  </dl>
  <h3>Sentito da</h3>
  {#if heard.length === 0 && !showMqtt}
    <p class="none">Nessuna radio</p>
  {:else}
    <ul class="heard">
      {#each heard as h (h.rid)}
        <li>
          <b>{h.name}</b>
          SNR {h.snr === null ? '–' : `${h.snr.toFixed(1).replace('.', ',')} dB`} · RSSI {h.rssi === null ? '–' : `${h.rssi} dBm`} ·
          salti {h.hops ?? '–'} · {timeAgo(h.time, now)}
        </li>
      {/each}
      {#if showMqtt}<li><b>MQTT</b> {node.mqtt_gateways} gateway</li>{/if}
    </ul>
  {/if}
  {#if !node.is_local_radio}
    <button class="dm" disabled={!firstRadio} title={firstRadio ? '' : 'Nessuna radio connessa'} onclick={directMessage}>
      Messaggio diretto
    </button>
  {/if}
  {#if node.lat !== null}
    <button class="track" disabled={loading} onclick={toggleTrack}>
      {shown ? 'Nascondi percorso' : loading ? 'Caricamento…' : 'Mostra percorso'}
    </button>
  {/if}
  {#if msg}<p class="msg">{msg}</p>{/if}
  <TelemetryChart nodeId={node.id} />
  <Traceroute {node} />
</section>

<style>
  section {
    padding: 8px 12px;
  }
  header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  h2 {
    font-size: 17px;
    margin: 4px 0;
    flex: 1;
  }
  .star {
    background: none;
    border: 0;
    color: #fbbf24;
    font-size: 20px;
    cursor: pointer;
  }
  .x {
    background: none;
    border: 0;
    color: inherit;
    font-size: 18px;
    cursor: pointer;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 3px 12px;
    margin: 8px 0;
    font-size: 14px;
  }
  dt {
    color: #9ca3af;
  }
  dd {
    margin: 0;
    word-break: break-all;
  }
  .track {
    background: #2563eb;
    color: #fff;
    border: 0;
    border-radius: 6px;
    padding: 6px 12px;
    cursor: pointer;
  }
  h3 {
    font-size: 14px;
    margin: 10px 0 4px;
  }
  .heard {
    list-style: none;
    margin: 0 0 8px;
    padding: 0;
    font-size: 13px;
  }
  .none {
    margin: 0 0 8px;
    font-size: 13px;
    color: #9ca3af;
  }
  .dm {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 6px 12px;
    cursor: pointer;
    margin-right: 6px;
  }
  .dm:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .msg {
    color: #fbbf24;
    font-size: 13px;
  }
</style>
