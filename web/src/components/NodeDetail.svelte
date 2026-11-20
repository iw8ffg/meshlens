<script lang="ts">
  import { getJSON } from '../lib/api'
  import { flag } from '../lib/format'
  import { formatPrecision } from '../lib/geo'
  import type { Node } from '../lib/types'

  type Pos = { time: number; lat: number; lon: number; precision_bits: number | null; source: string }
  let {
    node,
    ontrack,
    onclose,
  }: { node: Node; ontrack: (pts: [number, number][] | null) => void; onclose: () => void } = $props()

  let loading = $state(false)
  let msg = $state('')
  let shown = $state(false)

  // Cambiando nodo il percorso precedente non e' piu' pertinente
  $effect(() => {
    void node.id
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
  const date = (t: number) => new Date(t * 1000).toLocaleString('it-IT')
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
    ['Ultimo contatto', date(node.last_heard)],
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
    <button class="x" aria-label="Chiudi dettaglio" onclick={onclose}>✕</button>
  </header>
  <dl>
    {#each rows as [k, v] (k)}
      <dt>{k}</dt>
      <dd>{v}</dd>
    {/each}
  </dl>
  {#if node.lat !== null}
    <button class="track" disabled={loading} onclick={toggleTrack}>
      {shown ? 'Nascondi percorso' : loading ? 'Caricamento…' : 'Mostra percorso'}
    </button>
  {/if}
  {#if msg}<p class="msg">{msg}</p>{/if}
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
  .msg {
    color: #fbbf24;
    font-size: 13px;
  }
</style>
