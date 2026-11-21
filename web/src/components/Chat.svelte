<script lang="ts">
  import { onMount, tick, untrack } from 'svelte'
  import { ApiError, getJSON, mqttChannels, mqttSend, send } from '../lib/api'
  import { ago } from '../lib/format'
  import { brokerLabel, pickBroker } from '../lib/brokers'
  import { MAX_BYTES, MQTT_CONV, groupMessages, localNodeIds, splitKey, statusIcon } from '../lib/chat'
  import {
    MQTT_VIA,
    PUBLIC_WARNING,
    byteCount,
    classifyMqttError,
    mqttBody,
    mqttChannelNames,
    pickRadioChannel,
    pickVia,
    resendBody,
    statusAria,
    viaOptions,
    viaRadioId,
    DEFAULT_MQTT_CHANNEL,
    type MqttSendBody,
  } from '../lib/send'
  import { keepAboveKeyboard } from '../lib/keyboard'
  import { app, addMessage, addRadioHistory, attachChat, rememberConv } from '../lib/stores.svelte'
  import Badge from '../lib/ui/Badge.svelte'
  import BrokerBadge from '../lib/ui/BrokerBadge.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import { emptyRadioHint, navigate } from '../lib/shell/navigate'
  import Field from '../lib/ui/Field.svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import Select from '../lib/ui/Select.svelte'
  import Toast from '../lib/ui/Toast.svelte'
  import BrokerPicker from '../lib/shell/BrokerPicker.svelte'
  import MessageFeed from './MessageFeed.svelte'
  import type { Message, Radio } from '../lib/types'

  let { now, onpick }: { now: number; onpick: (id: string) => void } = $props()

  const uid = $props.id()
  let conv = $state<string>(MQTT_CONV)
  let text = $state('')
  let via = $state('')
  let radioChan = $state('0')
  let mqttChan = $state(DEFAULT_MQTT_CHANNEL)
  let mqttChans = $state<string[]>([DEFAULT_MQTT_CHANNEL])
  let mqttBroker = $state('')
  let mqttNodeId = $state('')
  let confirmText = $state(PUBLIC_WARNING)
  let unknownNode = $state(false)
  let sending = $state(false)
  let error = $state('')
  let notice = $state('')
  let confirmOpen = $state(false)
  let pending = $state<MqttSendBody | null>(null)
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

  // Canali MQTT per l'invio e id nodo impostato (per sapere in anticipo se MQTT e' utilizzabile)
  onMount(() => {
    let alive = true
    getJSON<{ mqtt_node_id?: string }>('/settings')
      .then((s) => {
        if (alive && typeof s.mqtt_node_id === 'string') mqttNodeId = s.mqtt_node_id
      })
      .catch(() => {})
    // Apertura da fuori (es. "Messaggio diretto" nel dettaglio nodo): callback, nessun effetto
    const chat = attachChat((key) => {
      conv = key
    })
    if (chat.pending) conv = chat.pending
    return () => {
      alive = false
      chat.detach()
    }
  })
  $effect(() => rememberConv(conv))

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

  const convOptions = $derived.by(() => {
    const keys: string[] = [MQTT_CONV]
    for (const r of app.radios) for (const c of r.channels) keys.push(`ch:${r.id}:${c.index}`)
    for (const k of groups.keys()) if (!keys.includes(k)) keys.push(k)
    if (!keys.includes(conv)) keys.push(conv)
    return keys.map((k) => ({ key: k, label: label(k) }))
  })

  const isRadioConv = $derived(conv !== MQTT_CONV)
  const msgs = $derived(groups.get(conv) ?? [])
  const dmTo = $derived(conv.startsWith('dm:') ? splitKey(conv)[2] : '')

  // --- Invia via ---
  const brokers = $derived(app.status?.mqtt.brokers ?? [])
  // Server vecchio (senza `brokers`): vale il totale
  const mqttConnected = $derived(brokers.length ? (brokers.find((b) => b.id === mqttBroker)?.connected ?? false) : (app.status?.mqtt.connected ?? false))
  $effect(() => {
    mqttBroker = pickBroker(untrack(() => mqttBroker), brokers)
  })
  // Canali MQTT del broker scelto (anche i personalizzati senza traffico)
  $effect(() => {
    let alive = true
    mqttChans = [DEFAULT_MQTT_CHANNEL]
    mqttChannels(mqttBroker)
      .then((rows) => {
        if (alive) mqttChans = mqttChannelNames(rows)
      })
      .catch(() => {
        if (alive) mqttChans = [DEFAULT_MQTT_CHANNEL]
      })
    return () => {
      alive = false
    }
  })
  // Se il canale scelto non esiste nel broker corrente si torna al primo
  $effect(() => {
    if (!mqttChans.includes(untrack(() => mqttChan))) mqttChan = mqttChans[0] ?? DEFAULT_MQTT_CHANNEL
  })
  const options = $derived(viaOptions({ radios: app.radios, mqttConnected, mqttNodeId, unknownNode }))
  // Etichette con i nomi dei canali (solo visualizzazione: la scelta usa `options`, senza dipendere dal canale)
  const chanName = (r: Radio): string | undefined => {
    const idx = r.id === radioId ? (dmTo ? 0 : Number(radioChan)) : pickRadioChannel(conv, app.radios, r.id, 0, true)
    return r.channels.find((c) => c.index === idx)?.name || undefined
  }
  const shownOptions = $derived(
    viaOptions({ radios: app.radios, mqttConnected, mqttNodeId, unknownNode, radioChannelName: chanName, mqttChannel: mqttChan }),
  )
  const radioId = $derived(viaRadioId(via))
  const viaRadio = $derived(app.radios.find((r) => r.id === radioId) ?? null)
  const hasChoice = $derived(options.some((o) => !o.disabled))

  // Se le radio collegate o l'id nodo cambiano, un vecchio "nodo sconosciuto" non vale piu'
  const identityKey = $derived(app.radios.map((r) => `${r.id}:${r.state}:${r.my_node_id ?? ''}`).join('|') + `#${mqttNodeId}`)
  $effect(() => {
    void identityKey
    unknownNode = false
  })

  // Scelta di "Invia via": la scelta manuale persiste finche' e' disponibile (vedi pickVia)
  let lastConv = ''
  $effect(() => {
    const changed = conv !== lastConv
    lastConv = conv
    via = pickVia(untrack(() => via), conv, options, changed)
  })

  // Canale della radio scelta
  let lastSel = ''
  $effect(() => {
    const sel = `${conv}|${radioId}`
    const changed = sel !== lastSel
    lastSel = sel
    radioChan = String(pickRadioChannel(conv, app.radios, radioId, Number(untrack(() => radioChan)), changed))
  })

  const bc = $derived(byteCount(text))
  const canSend = $derived(!sending && !bc.over && text.trim() !== '' && hasChoice && via !== '')

  async function sendRadio() {
    const m = await send<Message>('POST', `/radios/${encodeURIComponent(radioId)}/send`, {
      text: text.trim(),
      channel_index: dmTo ? 0 : Number(radioChan),
      to: dmTo || null,
    })
    forceScroll = true
    addMessage(m)
    text = ''
    // il messaggio non compare nella conversazione aperta: lo si conferma con un avviso
    const inConv = dmTo ? splitKey(conv)[1] === radioId : conv === `ch:${radioId}:${radioChan}`
    if (!inConv) {
      const ch = viaRadio?.channels.find((c) => String(c.index) === radioChan)
      notice = `Inviato via radio · ${dmTo ? `DM ${nodeName(dmTo)}` : ch?.name || `Canale ${radioChan}`}`
    }
  }

  async function sendMqtt(body: MqttSendBody) {
    try {
      const r = await mqttSend(body)
      forceScroll = true
      addMessage(r.message)
      text = ''
      const bn = brokerLabel(body.broker, brokers)
      notice = `Pubblicato su MQTT · ${bn ? `${bn} · ` : ''}${body.channel}`
    } catch (e) {
      const info = classifyMqttError(
        e instanceof ApiError ? { status: e.status, code: e.code, message: e.message, retryAfter: e.retryAfter } : { status: 0, code: null, message: '' },
      )
      if (info.kind === 'confirm') {
        confirmText = info.message
        pending = body
        confirmOpen = true
        return
      }
      if (info.kind === 'unknown_node') unknownNode = true
      error = info.message
    }
  }

  async function submit() {
    if (!canSend) return
    sending = true
    error = ''
    notice = ''
    try {
      if (via === MQTT_VIA) await sendMqtt(mqttBody(text, mqttChan, dmTo || null, false, mqttBroker))
      else await sendRadio()
    } catch (e) {
      error = e instanceof Error && e.message ? e.message : 'Invio non riuscito'
    } finally {
      sending = false
    }
  }

  async function confirmPublic() {
    const body = pending
    confirmOpen = false
    pending = null
    if (!body) return
    sending = true
    error = ''
    try {
      await sendMqtt(resendBody(body))
    } finally {
      sending = false
    }
  }

  function cancelPublic() {
    confirmOpen = false
    pending = null
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

  const placeholder = $derived(dmTo ? 'Messaggio diretto…' : via === MQTT_VIA ? 'Messaggio pubblico su MQTT…' : 'Messaggio sul canale…')
</script>

<div class="chat">
  <div class="bar">
    <Field label="Conversazione" for="{uid}-conv">
      {#snippet children({ describedby })}
        <Select id="{uid}-conv" bind:value={conv} aria-describedby={describedby}>
          {#each convOptions as o (o.key)}
            <option value={o.key}>{o.label}</option>
          {/each}
        </Select>
      {/snippet}
    </Field>
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
          <Button onclick={loadOlder} disabled={loadingOlder}>{loadingOlder ? 'Caricamento…' : 'Carica precedenti'}</Button>
        </li>
      {/if}
      {#if olderError}<li role="alert"><Banner kind="danger" title={olderError} /></li>{/if}
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
      {#each msgs as m (m.key)}
        {@const out = m.direction === 'out'}
        <li class="msg" class:out>
          <div class="bubble">
            {#if !out}
              <button type="button" class="name" onclick={() => onpick(m.from)}>{m.from_name ?? nodeName(m.from)}</button>
            {/if}
            <p class="text">{m.text}</p>
            <div class="meta">
              <span>{ago((now - m.time) / 60)}</span>
              {#if m.via === 'mqtt'}<Badge kind="info">via MQTT</Badge>{/if}
              <BrokerBadge id={m.broker} />
              {#if out && m.status}
                <span class="st" class:bad={m.status === 'failed'} role="img" title={statusAria(m.status, m.via)} aria-label={statusAria(m.status, m.via)}>
                  {statusIcon(m.status)}
                </span>
              {/if}
            </div>
          </div>
        </li>
      {/each}
    </ul>
  {/if}

  <form class="composer" use:keepAboveKeyboard onsubmit={(e) => (e.preventDefault(), submit())}>
    {#if notice}<Toast kind="ok" onclose={() => (notice = '')}>{notice}</Toast>{/if}
    <fieldset class="via">
      <legend>Invia via</legend>
      {#each shownOptions as o (o.value)}
        <label class="opt" class:dis={o.disabled}>
          <input type="radio" name="{uid}-via" value={o.value} bind:group={via} disabled={o.disabled} aria-describedby={o.reason ? `${uid}-why-${o.value}` : undefined} />
          <span class="lbl">{o.label}</span>
          {#if o.reason}<span class="why" id="{uid}-why-{o.value}">{o.reason}</span>{/if}
        </label>
      {/each}
    </fieldset>

    {#if via === MQTT_VIA}
      <BrokerPicker id="{uid}-brk" {brokers} bind:value={mqttBroker} />
      <Field label="Canale MQTT" for="{uid}-mch" hint={dmTo ? `Diretto a ${nodeName(dmTo)}` : undefined}>
        {#snippet children({ describedby })}
          <Select id="{uid}-mch" bind:value={mqttChan} aria-describedby={describedby}>
            {#each mqttChans as c (c)}<option value={c}>{c}</option>{/each}
          </Select>
        {/snippet}
      </Field>
    {:else if viaRadio}
      {#if dmTo}
        <p class="to">Messaggio diretto a <b>{nodeName(dmTo)}</b></p>
      {:else}
        <Field label="Canale" for="{uid}-rch">
          {#snippet children({ describedby })}
            <Select id="{uid}-rch" bind:value={radioChan} aria-describedby={describedby}>
              {#each viaRadio.channels as c (c.index)}<option value={String(c.index)}>{c.name || `Canale ${c.index}`}</option>{/each}
            </Select>
          {/snippet}
        </Field>
      {/if}
    {/if}

    <textarea
      class="ui-input ta"
      rows="2"
      aria-label="Messaggio"
      aria-describedby="{uid}-cnt"
      {placeholder}
      bind:value={text}
      onkeydown={onkey}
      disabled={!hasChoice}
    ></textarea>
    <div class="row">
      <span class="count ui-mono" class:over={bc.over} id="{uid}-cnt">{bc.bytes}/{MAX_BYTES} byte{bc.over ? ' — troppo lungo' : ''}</span>
      <Button type="submit" kind="primary" icon="send" disabled={!canSend} title="Ctrl+Invio">{sending ? 'Invio…' : 'Invia'}</Button>
    </div>
    {#if error}<Banner kind="danger" title={error} />{/if}
  </form>
</div>

<Modal open={confirmOpen} title="Pubblicare su MQTT?" confirmLabel="Pubblica" oncancel={cancelPublic} onconfirm={confirmPublic}>
  <p class="warn">{confirmText}</p>
</Modal>

<style>
  .chat {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    color: var(--ink);
  }
  .bar {
    padding: var(--space-3);
    border-bottom: 1px solid var(--line);
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
  }
  .msg.out {
    justify-content: flex-end;
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
  .composer {
    border-top: 1px solid var(--line);
    background: var(--surface);
    padding: var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    position: relative;
    z-index: 1;
    flex: none;
  }
  .via {
    border: 0;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
    min-width: 0;
  }
  .via legend {
    font: 600 13px/16px var(--font-sans);
    color: var(--ink-muted);
    padding: 0;
    margin-bottom: var(--space-1);
  }
  .opt {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: var(--space-1) var(--space-2);
    min-height: var(--touch-min);
    padding: 0 var(--space-3);
    border: 1px solid var(--line-strong);
    border-radius: var(--radius-md);
    background: var(--surface-sunken);
    cursor: pointer;
    font: 500 14px/20px var(--font-sans);
  }
  .opt:has(input:checked) {
    border-color: var(--accent);
    background: var(--accent-soft);
  }
  .opt:has(input:focus-visible) {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .opt input {
    accent-color: var(--accent);
    width: 18px;
    height: 18px;
    margin: 0;
  }
  .opt.dis {
    cursor: not-allowed;
    color: var(--ink-muted);
  }
  .why {
    font: 400 13px/16px var(--font-sans);
    color: var(--warn);
  }
  .to {
    margin: 0;
    font-size: 14px;
  }
  .ta {
    height: auto;
    padding: var(--space-2) var(--space-3);
    resize: vertical;
    min-height: 64px;
  }
  .row {
    display: flex;
    gap: var(--space-3);
    align-items: center;
    justify-content: space-between;
  }
  .count {
    font-size: 13px;
    color: var(--ink-muted);
  }
  .count.over {
    color: var(--danger);
    font-weight: 600;
  }
  .warn {
    margin: 0;
  }
  :global(.vp-phone) .name,
  :global(.vp-phone) .meta,
  :global(.vp-phone) .count,
  :global(.vp-phone) .why,
  :global(.vp-phone) .opt {
    font-size: 14px;
  }
  :global(.vp-phone) .ta {
    font-size: 16px;
  }
  :global(.vp-phone) .opt {
    min-height: 48px;
  }
</style>
