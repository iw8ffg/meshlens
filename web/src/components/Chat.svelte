<script lang="ts">
  import { tick, untrack } from 'svelte'
  import { getJSON, send } from '../lib/api'
  import { timeAgo } from '../lib/format'
  import {
    MAX_BYTES,
    MQTT_CONV,
    byteLength,
    groupMessages,
    localNodeIds,
    pickSendRadio,
    statusIcon,
    statusLabel,
  } from '../lib/chat'
  import { app, addMessage, addRadioHistory } from '../lib/stores.svelte'
  import MessageFeed from './MessageFeed.svelte'
  import type { Message } from '../lib/types'

  let { now, onpick }: { now: number; onpick: (id: string) => void } = $props()

  let conv = $state<string>(MQTT_CONV)
  let text = $state('')
  let radioId = $state('')
  let sending = $state(false)
  let error = $state('')
  let listEl = $state<HTMLElement | null>(null)
  let nearBottom = true
  let forceScroll = false
  let loadingOlder = $state(false)
  let exhausted = $state(false)
  let olderError = $state('')

  const PAGE = 200

  async function loadOlder() {
    const oldest = app.radioMessages.length ? app.radioMessages[0].time : Math.floor(Date.now() / 1000)
    loadingOlder = true
    olderError = ''
    try {
      const list = await getJSON<Message[]>(`/messages/radio?limit=${PAGE}&before=${oldest}`)
      if (list.length < PAGE) exhausted = true
      addRadioHistory(list)
    } catch {
      olderError = 'Impossibile caricare i messaggi precedenti'
    } finally {
      loadingOlder = false
    }
  }

  // Apertura da fuori (es. "Messaggio diretto" nel dettaglio nodo)
  $effect(() => {
    if (app.chatConv) {
      conv = app.chatConv
      app.chatConv = null
    }
  })

  const localIds = $derived(localNodeIds(app.radios))
  const groups = $derived(groupMessages(app.radioMessages, localIds))

  const nodeName = (id: string) => app.nodes.get(id)?.long_name || app.nodes.get(id)?.short_name || id
  const radioName = (id: string) => app.radios.find((r) => r.id === id)?.name ?? id

  function label(key: string): string {
    if (key === MQTT_CONV) return 'Pubblico (MQTT)'
    const [kind, rid, rest] = splitKey(key)
    if (kind === 'ch') {
      const ch = app.radios.find((r) => r.id === rid)?.channels.find((c) => String(c.index) === rest)
      return `${radioName(rid)} · ${ch?.name || `Canale ${rest}`}`
    }
    return `${radioName(rid)} · DM ${nodeName(rest)}`
  }

  // "dm:r1:!abcd" -> ['dm', 'r1', '!abcd']
  function splitKey(key: string): [string, string, string] {
    const a = key.indexOf(':')
    const b = key.indexOf(':', a + 1)
    return [key.slice(0, a), key.slice(a + 1, b), key.slice(b + 1)]
  }

  const options = $derived.by(() => {
    const keys: string[] = [MQTT_CONV]
    for (const r of app.radios) for (const c of r.channels) keys.push(`ch:${r.id}:${c.index}`)
    for (const k of groups.keys()) if (!keys.includes(k)) keys.push(k)
    if (!keys.includes(conv)) keys.push(conv)
    return keys.map((k) => ({ key: k, label: label(k) }))
  })

  const isRadioConv = $derived(conv !== MQTT_CONV)
  const convRadio = $derived(isRadioConv ? splitKey(conv)[1] : '')
  const msgs = $derived(groups.get(conv) ?? [])
  const connected = $derived(app.radios.filter((r) => r.state === 'connected'))

  // Radio di invio: la scelta manuale persiste (vedi pickSendRadio)
  let lastConv = ''
  $effect(() => {
    const changed = conv !== lastConv
    lastConv = conv
    radioId = pickSendRadio(
      untrack(() => radioId),
      convRadio,
      connected.map((r) => r.id),
      changed,
    )
  })

  const bytes = $derived(byteLength(text))
  const over = $derived(bytes > MAX_BYTES)
  const canSend = $derived(!sending && !over && text.trim() !== '' && radioId !== '')

  async function submit() {
    if (!canSend) return
    const [kind, , rest] = splitKey(conv)
    sending = true
    error = ''
    try {
      const m = await send<Message>('POST', `/radios/${encodeURIComponent(radioId)}/send`, {
        text: text.trim(),
        channel_index: kind === 'ch' ? Number(rest) : 0,
        to: kind === 'dm' ? rest : null,
      })
      forceScroll = true
      addMessage(m)
      text = ''
    } catch (e) {
      error = e instanceof Error && e.message ? e.message : 'Invio non riuscito'
    } finally {
      sending = false
    }
  }

  function onkey(e: KeyboardEvent) {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      submit()
    }
  }

  // Scorre in fondo quando arrivano messaggi nuovi
  $effect(() => {
    void msgs.length
    tick().then(() => {
      if (listEl && (nearBottom || forceScroll)) listEl.scrollTo({ top: listEl.scrollHeight })
      forceScroll = false
    })
  })
</script>

<div class="chat">
  <div class="bar">
    <select aria-label="Conversazione" bind:value={conv}>
      {#each options as o (o.key)}
        <option value={o.key}>{o.label}</option>
      {/each}
    </select>
  </div>

  {#if !isRadioConv}
    <div class="feed"><MessageFeed {now} {onpick} /></div>
  {:else}
    <ul
      class="list"
      bind:this={listEl}
      onscroll={() => (nearBottom = !!listEl && listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 60)}
    >
      {#if !exhausted}
        <li class="older">
          <button type="button" onclick={loadOlder} disabled={loadingOlder}>
            {loadingOlder ? 'Caricamento…' : 'Carica precedenti'}
          </button>
        </li>
      {/if}
      {#if olderError}<li class="err" role="alert">{olderError}</li>{/if}
      {#if msgs.length === 0}<li class="empty">Nessun messaggio</li>{/if}
      {#each msgs as m (m.key)}
        {@const out = m.direction === 'out'}
        <li class="msg" class:out>
          <div class="bubble">
            {#if !out}
              <button class="name" onclick={() => onpick(m.from)}>{m.from_name ?? nodeName(m.from)}</button>
            {/if}
            <p class="text">{m.text}</p>
            <div class="meta">
              <span>{timeAgo(m.time, now)}</span>
              {#if out && m.status}
                <span class="st" class:bad={m.status === 'failed'} title={statusLabel(m.status)} aria-label={statusLabel(m.status)}>
                  {statusIcon(m.status)}
                </span>
              {/if}
            </div>
          </div>
        </li>
      {/each}
    </ul>

    <form class="composer" onsubmit={(e) => (e.preventDefault(), submit())}>
      {#if connected.length === 0}
        <p class="warn">Nessuna radio connessa: impossibile inviare.</p>
      {/if}
      <textarea
        rows="2"
        placeholder={conv.startsWith('dm:') ? 'Messaggio diretto…' : 'Messaggio sul canale…'}
        bind:value={text}
        onkeydown={onkey}
        disabled={connected.length === 0}
      ></textarea>
      <div class="row">
        <span class="count" class:over>{bytes}/{MAX_BYTES} byte{over ? ' — troppo lungo' : ''}</span>
        <select aria-label="Radio di invio" bind:value={radioId} disabled={connected.length === 0}>
          {#each connected as r (r.id)}
            <option value={r.id}>{r.name}</option>
          {/each}
        </select>
        <button type="submit" disabled={!canSend} title="Ctrl+Invio">{sending ? 'Invio…' : 'Invia'}</button>
      </div>
      {#if error}<p class="err" role="alert">{error}</p>{/if}
    </form>
  {/if}
</div>

<style>
  .chat {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
  }
  .bar {
    padding: 6px 8px;
    border-bottom: 1px solid #1f2937;
  }
  select,
  textarea {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    font: inherit;
  }
  .bar select {
    width: 100%;
    padding: 6px;
  }
  .feed {
    flex: 1;
    overflow: auto;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 8px;
    flex: 1;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: 6px;
    min-height: 120px;
  }
  .msg {
    display: flex;
  }
  .msg.out {
    justify-content: flex-end;
  }
  .bubble {
    max-width: 85%;
    background: #1f2937;
    border-radius: 8px;
    padding: 6px 8px;
  }
  .out .bubble {
    background: #1d4ed8;
  }
  .name {
    background: none;
    border: 0;
    padding: 0;
    color: #93c5fd;
    font: inherit;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
  }
  .text {
    margin: 2px 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .meta {
    display: flex;
    gap: 6px;
    justify-content: flex-end;
    font-size: 11px;
    color: #9ca3af;
  }
  .out .meta {
    color: #bfdbfe;
  }
  .st.bad {
    color: #fca5a5;
  }
  .older {
    text-align: center;
  }
  .older button {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 4px 10px;
    cursor: pointer;
  }
  .empty {
    color: #9ca3af;
    padding: 8px;
  }
  .composer {
    border-top: 1px solid #1f2937;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  textarea {
    resize: vertical;
    padding: 6px;
  }
  .row {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .count {
    flex: 1;
    font-size: 12px;
    color: #9ca3af;
  }
  .count.over {
    color: #f87171;
  }
  .row select {
    padding: 4px;
    max-width: 40%;
  }
  button[type='submit'] {
    background: #2563eb;
    color: #fff;
    border: 0;
    border-radius: 6px;
    padding: 6px 14px;
    cursor: pointer;
  }
  button[type='submit']:disabled {
    opacity: 0.5;
    cursor: default;
  }
  .warn,
  .err {
    margin: 0;
    font-size: 13px;
  }
  .warn {
    color: #fbbf24;
  }
  .err {
    color: #f87171;
  }
</style>
