<script lang="ts">
  import { locale, t } from '../lib/i18n/index.svelte'
  import { onMount } from 'svelte'
  import { getJSON, packets as fetchPackets } from '../lib/api'
  import { num } from '../lib/format'
  import { kindLabel, kindOptions } from '../lib/netstats'
  import { hopsText, packetQuery, PAGE_SIZE, resolveNode, statusOptions, type PacketFilters } from '../lib/packets'
  import type { AppSettings } from '../lib/settings'
  import type { Node, PacketRow } from '../lib/types'
  import { viewport } from '../lib/viewport.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import Select from '../lib/ui/Select.svelte'
  import SourceMark from '../lib/ui/SourceMark.svelte'
  import Switch from '../lib/ui/Switch.svelte'
  import Table, { type Column } from '../lib/ui/Table.svelte'
  import PacketDetail from './PacketDetail.svelte'

  let { nodes, onpick }: { nodes: Node[]; onpick: (id: string) => void } = $props()

  const LIVE_MS = 5000
  const LIVE_MAX_ROWS = 500
  const LIVE_MAX_PAGES = 10
  const NODE_DEBOUNCE_MS = 300
  const BROADCAST = '!ffffffff'

  const COLS = $derived<Column[]>([
    { key: 'time', label: t('packets.col.time'), fix: true },
    { key: 'from', label: t('packets.col.from') },
    { key: 'to', label: t('packets.col.to') },
    { key: 'kind', label: t('packets.col.kind') },
    { key: 'source', label: t('nodes.source') },
    { key: 'snr', label: 'SNR', num: true },
    { key: 'hops', label: t('nodes.hops') },
    { key: 'copies', label: t('packets.col.copies'), num: true },
  ])
  const SOURCES = $derived<{ value: PacketFilters['source']; label: string }[]>([
    { value: '', label: t('packets.all.f') },
    { value: 'rf', label: t('nodes.sourceRadio') },
    { value: 'mqtt', label: 'MQTT' },
  ])
  const PERIODS = $derived<{ value: PacketFilters['period']; label: string }[]>([
    { value: '1h', label: t('packets.period.1h') },
    { value: '6h', label: t('packets.period.6h') },
    { value: '24h', label: t('nodes.age24h') },
    { value: 'all', label: t('packets.period.all') },
  ])

  let mode = $state<AppSettings['packet_log_mode'] | null>(null)
  let f = $state<PacketFilters>({ node: '', kind: '', source: '', status: '', minSnr: null, period: '1h' })
  /** Il testo del nodo dopo una pausa: ogni tasto non rilancia l'interrogazione. */
  let nodeQuery = $state('')
  let polling = false
  let live = $state(false)
  let items = $state<PacketRow[]>([])
  let next = $state<number | null>(null)
  let loading = $state(false)
  let error = $state(false)
  let selected = $state<number | null>(null)
  let innerWidth = $state(0)
  /** Si incrementa a ogni nuova interrogazione: le risposte di una precedente si scartano. */
  let gen = 0

  const nodeText = $derived(nodeQuery.trim())
  const nodeId = $derived(resolveNode(nodeText, nodes))
  const nodeUnknown = $derived(nodeText !== '' && nodeId === null)
  const wide = $derived(!viewport.phone && innerWidth >= 1100)
  const names = $derived(new Map(nodes.map((n) => [n.id, n.long_name ?? n.short_name ?? n.id])))
  const nodeMatch = $derived(nodeId === null ? '' : (names.get(nodeId) ?? nodeId))

  function loadMode() {
    getJSON<AppSettings>('/settings')
      .then((s) => (mode = s.packet_log_mode ?? 'archived'))
      .catch(() => (mode ??= 'archived'))
  }
  onMount(loadMode)
  // La modalità si cambia in Impostazioni: al ritorno sulla pagina si rilegge
  function onVisible() {
    if (document.visibilityState === 'visible') loadMode()
  }

  $effect(() => {
    const text = f.node
    const timer = setTimeout(() => (nodeQuery = text), NODE_DEBOUNCE_MS)
    return () => clearTimeout(timer)
  })

  // Prima pagina: si rilegge a ogni cambio di filtro
  $effect(() => {
    // il testo del nodo arriva da `nodeId` (con pausa): qui non si legge `f.node`
    const filters: PacketFilters = { node: '', kind: f.kind, source: f.source, status: f.status, minSnr: f.minSnr, period: f.period }
    const id = nodeId
    const unknown = nodeUnknown
    const m = mode
    if (m === null || m === 'off' || unknown) {
      items = []
      next = null
      return
    }
    const my = ++gen
    loading = true
    error = false
    fetchPackets(packetQuery(filters, Date.now() / 1000, null, id))
      .then((r) => {
        if (my !== gen) return
        items = r.items
        next = r.next_before_id
      })
      .catch(() => {
        if (my === gen) error = true
      })
      .finally(() => {
        if (my === gen) loading = false
      })
  })

  async function more() {
    if (next === null || loading) return
    const my = gen
    loading = true
    try {
      const r = await fetchPackets(packetQuery(f, Date.now() / 1000, next, nodeId))
      if (my !== gen) return
      const seen = new Set(items.map((p) => p.id))
      items = [...items, ...r.items.filter((p) => !seen.has(p.id))]
      next = r.next_before_id
    } catch {
      if (my === gen) error = true
    } finally {
      if (my === gen) loading = false
    }
  }

  async function poll() {
    // prima pagina non ancora arrivata: niente after_id=0 (con «Tutto» darebbe le righe più vecchie)
    if (polling || items.length === 0) return
    polling = true
    const my = gen
    try {
      // Dall'ultimo id visto, a pagine: si prosegue finché la pagina è piena
      for (let page = 0; page < LIVE_MAX_PAGES; page++) {
        const r = await fetchPackets(packetQuery(f, Date.now() / 1000, null, nodeId, items[0].id))
        if (my !== gen) return
        if (r.items.length > 0) {
          const seen = new Set(items.map((p) => p.id))
          const fresh = r.items.filter((p) => !seen.has(p.id)).reverse()
          const merged = [...fresh, ...items]
          if (merged.length > LIVE_MAX_ROWS) {
            items = merged.slice(0, LIVE_MAX_ROWS)
            // «Carica altri» riparte dall'ultima riga tenuta, senza buchi
            next = items[items.length - 1].id
          } else {
            items = merged
          }
        }
        if (r.items.length < PAGE_SIZE) break
      }
    } catch {
      // al prossimo giro
    } finally {
      polling = false
    }
  }

  // In diretta: finché lo Switch è acceso e l'ispettore attivo
  $effect(() => {
    const on = live
    const active = mode !== null && mode !== 'off' && !nodeUnknown
    if (!on || !active) return
    const timer = setInterval(poll, LIVE_MS)
    return () => clearInterval(timer)
  })

  const timeText = (sec: number) => new Date(sec * 1000).toLocaleTimeString(locale())
  const label = (id: string) => (id === BROADCAST ? t('packets.all.m') : (names.get(id) ?? id))
  const rowKey = (p: PacketRow) => String(p.id)
</script>

<svelte:window bind:innerWidth onfocus={loadMode} />
<svelte:document onvisibilitychange={onVisible} />

<div class="insp">
  {#if mode === 'off'}
    <Banner kind="warn" title={t('packets.off')} />
  {:else}
    <div class="filters">
      <Field label={t('packets.filter.node')} for="pk-node">
        {#snippet children()}<input id="pk-node" class="ui-input" type="text" placeholder={t('packets.filter.nodePlaceholder')} bind:value={f.node} />{/snippet}
      </Field>
      <Field label={t('packets.col.kind')} for="pk-kind">
        {#snippet children()}
          <Select id="pk-kind" bind:value={f.kind}>
            <option value="">{t('packets.all.m')}</option>
            {#each kindOptions() as [k, l] (k)}<option value={k}>{l}</option>{/each}
          </Select>
        {/snippet}
      </Field>
      <Field label={t('packets.filter.status')} for="pk-status">
        {#snippet children()}
          <Select id="pk-status" bind:value={f.status}>
            <option value="">{t('packets.all.m')}</option>
            {#each statusOptions() as [k, l] (k)}<option value={k}>{l}</option>{/each}
          </Select>
        {/snippet}
      </Field>
      <Field label={t('packets.filter.minSnr')} for="pk-snr">
        {#snippet children()}<input id="pk-snr" class="ui-input ui-mono" type="number" step="0.5" bind:value={f.minSnr} />{/snippet}
      </Field>
      <div class="seg">
        <span class="ui-lbl">{t('nodes.source')}</span>
        <Segmented items={SOURCES} bind:value={f.source} label={t('nodes.source')} />
      </div>
      <div class="seg">
        <span class="ui-lbl">{t('packets.filter.period')}</span>
        <Segmented items={PERIODS} bind:value={f.period} label={t('packets.filter.period')} />
      </div>
      <Switch bind:checked={live} label={t('packets.live')} />
    </div>
    {#if nodeUnknown}<p class="ui-hint err">{t('packets.nodeNotFound')}</p>{:else if nodeId !== null}<p class="ui-muted">{t('packets.nodeIs', { name: nodeMatch })}</p>{/if}
    {#if error}<Banner kind="danger" title={t('packets.unavailable')} />{/if}

    <div class="body" class:split={wide}>
      {#if !(selected !== null && !wide)}
        <div class="list">
          {#if items.length === 0 && !loading && !nodeUnknown}
            <Empty icon="network" title={t('packets.empty')} />
          {:else if items.length > 0}
            <Table columns={COLS} rows={items} {rowKey} selectedKey={selected === null ? null : String(selected)} onrowclick={(p) => (selected = p.id)} caption={t('packets.caption')}>
              {#snippet cell(p, c)}
                {#if c.key === 'time'}
                  {timeText(p.time)}
                {:else if c.key === 'from'}
                  {p.from_name ?? label(p.from)}
                {:else if c.key === 'to'}
                  {label(p.to)}
                {:else if c.key === 'kind'}
                  {kindLabel(p.kind)}
                {:else if c.key === 'source'}
                  <SourceMark source={p.source === 'rf' ? 'radio' : 'mqtt'} size={16} />
                {:else if c.key === 'snr'}
                  {p.snr === null ? '–' : num(p.snr, 1).replace('-', '−')}
                {:else if c.key === 'hops'}
                  {hopsText(p)}
                {:else}
                  {p.copies}
                {/if}
              {/snippet}
            </Table>
          {/if}
          {#if next !== null}
            <div class="more"><Button disabled={loading} onclick={more}>{t('packets.loadMore')}</Button></div>
          {/if}
        </div>
      {/if}
      {#if selected !== null}
        <div class="detail">
          <PacketDetail id={selected} {nodes} {onpick} {wide} onclose={() => (selected = null)} />
        </div>
      {/if}
    </div>
  {/if}
</div>

<style>
  .insp {
    padding: var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .filters {
    display: flex;
    flex-wrap: wrap;
    align-items: flex-end;
    gap: var(--space-3);
  }
  .filters :global(.ui-field) {
    width: 160px;
  }
  .seg {
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .body.split {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(360px, 440px);
    gap: var(--space-3);
    align-items: start;
  }
  .list {
    min-width: 0;
  }
  .more {
    display: flex;
    justify-content: center;
    padding: var(--space-3) 0;
  }
  :global(.vp-phone) .filters :global(.ui-field) {
    width: 100%;
  }
</style>
