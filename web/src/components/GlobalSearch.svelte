<script lang="ts">
  // Ricerca globale Ctrl+K (WP1, E2): azioni, nodi, conversazioni, impostazioni (istantanei) e testo
  // dei messaggi (dal server, con ritardo). Mai {@html}: gli snippet si rendono a segmenti con <mark>.
  import { untrack } from 'svelte'
  import { isIgnored } from '../lib/filters'
  import { mergeNodeHits, moveActive, rankLocal, searchableConversations, settingsItems } from '../lib/globalsearch'
  import type { NodeLike, SearchResult } from '../lib/globalsearch'
  import { closeGlobalSearch, searchUi, toggleGlobalSearch } from '../lib/globalsearch.svelte'
  import { t } from '../lib/i18n/index.svelte'
  import type { MsgKey } from '../lib/i18n/index.svelte'
  import { isSearchShortcut } from '../lib/keyboard'
  import { requestFocus } from '../lib/msgfocus'
  import { globalSearch, hitConvKey, loadHitContext, snippetParts } from '../lib/msgsearch'
  import type { GlobalSearchResult } from '../lib/msgsearch'
  import { openOnboarding } from '../lib/onboarding.svelte'
  import { formatHash } from '../lib/route'
  import { navigate } from '../lib/shell/navigate'
  import type { Tab } from '../lib/shell/nav'
  import { app, openChat } from '../lib/stores.svelte'
  import { unread } from '../lib/unread.svelte'
  import { viewport } from '../lib/viewport.svelte'
  import type { MessageSearchHit } from '../lib/types'
  import Icon from '../lib/ui/Icon.svelte'

  const uid = $props.id()
  const TABS: Tab[] = ['map', 'nodes', 'network', 'coverage', 'chat', 'radio', 'settings']

  let q = $state('')
  let remote = $state<GlobalSearchResult | null>(null)
  let remoteError = $state(false)
  let activeRaw = $state(0)
  let seq = 0
  let timer: ReturnType<typeof setTimeout> | undefined

  const nodeName = (id: string) => app.nodes.get(id)?.long_name || app.nodes.get(id)?.short_name || id
  const brokers = $derived((app.status?.mqtt.brokers ?? []).filter((b) => b.enabled))

  function openNode(id: string) {
    const target = formatHash({ tab: 'nodes', nodeId: id })
    if (location.hash === target) navigate('nodes')
    else location.hash = target
  }

  function openHit(hit: MessageSearchHit) {
    requestFocus(hit.message.key)
    openChat(hitConvKey(hit))
    navigate('chat')
    void loadHitContext(hit)
  }

  const actions = $derived([
    { id: 'guide', title: t('search.action.guide'), run: () => openOnboarding() },
    ...TABS.map((tab) => ({ id: `goto-${tab}`, title: t('search.action.goto', { tab: t(`nav.${tab}` as MsgKey) }), run: () => navigate(tab) })),
  ])

  const localNodes = $derived<NodeLike[]>([...app.nodes.values()])
  const ignoredIds = $derived(new Set([...app.nodes.values()].filter((n) => isIgnored(n)).map((n) => n.id)))
  const remoteNodes = $derived<NodeLike[]>((remote?.nodes ?? []).map((n) => ({ id: n.id, long_name: n.long_name, short_name: n.short_name, is_ignored: false })))

  const conversations = $derived(
    searchUi.open
      ? searchableConversations({ radios: app.radios, radioMessages: app.radioMessages, summaries: unread.summaries, counts: unread.counts, nodes: app.nodes, brokers })
      : [],
  )

  const local = $derived<SearchResult[]>(
    searchUi.open
      ? rankLocal(
          q,
          { nodes: mergeNodeHits(localNodes, remoteNodes, ignoredIds), conversations, settings: settingsItems((k) => t(k), t('nav.settings')), actions },
          { node: openNode, conversation: (key) => { openChat(key); navigate('chat') }, setting: () => navigate('settings') },
        )
      : [],
  )
  const messages = $derived<SearchResult[]>(
    (remote?.messages ?? []).map((h) => ({
      group: 'message' as const,
      id: h.message.key,
      title: h.message.from_name || nodeName(h.message.from),
      subtitle: h.message.text,
      snippet: h.snippet,
      run: () => openHit(h),
    })),
  )
  const results = $derived([...local, ...messages])
  const active = $derived(results.length ? Math.min(activeRaw, results.length - 1) : -1)
  const GROUPS = ['action', 'node', 'conversation', 'setting', 'message'] as const
  const groupLabel = (g: (typeof GROUPS)[number]) => t(`search.group.${g}` as MsgKey)

  // Messaggi dal server: dopo 250 ms senza digitazione, con 2 o piu' caratteri; le risposte obsolete si scartano
  $effect(() => {
    const query = q.trim()
    const open = searchUi.open
    clearTimeout(timer)
    const mine = ++seq
    if (!open || query.length < 2) {
      untrack(() => {
        remote = null
        remoteError = false
      })
      return
    }
    timer = setTimeout(async () => {
      try {
        const r = await globalSearch(query)
        if (mine !== seq) return
        remote = r
        remoteError = false
      } catch {
        if (mine !== seq) return
        remote = null
        remoteError = true
      }
    }, 250)
    return () => clearTimeout(timer)
  })

  // all'apertura: campo vuoto
  $effect(() => {
    if (searchUi.open)
      untrack(() => {
        q = ''
        activeRaw = 0
        remote = null
        remoteError = false
      })
  })

  function run(i: number) {
    const r = results[i]
    if (!r) return
    closeGlobalSearch()
    r.run()
  }

  function inputKey(e: KeyboardEvent) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault()
      activeRaw = moveActive(active, e.key === 'ArrowDown' ? 1 : -1, results.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      run(active)
    }
  }

  function winKey(e: KeyboardEvent) {
    if (isSearchShortcut(e)) {
      // non si apre sopra un altro dialogo modale (conferme, esportazioni, onboarding)
      if (!searchUi.open && document.querySelector('[aria-modal="true"]')) return
      e.preventDefault()
      toggleGlobalSearch()
    }
  }

  const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

  /** Focus nel campo, trappola di Tab, Esc chiude, il focus torna a chi lo aveva. */
  function dialog(node: HTMLElement) {
    const prev = document.activeElement as HTMLElement | null
    ;(node.querySelector<HTMLElement>('[data-autofocus]') ?? node).focus()
    const onkey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        closeGlobalSearch()
        return
      }
      if (e.key !== 'Tab') return
      const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (!items.length) {
        e.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const cur = document.activeElement
      if (e.shiftKey && (cur === first || cur === node)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && cur === last) {
        e.preventDefault()
        first.focus()
      }
    }
    node.addEventListener('keydown', onkey)
    return {
      destroy() {
        node.removeEventListener('keydown', onkey)
        prev?.focus?.()
      },
    }
  }

  // la voce attiva resta visibile nella lista
  $effect(() => {
    if (searchUi.open && active >= 0) document.getElementById(`${uid}-o${active}`)?.scrollIntoView?.({ block: 'nearest' })
  })

</script>

<svelte:window onkeydown={winKey} />

{#if searchUi.open}
  <div class="ui-modalbg gs-bg" class:phone={viewport.phone} role="presentation" onpointerdown={(e) => { if (e.target === e.currentTarget) closeGlobalSearch() }}>
    <div class="gs" class:phone={viewport.phone} role="dialog" aria-modal="true" aria-label={t('search.title')} tabindex="-1" use:dialog>
      <div class="bar">
        <Icon name="search" size={18} />
        <input
          data-autofocus
          class="in"
          type="text"
          role="combobox"
          aria-expanded="true"
          aria-controls="{uid}-list"
          aria-activedescendant={active >= 0 ? `${uid}-o${active}` : undefined}
          aria-autocomplete="list"
          aria-label={t('search.title')}
          placeholder={t('search.placeholder')}
          autocomplete="off"
          spellcheck="false"
          bind:value={q}
          oninput={() => (activeRaw = 0)}
          onkeydown={inputKey}
        />
        <button type="button" class="x" aria-label={t('search.close')} onclick={closeGlobalSearch}><Icon name="x" size={18} /></button>
      </div>

      <div class="body">
        <ul id="{uid}-list" role="listbox" aria-label={t('search.title')}>
          {#each GROUPS as g (g)}
            {@const rows = results.map((r, i) => ({ r, i })).filter((x) => x.r.group === g)}
            {#if rows.length}
              <li role="presentation" class="gh">{groupLabel(g)}</li>
              {#each rows as { r, i } (g + r.id)}
                <li id="{uid}-o{i}" role="option" aria-selected={i === active} class="opt" class:on={i === active} onclick={() => run(i)} onkeydown={() => {}} onpointermove={() => (activeRaw = i)}>
                  <span class="t">{r.title}</span>
                  {#if r.snippet}
                    <span class="s">{#each snippetParts(r.snippet) as p, k (k)}{#if p.hit}<mark>{p.text}</mark>{:else}{p.text}{/if}{/each}</span>
                  {:else if r.subtitle}
                    <span class="s">{r.subtitle}</span>
                  {/if}
                </li>
              {/each}
            {/if}
          {/each}
        </ul>
        <p class="live" role="status">{results.length === 0 ? t('search.noResults') : t('search.results', { n: results.length })}</p>
        {#if remoteError}<p class="note warn">{t('search.messagesUnavailable')}</p>{/if}
        {#if remote?.engine === 'like'}<p class="note">{t('search.engineLike')}</p>{/if}
      </div>
      {#if !viewport.phone}<div class="foot">{t('search.hint')}</div>{/if}
    </div>
  </div>
{/if}

<style>
  .gs-bg { align-items: start; padding-top: 10vh; }
  .gs-bg.phone { padding: 0; align-items: stretch; }
  .gs { width: 100%; max-width: 640px; max-height: 80vh; display: flex; flex-direction: column; background: var(--surface-raised); color: var(--ink); border: 1px solid var(--line-strong); border-radius: var(--radius-xl); box-shadow: var(--shadow-3); overflow: hidden; box-sizing: border-box; }
  .gs.phone { max-width: none; max-height: none; height: 100%; border-radius: 0; border: 0; }
  .bar { display: flex; align-items: center; gap: var(--space-2); padding: var(--space-2) var(--space-3); border-bottom: 1px solid var(--line); }
  .in { flex: 1; min-width: 0; height: var(--touch-min); background: none; border: 0; color: var(--ink); font: 400 16px/24px var(--font-sans); outline-offset: 2px; }
  .x { display: inline-flex; align-items: center; justify-content: center; min-width: var(--touch-min); min-height: var(--touch-min); background: none; border: 0; color: var(--ink); border-radius: var(--radius-md); cursor: pointer; }
  .x:hover { background: var(--accent-soft); }
  .x:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .body { flex: 1; min-height: 0; overflow: auto; padding: var(--space-2); }
  ul { list-style: none; margin: 0; padding: 0; }
  .gh { padding: var(--space-2) var(--space-3) var(--space-1); font: 600 13px/16px var(--font-sans); color: var(--ink-muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .opt { display: flex; flex-direction: column; justify-content: center; min-height: var(--touch-min); padding: var(--space-1) var(--space-3); border-radius: var(--radius-md); cursor: pointer; }
  .opt.on { background: var(--accent-soft); outline: 2px solid var(--accent); outline-offset: -2px; }
  .t { font: 500 14px/20px var(--font-sans); overflow-wrap: anywhere; }
  .s { font: 400 14px/20px var(--font-sans); color: var(--ink-muted); overflow-wrap: anywhere; }
  mark { background: var(--warn-soft); color: var(--ink); border-radius: 2px; padding: 0 1px; }
  .live { margin: 0; padding: var(--space-2) var(--space-3); font-size: 14px; color: var(--ink-muted); }
  .note { margin: 0; padding: 0 var(--space-3) var(--space-2); font-size: 14px; color: var(--ink-muted); }
  .note.warn { color: var(--warn); }
  .foot { padding: var(--space-2) var(--space-3); border-top: 1px solid var(--line); font-size: 14px; color: var(--ink-muted); }
</style>
