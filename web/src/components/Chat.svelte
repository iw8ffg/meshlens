<script lang="ts">
  import { onMount } from 'svelte'
  import { MQTT_CONV, groupMessages, localNodeIds } from '../lib/chat'
  import { buildConversations, convLabel, previewText } from '../lib/conversations'
  import { app, attachChat, rememberConv } from '../lib/stores.svelte'
  import { setActiveConv, unread } from '../lib/unread.svelte'
  import ConversationList from './chat/ConversationList.svelte'
  import Thread from './chat/Thread.svelte'
  import Composer from './chat/Composer.svelte'
  import type { Message } from '../lib/types'

  let { now, onpick }: { now: number; onpick: (id: string) => void } = $props()

  let conv = $state<string>(MQTT_CONV)
  // Elenco delle conversazioni o conversazione aperta (uguale su telefono e desktop)
  let view = $state<'list' | 'thread'>('list')
  let replyTo = $state<Message | null>(null)

  function open(key: string) {
    if (key !== conv) replyTo = null
    conv = key
    view = 'thread'
    setActiveConv(key)
    rememberConv(key)
  }

  function back() {
    view = 'list'
    setActiveConv(null)
  }

  onMount(() => {
    // Apertura da fuori (link, «Messaggio diretto», vista ricordata, notifica): callback, nessun effetto
    const chat = attachChat(open)
    if (chat.pending) open(chat.pending)
    return () => {
      chat.detach()
      setActiveConv(null)
    }
  })

  const localIds = $derived(localNodeIds(app.radios))
  const groups = $derived(groupMessages(app.radioMessages, localIds))
  const nodeName = (id: string) => app.nodes.get(id)?.long_name || app.nodes.get(id)?.short_name || id

  const items = $derived(
    buildConversations({
      radios: app.radios,
      groups,
      summaries: unread.summaries,
      counts: unread.counts,
      label: (k) => convLabel(k, app.radios, nodeName),
      previewOf: (m) => previewText(m, nodeName, localIds),
    }),
  )
  const msgs = $derived(groups.get(conv) ?? [])
</script>

<div class="chat">
  {#if view === 'list'}
    <ConversationList {items} active={conv} onopen={open} {now} {groups} />
  {:else}
    <Thread {conv} {msgs} {now} {onpick} onback={back} />
    <Composer {conv} {replyTo} oncancelreply={() => (replyTo = null)} onsent={() => (replyTo = null)} />
  {/if}
</div>

<style>
  .chat {
    display: flex;
    flex-direction: column;
    height: 100%;
    min-height: 0;
    color: var(--ink);
  }
</style>
