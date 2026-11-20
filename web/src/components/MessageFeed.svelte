<script lang="ts">
  import { getJSON } from '../lib/api'
  import { flag, timeAgo } from '../lib/format'
  import { app, addMessage } from '../lib/stores.svelte'
  import type { Message } from '../lib/types'

  let { now, onpick }: { now: number; onpick: (id: string) => void } = $props()

  const LIMIT = 200
  let older = $state<Message[]>([])
  let error = $state('')
  let loading = $state(false)
  let exhausted = $state(false)

  // Il server filtra per tutte le nazioni selezionate (elenco separato da virgole)
  const countryParam = $derived(
    app.filter.countries.length > 0 ? encodeURIComponent(app.filter.countries.join(',')) : null,
  )

  const shown = $derived.by(() => {
    const byKey = new Map<string, Message>()
    for (const m of [...older, ...app.messages]) byKey.set(m.key, m)
    const cs = app.filter.countries
    return [...byKey.values()]
      .filter((m) => cs.length === 0 || cs.includes(m.country ?? 'none'))
      .sort((a, b) => b.time - a.time)
  })

  function qs(extra: string): string {
    return `limit=${LIMIT}${countryParam ? `&country=${countryParam}` : ''}${extra}`
  }

  $effect(() => {
    const q = qs('')
    older = []
    exhausted = false
    error = ''
    getJSON<Message[]>(`/messages?${q}`)
      .then((list) => {
        // dal piu' vecchio al piu' recente: il limite dello store scarta i piu' vecchi
        for (const m of [...list].reverse()) addMessage(m)
      })
      .catch(() => (error = 'Messaggi non disponibili'))
  })

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
  {#if error}<p class="err" role="alert">{error}</p>{/if}
  {#if shown.length === 0 && !error}<p class="empty">Nessun messaggio</p>{/if}
  <ul>
    {#each shown as m (m.key)}
      <li>
        <div class="head">
          <span>{flag(m.country)}</span>
          <button class="name" onclick={() => onpick(m.from)}>{m.from_name ?? m.from}</button>
          <span class="ch">{m.channel}</span>
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
    font-size: 12px;
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
