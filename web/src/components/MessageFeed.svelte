<script lang="ts">
  import { onMount } from 'svelte'
  import { getJSON } from '../lib/api'
  import { flag, timeAgo } from '../lib/format'
  import { app, addMessage } from '../lib/stores.svelte'
  import { matchFeed } from '../lib/filters'
  import type { Message } from '../lib/types'

  let { now, onpick }: { now: number; onpick: (id: string) => void } = $props()

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
  const shown = $derived(all.filter((m) => matchFeed(m.country, app.feedFilter)))
  const hidden = $derived(all.length - shown.length)

  const qs = (extra: string) => `limit=${LIMIT}${extra}`

  onMount(() => {
    getJSON<Message[]>(`/messages?${qs('')}`)
      .then((list) => {
        // dal piu' vecchio al piu' recente: il limite dello store scarta i piu' vecchi
        for (const m of [...list].reverse()) addMessage(m)
      })
      .catch(() => (error = 'Messaggi non disponibili'))
    getJSON<Country[]>('/countries')
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
    <label class="opt"><input type="checkbox" bind:checked={app.feedFilter.includeUnknown} /> Includi nodi senza posizione</label>
    <button class="chip" onclick={() => (app.feedFilter.countries = [])}>Tutte le nazioni</button>
    <ul class="cl">
      {#each countries as c (c.code)}
        <li>
          <label class="opt">
            <input type="checkbox" checked={app.feedFilter.countries.includes(c.code)} onchange={() => toggle(c.code)} />
            <span>{flag(c.code)} {c.name}</span>
          </label>
        </li>
      {/each}
    </ul>
  </details>
  {#if hidden > 0}<p class="hid" role="status">{hidden} {hidden === 1 ? 'messaggio nascosto' : 'messaggi nascosti'} dal filtro</p>{/if}
  {#if error}<p class="err" role="alert">{error}</p>{/if}
  {#if shown.length === 0 && !error}<p class="empty">Nessun messaggio</p>{/if}
  <ul>
    {#each shown as m (m.key)}
      <li>
        <div class="head">
          <span title={m.country ?? 'Posizione sconosciuta'}>{m.country ? flag(m.country) : '?'}</span>
          <button class="name" onclick={() => onpick(m.from)}>{m.from_name ?? m.from}</button>
          {#if m.channel}<span class="ch">{m.channel}</span>{/if}
          <span class="t">{timeAgo(m.time, now)}</span>
        </div>
        <p class="text">{m.text}</p>
      </li>
    {/each}
  </ul>
  {#if !exhausted && shown.length > 0}
    <button class="more" onclick={loadOlder} disabled={loading}>
      {loading ? 'Caricamento…' : 'Carica precedenti'}
    </button>
  {/if}
</div>

<style>
  .ff {
    padding: 6px 8px;
    border-bottom: 1px solid #1f2937;
    font-size: 13px;
  }
  .ff summary {
    cursor: pointer;
    min-height: 40px;
    display: flex;
    align-items: center;
  }
  .opt {
    display: flex;
    gap: 6px;
    align-items: center;
    min-height: 40px;
    cursor: pointer;
  }
  .chip {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 999px;
    padding: 6px 14px;
    min-height: 40px;
    font-size: 13px;
    cursor: pointer;
  }
  .cl {
    max-height: 200px;
    overflow: auto;
  }
  .hid {
    margin: 0;
    padding: 6px 8px;
    font-size: 13px;
    color: #fbbf24;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li {
    padding: 8px;
    border-bottom: 1px solid #1f2937;
  }
  .head {
    display: flex;
    gap: 6px;
    align-items: baseline;
    font-size: 13px;
  }
  .name {
    background: none;
    border: 0;
    padding: 0;
    color: #93c5fd;
    font: inherit;
    font-weight: 600;
    cursor: pointer;
    text-align: left;
    overflow-wrap: anywhere;
  }
  .ch {
    color: #9ca3af;
  }
  .t {
    margin-left: auto;
    color: #9ca3af;
    white-space: nowrap;
    font-size: 13px;
  }
  .text {
    margin: 4px 0 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .more {
    display: block;
    margin: 8px auto;
    padding: 6px 12px;
    min-height: 40px;
    font-size: 13px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    cursor: pointer;
  }
  .empty,
  .err {
    padding: 8px 16px;
    margin: 0;
  }
  .empty {
    color: #9ca3af;
  }
  .err {
    color: #f87171;
  }
</style>
