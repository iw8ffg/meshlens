<script lang="ts">
  import { onDestroy } from 'svelte'
  import { getJSON, setFavorite, setMine } from '../lib/api'
  import { formatDate, ago, num } from '../lib/format'
  import { downloadText } from '../lib/download'
  import { fileStamp, gpx, slug } from '../lib/export'
  import { batteryView, contactMinutes, fmtOpt, hopsLabel, nodeName, sourceKind } from '../lib/nodes'
  import Badge from '../lib/ui/Badge.svelte'
  import BatteryBadge from '../lib/ui/BatteryBadge.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Flag from '../lib/ui/Flag.svelte'
  import SnrBadge from '../lib/ui/SnrBadge.svelte'
  import SourceMark from '../lib/ui/SourceMark.svelte'
  import { app, upsertNodes, openChat, openConfig } from '../lib/stores.svelte'
  import NodeCharts from './NodeCharts.svelte'
  import Traceroute from './Traceroute.svelte'
  import { formatPrecision } from '../lib/geo'
  import { copyText } from '../lib/clipboard'
  import { nodeLink } from '../lib/route'
  import { keyChangedRecently } from '../lib/reactions'
  import { T } from '../lib/strings/messaggi'
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
    openChat(`dm:${firstRadio.id}:${node.id}`)
    onchat()
  }

  let favBusy = $state(false)
  async function toggleFavorite() {
    favBusy = true
    msg = ''
    try {
      upsertNodes([await setFavorite(node.id, !node.is_favorite)])
    } catch {
      msg = 'Impossibile aggiornare "Preferito"'
    } finally {
      favBusy = false
    }
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

  // «Copia link»: link diretto al nodo, conferma «Link copiato» per 2 s
  let linkCopied = $state(false)
  let copiedTimer: ReturnType<typeof setTimeout> | undefined
  async function copyLink() {
    msg = ''
    if (await copyText(nodeLink(node.id, location))) {
      linkCopied = true
      clearTimeout(copiedTimer)
      copiedTimer = setTimeout(() => (linkCopied = false), 2000)
    } else {
      msg = 'Impossibile copiare il link'
    }
  }
  onDestroy(() => clearTimeout(copiedTimer))

  let loading = $state(false)
  let msg = $state('')
  let shown = $state(false)

  // Cambiando nodo il percorso precedente non e' piu' pertinente
  const nodeId = $derived(node.id)
  $effect(() => {
    void nodeId
    trackSeq++
    shown = false
    loading = false
    trackPts = []
    msg = ''
    linkCopied = false
    ontrack(null)
  })

  const TRACK_ERROR = 'Percorso non disponibile'

  const TRACK_PERIODS = [
    { hours: 24, label: '24 h' },
    { hours: 168, label: '7 g' },
    { hours: 720, label: '30 g' },
    { hours: 2160, label: '90 g' },
  ]
  let trackHours = $state(24)
  let trackPts = $state<Pos[]>([])
  const NO_TRACK = 'Nessun percorso nel periodo scelto'
  let trackSeq = 0 // scarta le risposte di richieste superate da un cambio di nodo o di periodo

  async function loadTrack() {
    const seq = ++trackSeq
    loading = true
    msg = ''
    const id = node.id
    try {
      const pos = await getJSON<Pos[]>(`/nodes/${encodeURIComponent(id)}/positions?hours=${trackHours}&max_points=5000`)
      if (seq !== trackSeq || id !== node.id) return
      const sorted = [...pos].sort((a, b) => a.time - b.time)
      trackPts = sorted
      if (sorted.length < 2) {
        msg = NO_TRACK
        ontrack(null)
      } else ontrack(sorted.map((p) => [p.lon, p.lat]))
      shown = true
    } catch {
      if (seq !== trackSeq) return
      msg = TRACK_ERROR
      ontrack(null)
    } finally {
      if (seq === trackSeq) loading = false
    }
  }

  async function toggleTrack() {
    if (shown) {
      trackSeq++
      shown = false
      loading = false
      msg = ''
      trackPts = []
      ontrack(null)
      return
    }
    await loadTrack()
  }

  function pickPeriod(h: number) {
    if (h === trackHours) return
    trackHours = h
    void loadTrack()
  }

  function exportGpx() {
    const name = node.short_name || node.id
    downloadText(`meshlens-percorso-${slug(name)}-${fileStamp(new Date())}.gpx`, 'application/gpx+xml', gpx(nodeName(node), trackPts))
  }

  const trackRange = $derived(
    trackPts.length >= 2
      ? `${trackPts.length} posizioni dal ${formatDate(trackPts[0].time)} al ${formatDate(trackPts[trackPts.length - 1].time)}`
      : '',
  )

  const precision = $derived(formatPrecision(node.precision_bits))
  const src = $derived(sourceKind(node))
  const bat = $derived(batteryView(node.battery))
  const rows = $derived<[string, string][]>([
    ['Id', node.id],
    ['Nome breve', node.short_name ?? '–'],
    ['Modello', node.hw_model ?? '–'],
    ['Firmware', node.firmware ?? '–'],
    ['Posizione', node.lat !== null && node.lon !== null ? `${num(node.lat, 5)}, ${num(node.lon, 5)}` : '–'],
    ['Precisione posizione', precision ?? (node.precision_bits === null ? '–' : 'esatta')],
    ['Fonte posizione', node.position_source ?? '–'],
    ['Ultimo contatto', formatDate(node.last_heard)],
    ['Tensione', fmtOpt(node.voltage, 2, ' V')],
    ['Uso canale', fmtOpt(node.channel_util, 1, '%')],
    ['Uso aria TX', fmtOpt(node.air_util_tx, 1, '%')],
    ['Gateway MQTT', String(node.mqtt_gateways)],
    [T.publicKeyLabel, node.public_key ? T.publicKeyPresent : T.publicKeyAbsent],
    ['Salti', hopsLabel(node.hops, node.hops_min)],
  ])
</script>

<section class="nd">
  <header>
    <Flag code={node.country} name={node.country ?? undefined} />
    <h2>{nodeName(node)}</h2>
    <Button kind="ghost" iconOnly icon="x" label="Chiudi dettaglio" onclick={onclose} />
  </header>

  <div class="state">
    {#if node.role}<Badge>{node.role}</Badge>{/if}
    {#if src}<SourceMark source={src} />{/if}
    <SnrBadge value={node.last_snr} />
    {#if bat}<BatteryBadge pct={bat.pct} usb={bat.usb} />{/if}
    <span class="ui-muted">{ago(contactMinutes(node.last_heard, now))}</span>
  </div>

  <div class="flags">
    <Button icon="star" aria-pressed={!!node.is_favorite} disabled={favBusy} onclick={toggleFavorite} class={node.is_favorite ? 'fav on' : 'fav'}>Preferito</Button>
    <Button icon="house" aria-pressed={!!node.is_mine} disabled={mineBusy} onclick={toggleMine} class={node.is_mine ? 'mine on' : 'mine'}>Mio nodo</Button>
  </div>

  <div class="acts">
    {#if !node.is_local_radio}
      <Button icon="chat" disabled={!firstRadio} title={firstRadio ? '' : 'Collega una radio'} onclick={directMessage}>Messaggio diretto</Button>
    {/if}
    <Button icon="settings" disabled={!firstRadio} title={firstRadio ? '' : 'Collega una radio'} onclick={() => openConfig(node.id)}>Configura</Button>
    {#if node.lat !== null}
      <Button icon="route" disabled={loading} onclick={toggleTrack}>{shown ? 'Nascondi percorso' : loading ? 'Caricamento…' : 'Mostra percorso'}</Button>
    {/if}
    <Button icon="copy" onclick={copyLink}>{linkCopied ? 'Link copiato' : 'Copia link'}</Button>
  </div>
  {#if shown}
    <div class="periods" role="group" aria-label="Periodo del percorso">
      {#each TRACK_PERIODS as p (p.hours)}
        <button type="button" class="ui-chip" aria-pressed={trackHours === p.hours} disabled={loading} onclick={() => pickPeriod(p.hours)}>{p.label}</button>
      {/each}
    </div>
    {#if trackRange}
      <p class="hint">{trackRange}</p>
      <div class="gap"><Button icon="download" onclick={exportGpx}>Esporta GPX</Button></div>
    {/if}
  {/if}
  {#if !firstRadio}<p class="hint">Collega una radio per i messaggi diretti e per configurare il nodo.</p>{/if}
  {#if msg}
    <div class="gap">
      <Banner kind="warn" title={msg}>
        {#snippet action()}
          {#if msg === TRACK_ERROR}<Button onclick={loadTrack}>Riprova</Button>{/if}
        {/snippet}
      </Banner>
    </div>
  {/if}

  {#if keyChangedRecently(node, now)}
    <div class="gap">
      <Banner kind="warn" title={T.keyChangedBanner(nodeName(node), formatDate(node.key_changed ?? null))} />
    </div>
  {/if}

  <dl>
    {#each rows as [k, v] (k)}
      <dt>{k}</dt>
      <dd>{v}</dd>
    {/each}
  </dl>

  <h3>Sentito da</h3>
  {#if heard.length === 0 && !showMqtt}
    <p class="ui-muted none">Nessuna radio</p>
  {:else}
    <ul class="heard">
      {#each heard as h (h.rid)}
        <li>
          <SourceMark source="radio" size={18} />
          <b>{h.name}</b>
          <SnrBadge value={h.snr} />
          <span class="ui-mono">RSSI {h.rssi === null ? '–' : `${h.rssi} dBm`}</span>
          <span>salti {hopsLabel(h.hops)}</span>
          <span class="ui-muted">{ago(contactMinutes(h.time, now))}</span>
        </li>
      {/each}
      {#if showMqtt}<li><SourceMark source="mqtt" size={18} /><b>MQTT</b> <span>{node.mqtt_gateways} gateway</span></li>{/if}
    </ul>
  {/if}

  <NodeCharts nodeId={node.id} />
  <Traceroute {node} />
</section>

<style>
  .nd {
    padding: var(--space-3) var(--space-4);
    color: var(--ink);
  }
  header {
    display: flex;
    align-items: center;
    gap: var(--space-2);
  }
  h2 {
    font: 600 18px/24px var(--font-sans);
    margin: var(--space-1) 0;
    flex: 1;
    min-width: 0;
    overflow-wrap: anywhere;
  }
  .flags {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
    margin: var(--space-2) 0;
  }
  .flags :global(.ui-btn.fav.on) {
    color: var(--brand-amber);
    border-color: var(--brand-amber);
  }
  .flags :global(.ui-btn.mine.on) {
    color: var(--accent-ink);
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .state {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    flex-wrap: wrap;
    margin: var(--space-2) 0 var(--space-3);
  }
  .acts {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .gap {
    margin-top: var(--space-2);
  }
  .periods {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
    margin-top: var(--space-2);
  }
  :global(.vp-phone) .periods :global(.ui-chip) {
    min-height: 44px;
  }
  .hint {
    margin: var(--space-2) 0 0;
    color: var(--ink-muted);
    font-size: 13px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: var(--space-1) var(--space-4);
    margin: var(--space-4) 0;
    font-size: 14px;
  }
  dt {
    color: var(--ink-muted);
  }
  dd {
    margin: 0;
    word-break: break-all;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
  }
  h3 {
    font: 600 14px/20px var(--font-sans);
    margin: var(--space-4) 0 var(--space-2);
  }
  .heard {
    list-style: none;
    margin: 0 0 var(--space-2);
    padding: 0;
    font-size: 13px;
  }
  .heard li {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-3);
    min-height: 36px;
    border-bottom: 1px solid var(--line);
  }
  .none {
    margin: 0 0 var(--space-2);
    font-size: 13px;
  }
  :global(.vp-phone) dl,
  :global(.vp-phone) .heard,
  :global(.vp-phone) .hint,
  :global(.vp-phone) .none {
    font-size: 14px;
  }
</style>
