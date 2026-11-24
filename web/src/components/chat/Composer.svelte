<script lang="ts">
import { safeStorage } from '../../lib/storage'
  import { onMount, untrack } from 'svelte'
  import { ApiError, getJSON, mqttChannels, mqttSend, send } from '../../lib/api'
  import { brokerLabel, pickBroker } from '../../lib/brokers'
  import { MAX_BYTES, mqttConvBroker, reactionDest, splitKey } from '../../lib/chat'
  import { draftSentUnchanged, loadDraft, saveDraft } from '../../lib/drafts'
  import {
    MQTT_VIA,
    byteCount,
    classifyMqttError,
    publicWarning,
    mqttBody,
    mqttChannelNames,
    pickRadioChannel,
    pickVia,
    resendBody,
    viaOptions,
    viaRadioId,
    DEFAULT_MQTT_CHANNEL,
    type MqttSendBody,
  } from '../../lib/send'
  import { keepAboveKeyboard } from '../../lib/keyboard'
  import { blockingVariables, expandVariables, insertReply, ownNodeId } from '../../lib/quickreplies'
  import { navigate } from '../../lib/shell/navigate'
  import { app, addMessage } from '../../lib/stores.svelte'
  import QuickReplies from './QuickReplies.svelte'
  import { t } from '../../lib/i18n/index.svelte'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Field from '../../lib/ui/Field.svelte'
  import Modal from '../../lib/ui/Modal.svelte'
  import Icon from '../../lib/ui/Icon.svelte'
  import Select from '../../lib/ui/Select.svelte'
  import Toast from '../../lib/ui/Toast.svelte'
  import BrokerPicker from '../../lib/shell/BrokerPicker.svelte'
  import type { Message, Radio } from '../../lib/types'

  let {
    conv,
    replyTo,
    oncancelreply,
    onsent,
  }: { conv: string; replyTo: Message | null; oncancelreply: () => void; onsent: (m: Message) => void } = $props()

  const uid = $props.id()
  let text = $state('')
  let via = $state('')
  let radioChan = $state('0')
  let mqttChan = $state(DEFAULT_MQTT_CHANNEL)
  let mqttChans = $state<string[]>([DEFAULT_MQTT_CHANNEL])
  let mqttBroker = $state('')
  let mqttNodeId = $state('')
  let confirmText = $state('')
  let unknownNode = $state(false)
  let sending = $state(false)
  let error = $state('')
  let notice = $state('')
  let confirmOpen = $state(false)
  let pending = $state<MqttSendBody | null>(null)
  // Conversazione da cui parte l'invio in attesa di conferma (per svuotarne la bozza)
  let pendingConv = ''
  // La reazione non tocca il testo in corso di scrittura
  let pendingClear = true
  interface Reply {
    id: number
    emoji: boolean
  }

  // Id nodo impostato (per sapere in anticipo se MQTT e' utilizzabile)
  onMount(() => {
    let alive = true
    getJSON<{ mqtt_node_id?: string }>('/settings')
      .then((s) => {
        if (alive && typeof s.mqtt_node_id === 'string') mqttNodeId = s.mqtt_node_id
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  })

  // Bozza: si carica al cambio di conversazione (qui) e si salva in `oninput` (non in un effetto)
  // variabili dei messaggi rapidi ancora da risolvere: valgono per la conversazione corrente
  let pendingVars = $state<string[]>([])
  let draftConv: string | null = null
  $effect.pre(() => {
    const c = conv
    if (c === draftConv) return
    draftConv = c
    text = loadDraft(safeStorage(), c)
    pendingVars = []
  })

  const dmTo = $derived(conv.startsWith('dm:') ? splitKey(conv)[2] : '')
  const nodeName = (id: string) => app.nodes.get(id)?.long_name || app.nodes.get(id)?.short_name || id

  // --- Invia via ---
  const brokers = $derived(app.status?.mqtt.brokers ?? [])
  // Server vecchio (senza `brokers`): vale il totale
  const mqttConnected = $derived(brokers.length ? (brokers.find((b) => b.id === mqttBroker)?.connected ?? false) : (app.status?.mqtt.connected ?? false))
  // Conversazione pubblica di un broker: si invia su quel broker (se attivo), senza scelta
  const convBroker = $derived(mqttConvBroker(conv))
  const lockedBroker = $derived(convBroker && brokers.some((b) => b.id === convBroker && b.enabled) ? convBroker : null)
  $effect(() => {
    mqttBroker = lockedBroker ?? pickBroker(untrack(() => mqttBroker), brokers)
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
  // Messaggi rapidi: una variabile non risolta ({batteria} senza dato...) non parte mai come testo
  const unresolved = $derived(blockingVariables(text, pendingVars).map((v) => `{${v}}`))
  const quickMissing = $derived(pendingVars.length > 0)
  let taEl: HTMLTextAreaElement | undefined = $state()
  const canSend = $derived(!sending && !bc.over && text.trim() !== '' && hasChoice && via !== '' && unresolved.length === 0)

  /** Inserisce un messaggio rapido nel campo (variabili espanse); non invia nulla. */
  function pickQuick(reply: string) {
    const id = ownNodeId(via, app.radios, mqttNodeId)
    const r = expandVariables(reply, { node: (id ? app.nodes.get(id) : null) ?? null, now: new Date() })
    text = insertReply(text, r.text)
    pendingVars = [...new Set([...pendingVars, ...r.missing])]
    saveDraft(safeStorage(), conv, text)
    taEl?.focus()
  }

  /** Invio riuscito: svuota il testo (se la conversazione e' ancora quella) e la sua bozza. */
  function sent(m: Message, from: string, clear: boolean, sentText: string) {
    addMessage(m)
    if (clear) {
      pendingVars = []
      // se nel frattempo si e' scritto altro, il testo (e la bozza) restano
      const current = conv === from ? text : loadDraft(safeStorage(), from)
      if (draftSentUnchanged(current, sentText)) {
        if (conv === from) text = ''
        saveDraft(safeStorage(), from, '')
      }
      onsent(m)
    }
  }

  async function sendRadio(from: string, body: string, reply: Reply | null) {
    const m = await send<Message>('POST', `/radios/${encodeURIComponent(radioId)}/send`, {
      text: body.trim(),
      channel_index: dmTo ? 0 : Number(radioChan),
      to: dmTo || null,
      ...(reply ? { reply_id: reply.id, ...(reply.emoji ? { emoji: true } : {}) } : {}),
    })
    sent(m, from, !reply?.emoji, body)
    // il messaggio non compare nella conversazione aperta: lo si conferma con un avviso
    const inConv = dmTo ? splitKey(conv)[1] === radioId : conv === `ch:${radioId}:${radioChan}`
    if (!inConv) {
      const ch = viaRadio?.channels.find((c) => String(c.index) === radioChan)
      notice = t('chat.sentRadio', { to: dmTo ? t('chat.dmShort', { name: nodeName(dmTo) }) : ch?.name || t('chat.channelFallback', { index: radioChan }) })
    }
  }

  async function sendMqtt(body: MqttSendBody, from: string, clear = true) {
    try {
      const r = await mqttSend(body)
      sent(r.message, from, clear, body.text)
      const bn = brokerLabel(body.broker, brokers)
      notice = t('chat.sentMqtt', { to: `${bn ? `${bn} · ` : ''}${body.channel}` })
    } catch (e) {
      const info = classifyMqttError(
        e instanceof ApiError ? { status: e.status, code: e.code, message: e.message, retryAfter: e.retryAfter } : { status: 0, code: null, message: '' },
      )
      if (info.kind === 'confirm') {
        confirmText = info.message
        pending = body
        pendingConv = from
        pendingClear = clear
        confirmOpen = true
        return
      }
      if (info.kind === 'unknown_node') unknownNode = true
      error = info.message
    }
  }

  async function submit() {
    if (!canSend) return
    const from = conv
    sending = true
    error = ''
    notice = ''
    try {
      const rid = replyTo?.packet_id ?? null
      if (via === MQTT_VIA) await sendMqtt(mqttBody(text, mqttChan, dmTo || null, false, mqttBroker, rid), from)
      else await sendRadio(from, text, rid ? { id: rid, emoji: false } : null)
    } catch (e) {
      error = e instanceof Error && e.message ? e.message : t('chat.send.failed')
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
      await sendMqtt(resendBody(body), pendingConv, pendingClear)
    } finally {
      sending = false
    }
  }

  function cancelPublic() {
    confirmOpen = false
    pending = null
  }

  /** Reazione a un messaggio: parte subito, con lo stesso «Invia via» (e la stessa conferma MQTT) del compositore. */
  export async function react(target: Message, emoji: string) {
    const rid = target.packet_id
    if (!rid || sending) return
    if (!hasChoice || via === '') {
      error = t('chat.reactionNoVia')
      return
    }
    const from = conv
    sending = true
    error = ''
    notice = ''
    try {
      if (via === MQTT_VIA) {
        const ch = target.channel && mqttChans.includes(target.channel) ? target.channel : mqttChan
        await sendMqtt(mqttBody(emoji, ch, reactionDest(target, dmTo || null), false, mqttBroker, rid, true), from, false)
      } else await sendRadio(from, emoji, { id: rid, emoji: true })
    } catch (e) {
      error = e instanceof Error && e.message ? e.message : t('chat.send.failed')
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

  const placeholder = $derived(dmTo ? t('chat.placeholderDm') : via === MQTT_VIA ? t('chat.placeholderMqtt') : t('chat.placeholderChannel'))
</script>

<form class="composer" use:keepAboveKeyboard onsubmit={(e) => (e.preventDefault(), submit())}>
  {#if notice}<Toast kind="ok" onclose={() => (notice = '')}>{notice}</Toast>{/if}
  <fieldset class="via">
    <legend>{t('chat.sendVia')}</legend>
    {#each shownOptions as o (o.value)}
      <label class="opt" class:dis={o.disabled}>
        <input type="radio" name="{uid}-via" value={o.value} bind:group={via} disabled={o.disabled} aria-describedby={o.reason ? `${uid}-why-${o.value}` : undefined} />
        <span class="lbl">{o.label}</span>
        {#if o.reason}<span class="why" id="{uid}-why-{o.value}">{o.reason}</span>{/if}
      </label>
    {/each}
  </fieldset>

  {#if via === MQTT_VIA}
    <!-- nella conversazione di un solo broker il broker e' gia' deciso; il canale si sceglie sempre -->
    {#if !lockedBroker}<BrokerPicker id="{uid}-brk" {brokers} bind:value={mqttBroker} />{/if}
    <Field label={t('chat.mqttChannelLabel')} for="{uid}-mch" hint={dmTo ? t('chat.directTo', { name: nodeName(dmTo) }) : undefined}>
      {#snippet children({ describedby })}
        <Select id="{uid}-mch" bind:value={mqttChan} aria-describedby={describedby}>
          {#each mqttChans as c (c)}<option value={c}>{c}</option>{/each}
        </Select>
      {/snippet}
    </Field>
  {:else if viaRadio}
    {#if dmTo}
      <p class="to">{t('chat.directMessageTo')} <b>{nodeName(dmTo)}</b></p>
    {:else}
      <Field label={t('chat.channel')} for="{uid}-rch">
        {#snippet children({ describedby })}
          <Select id="{uid}-rch" bind:value={radioChan} aria-describedby={describedby}>
            {#each viaRadio.channels as c (c.index)}<option value={String(c.index)}>{c.name || t('chat.channelFallback', { index: c.index })}</option>{/each}
          </Select>
        {/snippet}
      </Field>
    {/if}
  {/if}

  {#if replyTo}
    <div class="reply">
      <span class="rq">
        <b>{t('chat.replyingTo', { name: replyTo.direction === 'out' ? t('chat.you') : (replyTo.from_name ?? nodeName(replyTo.from)) })}</b>
        <span class="rp">{replyTo.text}</span>
      </span>
      <button type="button" class="rx" aria-label={t('chat.cancelReply')} title={t('chat.cancelReply')} onclick={oncancelreply}>
        <Icon name="x" size={16} />
      </button>
    </div>
  {/if}

  <textarea
    class="ui-input ta"
    rows="2"
    aria-label={t('chat.messageLabel')}
    aria-describedby="{uid}-cnt"
    {placeholder}
    bind:value={text}
    bind:this={taEl}
    oninput={(e) => {
      saveDraft(safeStorage(), conv, e.currentTarget.value)
      if (e.currentTarget.value === '') pendingVars = []
    }}
    onkeydown={onkey}
    disabled={!hasChoice}
  ></textarea>
  {#if unresolved.length}
    <p class="unres" role="status">{quickMissing ? t('chat.quick.missing', { names: unresolved.join(', ') }) : t('chat.quick.unresolved', { names: unresolved.join(', ') })}</p>
  {/if}
  <div class="row">
    <div class="lf">
      <QuickReplies disabled={!hasChoice} onpick={pickQuick} onmanage={() => navigate('settings')} />
      <span class="count ui-mono" class:over={bc.over} id="{uid}-cnt">{bc.bytes}/{MAX_BYTES} {t('chat.bytes')}{bc.over ? ` — ${t('chat.tooLong')}` : ''}</span>
    </div>
    <Button type="submit" kind="primary" icon="send" disabled={!canSend} title={t('chat.sendShortcut')}>{sending ? t('chat.sending') : t('chat.send')}</Button>
  </div>
  {#if error}<Banner kind="danger" title={error} />{/if}
</form>

<Modal open={confirmOpen} title={t('chat.publishTitle')} confirmLabel={t('chat.publish')} oncancel={cancelPublic} onconfirm={confirmPublic}>
  <p class="warn">{confirmText || publicWarning()}</p>
</Modal>

<style>
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
  .lf {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .unres {
    margin: 0;
    font: 400 14px/20px var(--font-sans);
    color: var(--warn);
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
  .reply {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-1) var(--space-2);
    background: var(--surface-sunken);
    border-left: 3px solid var(--accent);
    border-radius: var(--radius-sm);
    font-size: 14px;
    min-width: 0;
  }
  .rq {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
  }
  .rp {
    color: var(--ink-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .rx {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    flex: none;
    min-width: 32px;
    min-height: 32px;
    background: none;
    border: 0;
    border-radius: var(--radius-md);
    color: var(--ink);
    cursor: pointer;
  }
  .rx:hover {
    background: var(--accent-soft);
  }
  .rx:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  :global(.vp-phone) .rx {
    min-width: var(--touch-min);
    min-height: var(--touch-min);
  }
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
