<script lang="ts">
  import { onDestroy } from 'svelte'
  import { getJSON, setFavorite, setMine } from '../lib/api'
  import { formatDate, ago, num, countryName } from '../lib/format'
  import { downloadText } from '../lib/download'
  import { fileStamp, gpx, slug } from '../lib/export'
  import { batteryView, contactMinutes, fmtOpt, hopsLabel, nodeName, setRadioFlags, sourceKind } from '../lib/nodes'
  import type { AppSettings } from '../lib/settings'
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
  import NodeFlags from './node/NodeFlags.svelte'
  import PrivacyBanner from './PrivacyBanner.svelte'
  import SensorSection from './node/SensorSection.svelte'
  import TraceSchedule from './node/TraceSchedule.svelte'
  import TakInfo from './node/TakInfo.svelte'
  import { formatPrecision } from '../lib/geo'
  import { copyText } from '../lib/clipboard'
  import { nodeLink } from '../lib/route'
  import { keyChangedRecently } from '../lib/reactions'
  import { t, type MsgKey } from '../lib/i18n/index.svelte'
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
      .map(([rid, h]) => ({ ...h, rid, name: app.radios.find((r) => r.id === rid)?.name ?? t('nodes.detail.radioRemoved') }))
      .sort((a, b) => b.time - a.time),
  )
  const showMqtt = $derived(node.mqtt_gateways > 0 || node.sources.includes('mqtt'))
  const firstRadio = $derived(app.radios.find((r) => r.state === 'connected') ?? null)
  // WP4: avviso privacy solo per il nodo di una propria radio collegata
  const localRadio = $derived(app.radios.find((r) => r.state === 'connected' && r.my_node_id === node.id) ?? null)

  function directMessage() {
    if (!firstRadio) return
    openChat(`dm:${firstRadio.id}:${node.id}`)
    onchat()
  }

  let favBusy = $state(false)
  async function toggleFavorite() {
    favBusy = true
    msg = ''
    const value = !node.is_favorite
    try {
      upsertNodes([await setFavorite(node.id, value)])
    } catch {
      msg = 'nodes.detail.favoriteFailed'
      favBusy = false
      return
    }
    try {
      await copyFavoriteToRadios(value)
    } finally {
      favBusy = false
    }
  }

  // WP4: con «favorites_to_radio» la stella va anche nel NodeDB delle radio collegate;
  // un errore radio e' solo un avviso (la stella in MeshLens resta)
  async function copyFavoriteToRadios(value: boolean) {
    const ownRadio = !!node.is_local_radio || app.radios.some((r) => r.my_node_id === node.id)
    if (!firstRadio || ownRadio) return
    try {
      const s = await getJSON<AppSettings>('/settings')
      if (!s.favorites_to_radio) return
      const res = await setRadioFlags(node.id, { favorite: value })
      if (res.radios.some((r) => !r.ok)) msg = 'nodeflags.radioFailed'
    } catch {
      msg = 'nodeflags.radioFailed'
    }
  }

  let mineBusy = $state(false)
  async function toggleMine() {
    mineBusy = true
    msg = ''
    try {
      upsertNodes([await setMine(node.id, !node.is_mine)])
    } catch {
      msg = 'nodes.detail.mineFailed'
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
      msg = 'nodes.detail.copyFailed'
    }
  }
  onDestroy(() => clearTimeout(copiedTimer))

  let loading = $state(false)
  let msg = $state<MsgKey | ''>('')
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

  const TRACK_ERROR: MsgKey = 'nodes.detail.trackError'

  const TRACK_PERIODS: { hours: number; labelKey: MsgKey }[] = [
    { hours: 24, labelKey: 'nodes.age24h' },
    { hours: 168, labelKey: 'nodes.age7d' },
    { hours: 720, labelKey: 'nodes.period30d' },
    { hours: 2160, labelKey: 'nodes.period90d' },
  ]
  let trackHours = $state(24)
  let trackPts = $state<Pos[]>([])
  const NO_TRACK: MsgKey = 'nodes.detail.noTrack'
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
    downloadText(`${t('nodes.detail.gpxFile')}-${slug(name)}-${fileStamp(new Date())}.gpx`, 'application/gpx+xml', gpx(nodeName(node), trackPts))
  }

  const trackRange = $derived(
    trackPts.length >= 2
      ? t('nodes.detail.trackRange', { n: trackPts.length, from: formatDate(trackPts[0].time), to: formatDate(trackPts[trackPts.length - 1].time) })
      : '',
  )

  const precision = $derived(formatPrecision(node.precision_bits))
  const src = $derived(sourceKind(node))
  const bat = $derived(batteryView(node.battery))
  const rows = $derived<[string, string][]>([
    [t('nodes.row.id'), node.id],
    [t('nodes.row.shortName'), node.short_name ?? '–'],
    [t('nodes.row.model'), node.hw_model ?? '–'],
    [t('nodes.row.firmware'), node.firmware ?? '–'],
    [t('nodes.row.position'), node.lat !== null && node.lon !== null ? `${num(node.lat, 5)}, ${num(node.lon, 5)}` : '–'],
    [t('nodes.row.precision'), precision ?? (node.precision_bits === null ? '–' : t('nodes.row.exact'))],
    [t('nodes.row.positionSource'), node.position_source ?? '–'],
    [t('nodes.lastContact'), formatDate(node.last_heard)],
    [t('nodes.row.voltage'), fmtOpt(node.voltage, 2, ' V')],
    [t('nodes.row.channelUtil'), fmtOpt(node.channel_util, 1, '%')],
    [t('nodes.row.airUtilTx'), fmtOpt(node.air_util_tx, 1, '%')],
    [t('nodes.row.mqttGateways'), String(node.mqtt_gateways)],
    [t('chat.publicKeyLabel'), node.public_key ? t('chat.publicKeyPresent') : t('chat.publicKeyAbsent')],
    [t('nodes.hops'), hopsLabel(node.hops, node.hops_min)],
  ])
</script>

<section class="nd">
  <header>
    <Flag code={node.country} name={node.country ? countryName(node.country) : undefined} />
    <h2>{nodeName(node)}</h2>
    <Button kind="ghost" iconOnly icon="x" label={t('nodes.detail.close')} onclick={onclose} />
  </header>

  <div class="state">
    {#if node.role}<Badge>{node.role}</Badge>{/if}
    {#if src}<SourceMark source={src} />{/if}
    <SnrBadge value={node.last_snr} />
    {#if bat}<BatteryBadge pct={bat.pct} usb={bat.usb} />{/if}
    <span class="ui-muted">{ago(contactMinutes(node.last_heard, now))}</span>
  </div>

  <div class="flags">
    <Button icon="star" aria-pressed={!!node.is_favorite} disabled={favBusy} onclick={toggleFavorite} class={node.is_favorite ? 'fav on' : 'fav'}>{t('nodes.favorite')}</Button>
    <Button icon="house" aria-pressed={!!node.is_mine} disabled={mineBusy} onclick={toggleMine} class={node.is_mine ? 'mine on' : 'mine'}>{t('nodes.mine')}</Button>
    <NodeFlags {node} />
  </div>

  <div class="acts">
    {#if !node.is_local_radio}
      <Button icon="chat" disabled={!firstRadio} title={firstRadio ? '' : t('nodes.tr.connectRadio')} onclick={directMessage}>{t('nodes.detail.directMessage')}</Button>
    {/if}
    <Button icon="settings" disabled={!firstRadio} title={firstRadio ? '' : t('nodes.tr.connectRadio')} onclick={() => openConfig(node.id)}>{t('nodes.detail.configure')}</Button>
    {#if node.lat !== null}
      <Button icon="route" disabled={loading} onclick={toggleTrack}>{shown ? t('nodes.detail.hideTrack') : loading ? t('shell.loading') : t('nodes.detail.showTrack')}</Button>
    {/if}
    <Button icon="copy" onclick={copyLink}>{linkCopied ? t('nodes.detail.linkCopied') : t('nodes.detail.copyLink')}</Button>
  </div>
  {#if shown}
    <div class="periods" role="group" aria-label={t('nodes.detail.trackPeriod')}>
      {#each TRACK_PERIODS as p (p.hours)}
        <button type="button" class="ui-chip" aria-pressed={trackHours === p.hours} disabled={loading} onclick={() => pickPeriod(p.hours)}>{t(p.labelKey)}</button>
      {/each}
    </div>
    {#if trackRange}
      <p class="hint">{trackRange}</p>
      <div class="gap"><Button icon="download" onclick={exportGpx}>{t('nodes.detail.exportGpx')}</Button></div>
    {/if}
  {/if}
  {#if !firstRadio}<p class="hint">{t('nodes.detail.needRadio')}</p>{/if}
  {#if msg}
    <div class="gap">
      <Banner kind="warn" title={t(msg)}>
        {#snippet action()}
          {#if msg === TRACK_ERROR}<Button onclick={loadTrack}>{t('common.retry')}</Button>{/if}
        {/snippet}
      </Banner>
    </div>
  {/if}

  {#if localRadio}
    <div class="gap"><PrivacyBanner nodeId={node.id} compact /></div>
  {/if}

  {#if keyChangedRecently(node, now)}
    <div class="gap">
      <Banner kind="warn" title={t('chat.keyChangedBanner', { name: nodeName(node), date: formatDate(node.key_changed ?? null) })} />
    </div>
  {/if}

  <dl>
    {#each rows as [k, v] (k)}
      <dt>{k}</dt>
      <dd>{v}</dd>
    {/each}
  </dl>

  <h3>{t('nodes.detail.heardBy')}</h3>
  {#if heard.length === 0 && !showMqtt}
    <p class="ui-muted none">{t('nodes.detail.noRadio')}</p>
  {:else}
    <ul class="heard">
      {#each heard as h (h.rid)}
        <li>
          <SourceMark source="radio" size={18} />
          <b>{h.name}</b>
          <SnrBadge value={h.snr} />
          <span class="ui-mono">RSSI {h.rssi === null ? '–' : `${h.rssi} dBm`}</span>
          <span>{t('nodes.detail.hopsOf', { hops: hopsLabel(h.hops) })}</span>
          <span class="ui-muted">{ago(contactMinutes(h.time, now))}</span>
        </li>
      {/each}
      {#if showMqtt}<li><SourceMark source="mqtt" size={18} /><b>MQTT</b> <span>{t('nodes.detail.gateways', { n: node.mqtt_gateways })}</span></li>{/if}
    </ul>
  {/if}
  <TakInfo {node} />

  <NodeCharts nodeId={node.id} />
  <SensorSection {node} />
  <Traceroute {node} />
  <TraceSchedule {node} />
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
