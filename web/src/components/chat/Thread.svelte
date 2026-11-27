<script lang="ts">
  import { onMount, tick } from 'svelte'
  import { getJSON } from '../../lib/api'
  import { ago, formatDate } from '../../lib/format'
  import { isMqttConv, localNodeIds, mqttConvBroker, olderPage, splitKey, statusIcon } from '../../lib/chat'
  import { convLabel } from '../../lib/conversations'
  import { mqttDelivery, mqttFailText, statusAria } from '../../lib/send'
  import AcceptKey from '../../lib/shell/AcceptKey.svelte'
  import { keyChangedRecently, routingErrorText, threadItems } from '../../lib/reactions'
  import { app, addRadioHistory } from '../../lib/stores.svelte'
  import { markRead } from '../../lib/unread.svelte'
  import { peekFocus, takeFocus } from '../../lib/msgfocus'
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
    focusTick = 0,
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
    /** Cresce a ogni apertura di una conversazione da fuori: rilancia il salto al messaggio cercato */
    focusTick?: number
  } = $props()

  const PAGE = 200

  let listEl = $state<HTMLElement | null>(null)
  let nearBottom = true
  let loadingOlder = $state(false)
  let exhausted = $state(false)
  let cursor: number | null = null
  let olderError = $state(false)

  const nodeName = (id: string) => app.nodes.get(id)?.long_name || app.nodes.get(id)?.short_name || id
  const title = $derived(convLabel(conv, app.radios, nodeName, (app.status?.mqtt.brokers ?? []).filter((b) => b.enabled)))
  const isRadioConv = $derived(!isMqttConv(conv))
  const items = $derived(threadItems(msgs, nodeName, localNodeIds(app.radios)))
  // Avviso di chiave cambiata nei messaggi diretti
  const dmNode = $derived(conv.startsWith('dm:') ? app.nodes.get(splitKey(conv)[2]) : undefined)
  const keyChanged = $derived(dmNode && keyChangedRecently(dmNode, now) ? dmNode : null)

  function jumpTo(key: string) {
    const el = [...(listEl?.querySelectorAll<HTMLElement>('[data-mkey]') ?? [])].find((e) => e.dataset.mkey === key)
    el?.scrollIntoView({ block: 'center' })
  }

  async function loadOlder() {
    const before = cursor ?? (app.radioMessages.length ? app.radioMessages[0].time : Math.floor(Date.now() / 1000))
    loadingOlder = true
    olderError = false
    try {
      // il server include `before`: una pagina piena tutta gia' nota (stesso secondo) si ripete
      // da un secondo prima, cosi' la paginazione avanza sempre
      const known = new Set(app.radioMessages.map((m) => m.key))
      let list = await getJSON<Message[]>(`/messages/radio?limit=${PAGE}&before=${before}`)
      if (list.length >= PAGE && list.every((m) => known.has(m.key))) {
        list = await getJSON<Message[]>(`/messages/radio?limit=${PAGE}&before=${before - 1}`)
      }
      const page = olderPage(list, known, PAGE)
      if (page.exhausted) exhausted = true
      if (page.oldest !== null) cursor = page.oldest
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

  // Salto a un messaggio trovato dalla ricerca: se non e' ancora in elenco si ritenta (al piu' 3 volte), poi si scarta
  let threadEl = $state<HTMLElement | null>(null)
  let focusing: string | null = null
  const FOCUS_DELAYS = [0, 300, 900]
  function findMsg(key: string): HTMLElement | undefined {
    return [...(threadEl?.querySelectorAll<HTMLElement>('[data-mkey]') ?? [])].find((e) => e.dataset.mkey === key)
  }
  function tryFocus(key: string, attempt: number) {
    if (peekFocus() !== key) return
    const el = findMsg(key)
    if (el) {
      takeFocus()
      focusing = null
      el.scrollIntoView({ block: 'center' })
      el.classList.add('mk-hit')
      setTimeout(() => el.classList.remove('mk-hit'), 2600)
    } else if (attempt + 1 >= FOCUS_DELAYS.length) {
      takeFocus()
      focusing = null
    } else {
      setTimeout(() => tryFocus(key, attempt + 1), FOCUS_DELAYS[attempt + 1])
    }
  }
  $effect(() => {
    void conv
    void msgs.length
    void focusTick
    const key = peekFocus()
    if (!key || focusing === key) return
    focusing = key
    tick().then(() => tryFocus(key, 0))
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
    if (isMqttConv(c) || !v || newest <= lastMarked) return
    lastMarked = newest
    void markRead(c, newest)
  })
</script>

<div class="thread" bind:this={threadEl}>
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
      <Banner kind="warn" title={t('chat.keyChangedBanner', { name: nodeName(keyChanged.id), date: formatDate(keyChanged.key_changed ?? null) })}>
        {#snippet action()}<AcceptKey nodeId={keyChanged.id} />{/snippet}
      </Banner>
    </div>
  {/if}

  {#if !isRadioConv}
    <!-- un broker diverso e' un feed nuovo: si ricarica da capo -->
    {#key conv}<div class="feed"><MessageFeed {now} {onpick} {onreply} {onreact} broker={mqttConvBroker(conv)} /></div>{/key}
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
                {#if out && m.via === 'mqtt'}
                  {@const d = mqttDelivery(m, nodeName, app.radios)}
                  {#if d}<span class="mq {d.tone}" title={d.title}>{d.text}</span>{/if}
                {:else if out && m.status}
                  <span class="st" class:bad={m.status === 'failed'} role="img" title={statusAria(m.status, m.via)} aria-label={statusAria(m.status, m.via)}>
                    {statusIcon(m.status)}
                  </span>
                {/if}
                <MessageActions msg={m} {onreply} {onreact} />
              </div>
            </div>
            <ReactionChips reactions={it.reactions} />
            {#if m.status === 'failed'}<p class="fail" role="status">{m.via === 'mqtt' ? mqttFailText(m.error) : routingErrorText(m.error)}</p>{/if}
          </li>
        {/if}
      {/each}
    </ul>
  {/if}
</div>

<style>
  /* messaggio trovato dalla ricerca: evidenziato per qualche secondo (senza movimento con prefers-reduced-motion) */
  :global(.mk-hit) {
    animation: mk-hit 2.6s ease-out;
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: var(--radius-md);
  }
  @keyframes mk-hit {
    0%, 60% { background: var(--accent-soft); }
    100% { background: transparent; }
  }
  @media (prefers-reduced-motion: reduce) {
    :global(.mk-hit) { animation: none; background: var(--accent-soft); }
  }
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
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .title {
    flex: 1 1 0;
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
  .mq {
    white-space: nowrap;
    cursor: help;
  }
  .mq.wait {
    font-style: italic;
  }
  .mq.good,
  .mq.bad {
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
  /* telefoni stretti (360 px): il pulsante indietro resta la sola freccia (l'etichetta resta per i lettori di schermo)
     e il titolo si tronca invece di spingere i pulsanti fuori dalla riga */
  @media (max-width: 420px) {
    .back span:not([aria-hidden]) {
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip-path: inset(50%);
      white-space: nowrap;
    }
    .back {
      position: relative;
      min-width: var(--touch-min);
      justify-content: center;
    }
    .head {
      gap: var(--space-1);
      padding-inline: var(--space-2);
    }
  }
</style>
