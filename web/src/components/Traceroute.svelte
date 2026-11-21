<script lang="ts">
  import { ApiError, traceroute, traceroutes } from '../lib/api'
  import { formatDate } from '../lib/format'
  import { app, setTraceroute } from '../lib/stores.svelte'
  import type { Node, Traceroute, TracerouteHop } from '../lib/types'

  let { node }: { node: Node } = $props()

  const connected = $derived(app.radios.filter((r) => r.state === 'connected'))
  let radioId = $state('')
  let busy = $state(false)
  let error = $state('')
  let history = $state<Traceroute[]>([])

  const current = $derived(app.traceroutes.get(node.id) ?? null)

  // Una radio scelta che si scollega torna ad "automatica"
  $effect(() => {
    if (radioId && !connected.some((r) => r.id === radioId)) radioId = ''
  })

  // All'apertura del nodo: storico, e semina dello store col piu' recente
  // (un esito arrivato a WebSocket giu' non resta "pending")
  $effect(() => {
    const id = node.id
    error = ''
    history = []
    traceroutes(id)
      .then((list) => {
        if (id !== node.id) return
        history = list
        const latest = [...list].sort((a, b) => b.time - a.time || b.id - a.id)[0]
        const have = app.traceroutes.get(id)
        if (latest && (!have || latest.id >= have.id)) setTraceroute(latest)
      })
      .catch(() => {
        /* lo storico e' accessorio */
      })
  })

  async function run() {
    busy = true
    error = ''
    const id = node.id
    try {
      setTraceroute(await traceroute(id, radioId || undefined))
    } catch (e) {
      if (id === node.id) error = e instanceof ApiError ? e.message : 'Traceroute non riuscito'
    } finally {
      busy = false
    }
  }

  function name(id: string): string {
    const n = app.nodes.get(id)
    return n?.short_name || n?.long_name || id
  }

  function snr(v: number | null): string {
    if (v === null) return '? dB'
    return `${String(Math.round(v * 10) / 10).replace('.', ',').replace('-', '−')} dB`
  }

  /** `Base → Rip1 (6 dB) → Nodo (−1 dB)`: SNR con cui ogni salto e' stato ricevuto. */
  function path(hops: TracerouteHop[]): string {
    return hops.map((h, i) => (i === 0 ? name(h.id) : `${name(h.id)} (${snr(h.snr)})`)).join(' → ')
  }

  function failure(t: Traceroute): string {
    if (t.status === 'timeout') return 'Nessuna risposta entro 60 s'
    return t.error ? `Non riuscito: ${t.error}` : 'Non riuscito'
  }

  const pending = $derived(busy || current?.status === 'pending')
  const older = $derived(history.filter((h) => h.id !== current?.id))
</script>

<h3>Traceroute</h3>
<div class="row">
  <button class="tr" disabled={connected.length === 0 || pending} onclick={run}>Traceroute</button>
  {#if connected.length > 1}
    <select bind:value={radioId} aria-label="Radio per il traceroute">
      <option value="">automatica</option>
      {#each connected as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
    </select>
  {/if}
</div>
{#if connected.length === 0}<p class="none">Collega una radio</p>{/if}
{#if error}<p class="msg">{error}</p>{/if}
{#if pending}
  <p class="none">In corso… (max 60 s)</p>
{:else if current}
  {#if current.status === 'ok'}
    <p class="res"><b>Andata</b> {path(current.forward)}</p>
    <p class="res"><b>Ritorno</b> {path(current.back)}</p>
  {:else}
    <p class="msg">{failure(current)}</p>
  {/if}
{/if}
{#if older.length > 0}
  <ul class="hist">
    {#each older as t (t.id)}
      <li>
        <span class="when">{formatDate(t.time)}</span>
        {#if t.status === 'ok'}
          {path(t.forward)}
        {:else if t.status === 'pending'}
          In corso…
        {:else}
          {failure(t)}
        {/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  h3 {
    font-size: 14px;
    margin: 10px 0 4px;
  }
  .row {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .tr {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 6px 12px;
    cursor: pointer;
  }
  .tr:disabled {
    opacity: 0.5;
    cursor: default;
  }
  select {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 5px;
  }
  .none {
    margin: 4px 0;
    font-size: 13px;
    color: #9ca3af;
  }
  .msg {
    color: #fbbf24;
    font-size: 13px;
    margin: 4px 0;
  }
  .res {
    font-size: 13px;
    margin: 4px 0;
    word-break: break-word;
  }
  .hist {
    list-style: none;
    margin: 6px 0;
    padding: 0;
    font-size: 12px;
    color: #9ca3af;
  }
  .hist li {
    margin-bottom: 2px;
  }
  .when {
    margin-right: 6px;
  }
</style>
