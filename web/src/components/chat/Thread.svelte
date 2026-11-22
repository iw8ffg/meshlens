<script lang="ts">
  import { onMount, tick } from 'svelte'
  import { getJSON } from '../../lib/api'
  import { ago, formatDate } from '../../lib/format'
  import { MQTT_CONV, localNodeIds, splitKey, statusIcon } from '../../lib/chat'
  import { convLabel } from '../../lib/conversations'
  import { statusAria } from '../../lib/send'
  import { keyChangedRecently, routingErrorText, threadItems } from '../../lib/reactions'
  import { app, addRadioHistory } from '../../lib/stores.svelte'
  import { markRead } from '../../lib/unread.svelte'
  import { t } from '../../lib/i18n/index.svelte'
  import Badge from '../../lib/ui/Badge.svelte'
  import BrokerBadge from '../../lib/ui/BrokerBadge.svelte'
  import Banner from '../../lib/ui/Banner.svelte'
  import Icon from '../../lib/ui/Icon.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Empty from '../../lib/ui/Empty.svelte'
  import { emptyRadioHint, navigate } from '../../lib/shell/navigate'
  import MessageFeed from '../MessageFeed.svelte'
  import MessageActions from './MessageActions.svelte'
  import MessageQuote from './MessageQuote.svelte'
  import ReactionChips from './ReactionChips.svelte'
  import type { Snippet } from 'svelte'
  import type { Message } from '../../lib/types'

  let {
    conv,
    msgs,
    now,
    onpick,
    onback,
    onreply,
    onreact,
    wide = false,
    actions,
  }: {
    conv: string
    msgs: Message[]
    now: number
    onpick: (id: string) => void
    onback: () => void
    onreply: (m: Message) => void
    onreact: (m: Message, emoji: string) => void
    /** Pagina espansa: l'elenco è già a sinistra, niente «indietro» */
    wide?: boolean
    /** Pulsanti a destra del titolo (es. Espandi) */
    actions?: Snippet
  } = $props()

  const PAGE = 200

  let listEl = $state<HTMLElement | null>(null)
  let nearBottom = true
  let loadingOlder = $state(false)
  let exhausted = $state(false)
  let olderError = $state(false)

  const nodeName = (id: string) => app.nodes.get(id)?.long_name || app.nodes.get(id)?.short_name || id
  const title = $derived(convLabel(conv, app.radios, nodeName))
  const isRadioConv = $derived(conv !== MQTT_CONV)
  const items = $derived(threadItems(msgs, nodeName, localNodeIds(app.radios)))
  // Avviso di chiave cambiata nei messaggi diretti
  const dmNode = $derived(conv.startsWith('dm:') ? app.nodes.get(splitKey(conv)[2]) : undefined)
  const keyChanged = $derived(dmNode && keyChangedRecently(dmNode, now) ? dmNode : null)

  function jumpTo(key: string) {
    const el = [...(listEl?.querySelectorAll<HTMLElement>('[data-mkey]') ?? [])].find((e) => e.dataset.mkey === key)
    el?.scrollIntoView({ block: 'center' })
  }

  async function loadOlder() {
    const oldest = app.radioMessages.length ? app.radioMessages[0].time : Math.floor(Date.now() / 1000)
    loadingOlder = true
    olderError = false
    try {
      const list = await getJSON<Message[]>(`/messages/radio?limit=${PAGE}&before=${oldest}`)
      if (list.length < PAGE) exhausted = true
      addRadioHistory(list)
    } catch {
      olderError = true
    } finally {
      loadingOlder = false
    }
  }

  // Scorre in fondo quando arrivano messaggi nuovi; sempre al cambio di conversazione o dopo un proprio invio
  let scrollConv = ''
  let scrollLast = ''
  $effect(() => {
    const c = conv
    const last = msgs.length ? msgs[msgs.length - 1] : null
    const lastKey = last?.key ?? ''
    const force = c !== scrollConv || (lastKey !== scrollLast && last?.direction === 'out')
    scrollConv = c
    scrollLast = lastKey
    tick().then(() => {
      if (listEl && (nearBottom || force)) listEl.scrollTo({ top: listEl.scrollHeight })
    })
  })

  // Visibilita' della pagina (per segnare letto solo quando la conversazione si vede davvero)
  let visible = $state(typeof document === 'undefined' || document.visibilityState === 'visible')
  onMount(() => {
    const onvis = () => (visible = document.visibilityState === 'visible')
    document.addEventListener('visibilitychange', onvis)
    return () => document.removeEventListener('visibilitychange', onvis)
  })

  // Segna letto: dipendenze $state lette prima dei controlli; `unread` non si legge qui
  let markedConv = ''
  let lastMarked = 0
  $effect(() => {
    const c = conv
    const newest = msgs.length ? msgs[msgs.length - 1].time : 0
    const v = visible
    if (c !== markedConv) {
      markedConv = c
      lastMarked = 0
    }
    if (c === MQTT_CONV || !v || newest <= lastMarked) return
    lastMarked = newest
    void markRead(c, newest)
  })
</script>

<div class="thread">
  <header class="head">
    {#if !wide}
      <button type="button" class="back" onclick={onback}>
        <span aria-hidden="true">‹</span>
        <span>{t('chat.conversations')}</span>
      </button>
    {/if}
    <h2 class="title">{title}</h2>
    {#if actions}<span class="actions">{@render actions()}</span>{/if}
  </header>

  {#if keyChanged}
    <div class="keywarn">
      <Banner kind="warn" title={t('chat.keyChangedBanner', { name: nodeName(keyChanged.id), date: formatDate(keyChanged.key_changed ?? null) })} />
    </div>
  {/if}

  {#if !isRadioConv}
    <div class="feed"><MessageFeed {now} {onpick} {onreply} {onreact} /></div>
  {:else}
    <ul
      class="list"
      bind:this={listEl}
      onscroll={() => (nearBottom = !!listEl && listEl.scrollHeight - listEl.scrollTop - listEl.clientHeight < 60)}
    >
      {#if !exhausted}
        <li class="older">
          <Button onclick={loadOlder} disabled={loadingOlder}>{loadingOlder ? t('shell.loading') : t('chat.loadOlder')}</Button>
        </li>
      {/if}
      {#if olderError}<li role="alert"><Banner kind="danger" title={t('chat.olderError')} /></li>{/if}
      {#if msgs.length === 0}
        {@const hint = emptyRadioHint(app.radios.filter((r) => r.state === 'connected').length)}
        <li>
          <Empty icon="chat" title={hint.title}>
            {hint.text}
            {#snippet action()}
              {#if hint.action}{@const a = hint.action}<Button onclick={() => navigate(a.tab)}>{a.label}</Button>{/if}
            {/snippet}
          </Empty>
        </li>
      {/if}
      {#each items as it (it.msg.key)}
        {@const m = it.msg}
        {@const out = m.direction === 'out'}
        {#if it.orphan}
          <li class="orphan">{t('chat.orphanReaction', { emoji: m.text, name: out ? t('chat.you') : (m.from_name ?? nodeName(m.from)) })}</li>
        {:else}
          <li class="msg" class:out data-mkey={m.key}>
            <div class="bubble">
              {#if !out}
                <button type="button" class="name" onclick={() => onpick(m.from)}>{m.from_name ?? nodeName(m.from)}</button>
              {/if}
              <MessageQuote replyTo={it.replyTo} missing={it.replyMissing} {nodeName} onjump={jumpTo} />
              <p class="text">{m.text}</p>
              <div class="meta">
                {#if m.pki}<Icon name="lock" size={14} label={t('chat.pkiAria')} />{/if}
                <span>{ago((now - m.time) / 60)}</span>
                {#if m.via === 'mqtt'}<Badge kind="info">{t('chat.status.viaMqtt')}</Badge>{/if}
                <BrokerBadge id={m.broker} />
                {#if out && m.status}
                  <span class="st" class:bad={m.status === 'failed'} role="img" title={statusAria(m.status, m.via)} aria-label={statusAria(m.status, m.via)}>
                    {statusIcon(m.status)}
                  </span>
                {/if}
                <MessageActions msg={m} {onreply} {onreact} />
              </div>
            </div>
            <ReactionChips reactions={it.reactions} />
            {#if m.status === 'failed'}<p class="fail" role="status">{routingErrorText(m.error)}</p>{/if}
          </li>
        {/if}
      {/each}
    </ul>
  {/if}
</div>

<style>
  .thread {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--line);
    flex: none;
    min-width: 0;
  }
  .back {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
    min-height: var(--touch-min);
    padding: 0 var(--space-2);
    background: none;
    border: 0;
    border-radius: var(--radius-md);
    color: var(--accent-ink);
    font: 600 14px/20px var(--font-sans);
    cursor: pointer;
    flex: none;
  }
  .back span[aria-hidden='true'] {
    font-size: 20px;
  }
  .back:hover {
    background: var(--surface-sunken);
  }
  .back:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .actions {
    margin-left: auto;
    flex: none;
  }
  .title {
    margin: 0;
    font: 600 15px/20px var(--font-sans);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    min-width: 0;
  }
  .feed {
    flex: 1;
    overflow: auto;
    min-height: 120px;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: var(--space-3);
    flex: 1;
    overflow: auto;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    min-height: 120px;
  }
  .msg {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
  }
  .msg.out {
    align-items: flex-end;
  }
  .keywarn {
    flex: none;
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--line);
  }
  .orphan {
    align-self: center;
    color: var(--ink-muted);
    font: 400 13px/18px var(--font-sans);
    text-align: center;
  }
  .fail {
    margin: var(--space-1) 0 0;
    max-width: 85%;
    color: var(--danger);
    font: 400 13px/18px var(--font-sans);
    text-align: right;
  }
  .bubble {
    max-width: 85%;
    background: var(--surface-raised);
    border: 1px solid var(--line);
    border-radius: var(--radius-lg);
    padding: var(--space-2) var(--space-3);
  }
  .out .bubble {
    background: var(--accent);
    border-color: var(--accent);
    color: var(--on-accent);
  }
  .name {
    background: none;
    border: 0;
    padding: 0;
    min-height: 24px;
    color: var(--accent-ink);
    font: 600 13px/20px var(--font-sans);
    cursor: pointer;
  }
  .text {
    margin: 2px 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
  }
  .meta {
    display: flex;
    gap: var(--space-2);
    align-items: center;
    justify-content: flex-end;
    font-size: 12px;
    color: var(--ink-muted);
  }
  .out .meta {
    color: var(--on-accent);
  }
  .st {
    min-width: 20px;
    text-align: right;
  }
  .st.bad {
    font-weight: 700;
  }
  .older {
    text-align: center;
  }
  :global(.vp-phone) .name,
  :global(.vp-phone) .meta,
  :global(.vp-phone) .orphan,
  :global(.vp-phone) .fail {
    font-size: 14px;
  }
  :global(.vp-phone) .title {
    font-size: 16px;
  }
</style>
