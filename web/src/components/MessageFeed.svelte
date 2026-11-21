<script lang="ts">
  import { onMount } from 'svelte'
  import { getJSON, getCountries } from '../lib/api'
  import { ago } from '../lib/format'
  import { statusIcon } from '../lib/chat'
  import { statusAria } from '../lib/send'
  import { routingErrorText, threadItems } from '../lib/reactions'
  import { T } from '../lib/strings/messaggi'
  import Badge from '../lib/ui/Badge.svelte'
  import BrokerBadge from '../lib/ui/BrokerBadge.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Check from '../lib/ui/Check.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import Flag from '../lib/ui/Flag.svelte'
  import Icon from '../lib/ui/Icon.svelte'
  import MessageActions from './chat/MessageActions.svelte'
  import MessageQuote from './chat/MessageQuote.svelte'
  import ReactionChips from './chat/ReactionChips.svelte'
  import { app, addMessage } from '../lib/stores.svelte'
  import { matchFeed } from '../lib/filters'
  import { emptyFeedHint, navigate } from '../lib/shell/navigate'
  import type { Message } from '../lib/types'

  let {
    now,
    onpick,
    onreply,
    onreact,
  }: { now: number; onpick: (id: string) => void; onreply: (m: Message) => void; onreact: (m: Message, emoji: string) => void } = $props()

  const LIMIT = 200
  let older = $state<Message[]>([])
  let error = $state('')
  let loading = $state(false)
  let exhausted = $state(false)

  type Country = { code: string; name: string; nodes: number }
  let countries = $state<Country[]>([])

  // Il feed ha un filtro suo (non quello della mappa): il server manda tutto, si filtra qui
  const all = $derived.by(() => {
    const byKey = new Map<string, Message>()
    for (const m of [...older, ...app.messages]) byKey.set(m.key, m)
    return [...byKey.values()].filter((m) => !m.radio_id).sort((a, b) => b.time - a.time)
  })
  // i messaggi inviati da qui restano sempre visibili, qualunque sia il filtro
  const shown = $derived(all.filter((m) => m.direction === 'out' || matchFeed(m.country, app.feedFilter)))
  const hidden = $derived(all.length - shown.length)
  const nodeName = (id: string) => app.nodes.get(id)?.long_name || app.nodes.get(id)?.short_name || id
  const items = $derived(threadItems(shown, nodeName, new Set()))
  let listEl = $state<HTMLElement | null>(null)

  function jumpTo(key: string) {
    const el = [...(listEl?.querySelectorAll<HTMLElement>('[data-mkey]') ?? [])].find((e) => e.dataset.mkey === key)
    el?.scrollIntoView({ block: 'center' })
  }

  const qs = (extra: string) => `limit=${LIMIT}${extra}`

  const hint = $derived(emptyFeedHint(app.status?.mqtt ?? null))

  function loadFirst() {
    error = ''
    getJSON<Message[]>(`/messages?${qs('')}`)
      .then((list) => {
        // dal piu' vecchio al piu' recente: il limite dello store scarta i piu' vecchi
        for (const m of [...list].reverse()) addMessage(m)
      })
      .catch(() => (error = 'Messaggi non disponibili'))
  }

  function showAll() {
    app.feedFilter.countries = []
    app.feedFilter.includeUnknown = true
  }

  onMount(() => {
    loadFirst()
    getCountries()
      .then((list) => (countries = list.filter((c) => c.code !== 'none')))
      .catch(() => {})
  })

  function toggle(code: string) {
    const c = app.feedFilter.countries
    app.feedFilter.countries = c.includes(code) ? c.filter((x) => x !== code) : [...c, code]
  }

  async function loadOlder() {
    const oldest = shown.length ? shown[shown.length - 1].time : Math.floor(Date.now() / 1000)
    loading = true
    error = ''
    try {
      const list = await getJSON<Message[]>(`/messages/history?${qs(`&before=${oldest}`)}`)
      if (list.length < LIMIT) exhausted = true
      older = [...older, ...list]
    } catch {
      error = 'Impossibile caricare i messaggi precedenti'
    } finally {
      loading = false
    }
  }
</script>

<div class="feed">
  <details class="ff">
    <summary>
      Filtro messaggi ({app.feedFilter.countries.length === 0 ? 'tutte le nazioni' : `${app.feedFilter.countries.length} nazioni`})
    </summary>
    <Check bind:checked={app.feedFilter.includeUnknown} label="Includi nodi senza posizione" />
    <div class="chips">
      <button type="button" class="ui-chip" aria-pressed={app.feedFilter.countries.length === 0} onclick={() => (app.feedFilter.countries = [])}>Tutte le nazioni</button>
      {#each countries as c (c.code)}
        <button type="button" class="ui-chip" aria-pressed={app.feedFilter.countries.includes(c.code)} onclick={() => toggle(c.code)}>
          <Flag code={c.code} name={c.name} />{c.name}
        </button>
      {/each}
    </div>
  </details>
  {#if hidden > 0}
    <div class="hid" role="status">
      <span>{hidden} {hidden === 1 ? 'messaggio nascosto' : 'messaggi nascosti'} dal filtro</span>
      <Button onclick={showAll}>Mostra tutti</Button>
    </div>
  {/if}
  {#if error}
    <div class="pad">
      <Banner kind="danger" title={error}>
        {#snippet action()}<Button onclick={loadFirst}>Riprova</Button>{/snippet}
      </Banner>
    </div>
  {/if}
  {#if shown.length === 0 && !error}
    <Empty icon="chat" title={hint.title}>
      {hint.text}
      {#snippet action()}
        {#if hint.action}{@const a = hint.action}<Button onclick={() => navigate(a.tab)}>{a.label}</Button>{/if}
      {/snippet}
    </Empty>
  {/if}
  <ul bind:this={listEl}>
    {#each items as it (it.msg.key)}
      {@const m = it.msg}
      {@const out = m.direction === 'out'}
      {#if it.orphan}
        <li class="orphan">{T.orphanReaction(m.text, out ? T.you : (m.from_name ?? nodeName(m.from)))}</li>
      {:else}
      <li class:out data-mkey={m.key}>
        <div class="head">
          <Flag code={m.country} name={m.country ?? 'Posizione sconosciuta'} />
          {#if out}
            <b class="name">Tu</b>
          {:else}
            <button type="button" class="name" onclick={() => onpick(m.from)}>{m.from_name ?? m.from}</button>
          {/if}
          {#if m.channel}<Badge>{m.channel}</Badge>{/if}
          {#if out}<Badge kind="info">via MQTT</Badge>{/if}
          <BrokerBadge id={m.broker} />
          <span class="t">{ago((now - m.time) / 60)}</span>
          {#if out && m.status}
            <span class="st" role="img" title={statusAria(m.status, m.via)} aria-label={statusAria(m.status, m.via)}>{statusIcon(m.status)}</span>
          {/if}
          {#if m.pki}<Icon name="lock" size={14} label={T.pkiAria} />{/if}
          <MessageActions msg={m} {onreply} {onreact} />
        </div>
        <MessageQuote replyTo={it.replyTo} missing={it.replyMissing} {nodeName} onjump={jumpTo} />
        <p class="text">{m.text}</p>
        <ReactionChips reactions={it.reactions} />
        {#if m.status === 'failed'}<p class="fail" role="status">{routingErrorText(m.error)}</p>{/if}
      </li>
      {/if}
    {/each}
  </ul>
  {#if !exhausted && shown.length > 0}
    <div class="more"><Button onclick={loadOlder} disabled={loading}>{loading ? 'Caricamento…' : 'Carica precedenti'}</Button></div>
  {/if}
</div>

<style>
  .feed {
    color: var(--ink);
  }
  .ff {
    padding: var(--space-1) var(--space-3);
    border-bottom: 1px solid var(--line);
  }
  .ff summary {
    cursor: pointer;
    min-height: var(--touch-min);
    display: flex;
    align-items: center;
    font: 600 14px/20px var(--font-sans);
  }
  .chips {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
    max-height: 200px;
    overflow: auto;
    padding: var(--space-2) 0 var(--space-3);
  }
  .hid {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    margin: 0;
    padding: var(--space-2) var(--space-3);
    font-size: 13px;
    color: var(--warn);
  }
  .pad {
    padding: var(--space-3);
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    padding: var(--space-3);
    border-bottom: 1px solid var(--line);
  }
  li.out {
    background: var(--accent-soft);
  }
  .head {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    flex-wrap: wrap;
    font-size: 13px;
  }
  .name {
    background: none;
    border: 0;
    padding: 0;
    min-height: 24px;
    color: var(--accent-ink);
    font: 600 14px/20px var(--font-sans);
    cursor: pointer;
    text-align: left;
    overflow-wrap: anywhere;
  }
  b.name {
    cursor: default;
  }
  .t {
    margin-left: auto;
    color: var(--ink-muted);
    white-space: nowrap;
  }
  .st {
    min-width: 20px;
    text-align: right;
  }
  .text {
    margin: var(--space-1) 0 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  li.orphan {
    color: var(--ink-muted);
    font: 400 13px/18px var(--font-sans);
  }
  .fail {
    margin: var(--space-1) 0 0;
    color: var(--danger);
    font-size: 13px;
  }
  .more {
    display: flex;
    justify-content: center;
    padding: var(--space-3);
  }
  :global(.vp-phone) .head,
  :global(.vp-phone) .orphan,
  :global(.vp-phone) .fail,
  :global(.vp-phone) .hid {
    font-size: 14px;
  }
</style>
