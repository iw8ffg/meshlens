<script lang="ts">
  import { onMount } from 'svelte'
  import { MQTT_CONV, groupMessages, localNodeIds } from '../lib/chat'
  import { buildConversations, convLabel, previewText } from '../lib/conversations'
  import { app, attachChat, rememberConv, setOpenChat } from '../lib/stores.svelte'
  import { setActiveConv, unread } from '../lib/unread.svelte'
  import ConversationList from './chat/ConversationList.svelte'
  import Thread from './chat/Thread.svelte'
  import Composer from './chat/Composer.svelte'
  import { t } from '../lib/i18n/index.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import type { Message } from '../lib/types'

  let {
    now,
    onpick,
    expanded = false,
    canExpand = false,
    ontoggleexpand = () => {},
  }: {
    now: number
    onpick: (id: string) => void
    /** Pagina intera (desktop): elenco e conversazione affiancati */
    expanded?: boolean
    /** Pulsante Espandi/Riduci (solo desktop) */
    canExpand?: boolean
    ontoggleexpand?: () => void
  } = $props()

  let conv = $state<string>(MQTT_CONV)
  // Elenco delle conversazioni o conversazione aperta (uguale su telefono e desktop)
  let view = $state<'list' | 'thread'>('list')
  let replyTo = $state<Message | null>(null)
  let composer = $state<ReturnType<typeof Composer> | null>(null)

  function open(key: string) {
    if (key !== conv) replyTo = null
    conv = key
    view = 'thread'
    setOpenChat(key)
    setActiveConv(key)
    rememberConv(key)
  }

  function back() {
    view = 'list'
    setOpenChat(null)
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

{#snippet expandButton()}
  {#if canExpand}
    <Button
      kind="ghost"
      iconOnly
      icon={expanded ? 'collapse' : 'expand'}
      label={expanded ? t('chat.collapse') : t('chat.expand')}
      title={expanded ? t('chat.collapse') : t('chat.expand')}
      aria-pressed={expanded}
      onclick={ontoggleexpand}
    />
  {/if}
{/snippet}

{#snippet thread(wide: boolean)}
  <Thread {conv} {msgs} {now} {onpick} {wide} onback={back} onreply={(m) => (replyTo = m)} onreact={(m, e) => composer?.react(m, e)} actions={wide ? undefined : expandButton} />
  <Composer bind:this={composer} {conv} {replyTo} oncancelreply={() => (replyTo = null)} onsent={() => (replyTo = null)} />
{/snippet}

<div class="chat" class:wide={expanded}>
  {#if expanded}
    <div class="side">
      <ConversationList {items} active={view === 'thread' ? conv : ''} onopen={open} {now} {groups} actions={expandButton} />
    </div>
    <div class="main">
      {#if view === 'thread'}
        {@render thread(true)}
      {:else}
        <Empty icon="chat" title={t('chat.pickConversation')} />
      {/if}
    </div>
  {:else if view === 'list'}
    <ConversationList {items} active={conv} onopen={open} {now} {groups} actions={expandButton} />
  {:else}
    {@render thread(false)}
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
  .chat.wide {
    flex-direction: row;
  }
  .side {
    width: 340px;
    flex: none;
    display: flex;
    flex-direction: column;
    min-height: 0;
    border-right: 1px solid var(--line-strong);
  }
  .main {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    min-height: 0;
  }
  /* Su schermi larghi la conversazione non si stira oltre una riga leggibile */
  .wide .main :global(.thread),
  .wide .main :global(form.composer) {
    width: 100%;
    max-width: 980px;
    margin: 0 auto;
  }
</style>
