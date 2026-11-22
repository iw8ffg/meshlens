<script lang="ts">
  import { locale } from '../lib/i18n/index.svelte'
  import { packet as fetchPacket } from '../lib/api'
  import { copyText } from '../lib/clipboard'
  import { kindLabel } from '../lib/netstats'
  import { hexDump, hopsText, relayCandidates, STATUS_LABEL } from '../lib/packets'
  import type { Node, PacketDetail } from '../lib/types'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import SourceMark from '../lib/ui/SourceMark.svelte'

  let {
    id,
    nodes,
    onpick,
    onclose,
    wide = false,
  }: { id: number; nodes: Node[]; onpick: (id: string) => void; onclose: () => void; wide?: boolean } = $props()

  const BROADCAST = '!ffffffff'

  let data = $state<PacketDetail | null>(null)
  let error = $state('')
  let copied = $state(false)
  let copyTimer: ReturnType<typeof setTimeout> | undefined

  $effect(() => () => clearTimeout(copyTimer))

  $effect(() => {
    const pid = id
    data = null
    error = ''
    let stale = false
    fetchPacket(pid)
      .then((d) => {
        if (!stale) data = d
      })
      .catch(() => {
        if (!stale) error = 'Pacchetto non disponibile'
      })
    return () => {
      stale = true
    }
  })

  const names = $derived(new Map(nodes.map((n) => [n.id, n.long_name ?? n.short_name ?? n.id])))
  const label = (nid: string) => (nid === BROADCAST ? 'Tutti' : (names.get(nid) ?? nid))
  const dump = $derived(data ? hexDump(data.raw_hex) : [])
  const relayHex = (r: number) => r.toString(16).padStart(2, '0')
  const relays = $derived(data ? relayCandidates(data.relay_node, nodes) : [])
  const summaryText = $derived(data?.summary ? JSON.stringify(data.summary, null, 2) : '')
  const when = (t: number) => new Date(t * 1000).toLocaleString(locale())
  const num1 = (v: number | null) => (v === null ? '–' : String(v).replace('-', '−'))

  async function copyHex() {
    if (!data) return
    copied = await copyText(data.raw_hex)
    if (copied) {
      clearTimeout(copyTimer)
      copyTimer = setTimeout(() => (copied = false), 2000)
    }
  }
</script>

<Card>
  <div class="head">
    {#if !wide}<Button icon="chevL" onclick={onclose}>Indietro</Button>{/if}
    {#if data}
      <h3>{kindLabel(data.kind)}</h3>
      <span class="ui-muted">{STATUS_LABEL[data.status] ?? data.status} · {when(data.time)}</span>
    {/if}
    {#if wide}<Button icon="x" onclick={onclose}>Chiudi</Button>{/if}
  </div>

  {#if error}
    <Banner kind="danger" title={error} />
  {:else if !data}
    <p class="ui-muted">Caricamento…</p>
  {:else}
    <dl>
      <dt>Da</dt>
      <dd><button type="button" class="lnk" onclick={() => onpick(data!.from)}>{data.from_name ?? label(data.from)}</button> <span class="ui-mono ui-muted">{data.from}</span></dd>
      <dt>A</dt>
      <dd>
        {#if data.to === BROADCAST}Tutti{:else}<button type="button" class="lnk" onclick={() => onpick(data!.to)}>{label(data.to)}</button> <span class="ui-mono ui-muted">{data.to}</span>{/if}
      </dd>
      <dt>Id del pacchetto</dt>
      <dd class="ui-mono">{data.packet_id ?? '–'}</dd>
      <dt>Canale</dt>
      <dd>{data.channel ?? '–'}</dd>
      <dt>Portnum</dt>
      <dd class="ui-mono">{data.portnum ?? '–'}</dd>
      <dt>Fonte</dt>
      <dd><SourceMark source={data.source === 'rf' ? 'radio' : 'mqtt'} size={16} /> {data.source === 'rf' ? (data.radio_id ?? 'Radio') : (data.broker ?? 'MQTT')}</dd>
      <dt>SNR</dt>
      <dd class="ui-mono">{num1(data.snr)}</dd>
      <dt>RSSI</dt>
      <dd class="ui-mono">{num1(data.rssi)}</dd>
      <dt>Salti</dt>
      <dd>{hopsText(data)}</dd>
      <dt>Ritrasmettitore</dt>
      <dd>
        {#if data.relay_node === null || data.relay_node === 0}–{:else}
          <span class="ui-mono">…{relayHex(data.relay_node)}</span>
          {#each relays as n (n.id)} <button type="button" class="lnk" onclick={() => onpick(n.id)}>{n.long_name ?? n.short_name ?? n.id}</button>{/each}
        {/if}
      </dd>
      <dt>Gateway</dt>
      <dd class="ui-mono">{data.gateway ?? '–'}</dd>
      <dt>Copie</dt>
      <dd>{data.copies}</dd>
    </dl>

    <h4>Ricezioni</h4>
    {#if data.receptions.length === 0}
      <p class="ui-muted">–</p>
    {:else}
      <ul class="rec">
        {#each data.receptions as r, i (i)}
          <li>
            <SourceMark source={r.source === 'rf' ? 'radio' : 'mqtt'} size={16} />
            <span>{r.source === 'rf' ? (r.radio_id ?? 'Radio') : (r.broker ?? 'MQTT')}</span>
            <span class="ui-mono">{when(r.time)}</span>
            <span class="ui-mono">SNR {num1(r.snr)}</span>
            <span class="ui-mono">RSSI {num1(r.rssi)}</span>
            <span>{hopsText({ hops: r.hops, hop_start: null, hop_limit: null })}</span>
          </li>
        {/each}
      </ul>
    {/if}

    <h4>Contenuto</h4>
    {#if summaryText}<pre class="ui-mono sum">{summaryText}</pre>{:else}<p class="ui-muted">–</p>{/if}

    <h4>Dati grezzi</h4>
    {#if dump.length === 0}
      <p class="ui-muted">–</p>
    {:else}
      <div class="dump ui-mono" role="table" aria-label="Dati grezzi">
        {#each dump as row (row.offset)}
          <div class="ln" role="row"><span class="off">{row.offset}</span><span class="hx">{row.hex}</span><span class="as">{row.ascii}</span></div>
        {/each}
      </div>
      <Button icon="copy" onclick={copyHex}>{copied ? 'Copiato' : 'Copia esadecimale'}</Button>
    {/if}
  {/if}
</Card>

<style>
  .head {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-3);
    margin-bottom: var(--space-3);
  }
  .head h3 {
    margin: 0;
  }
  dl {
    display: grid;
    grid-template-columns: max-content 1fr;
    gap: var(--space-1) var(--space-4);
    margin: 0 0 var(--space-3);
    font-size: 14px;
  }
  dt {
    color: var(--ink-muted);
  }
  dd {
    margin: 0;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  h4 {
    margin: var(--space-3) 0 var(--space-2);
  }
  .lnk {
    background: none;
    border: 0;
    padding: 0;
    min-height: 24px;
    color: var(--accent-ink);
    font: inherit;
    text-decoration: underline;
    cursor: pointer;
  }
  .lnk:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .rec {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    font-size: 14px;
  }
  .rec li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-3);
  }
  .sum {
    margin: 0;
    padding: var(--space-2);
    background: var(--surface-sunken);
    border-radius: var(--radius-sm);
    font-size: 13px;
    max-height: 280px;
    overflow: auto;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .dump {
    background: var(--surface-sunken);
    border-radius: var(--radius-sm);
    padding: var(--space-2);
    margin-bottom: var(--space-2);
    overflow-x: auto;
    font-size: 13px;
    line-height: 20px;
  }
  .ln {
    display: grid;
    grid-template-columns: 4ch minmax(0, max-content) 16ch;
    gap: var(--space-3);
    white-space: pre;
  }
  .hx {
    min-width: 47ch;
  }
  .off {
    color: var(--ink-muted);
  }
  :global(.vp-phone) .lnk {
    min-height: 44px;
  }
  :global(.vp-phone) .sum,
  :global(.vp-phone) .dump {
    font-size: 14px;
  }
</style>
