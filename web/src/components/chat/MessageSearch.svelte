<script lang="ts">
  // Ricerca nel testo dei messaggi (WP1, E4): filtri per conversazione, periodo e mittente; risultati
  // paginati con cursore. Mai {@html}: gli snippet si rendono a segmenti con <mark>.
  import { untrack } from 'svelte'
  import { convLabel } from '../../lib/conversations'
  import { formatDate } from '../../lib/format'
  import { t } from '../../lib/i18n/index.svelte'
  import type { MsgKey } from '../../lib/i18n/index.svelte'
  import { hitConvKey, mergePages, periodRange, searchMessages, senderOptions, snippetParts } from '../../lib/msgsearch'
  import type { PeriodKind } from '../../lib/msgsearch'
  import { app } from '../../lib/stores.svelte'
  import type { MessageSearchHit } from '../../lib/types'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Field from '../../lib/ui/Field.svelte'
  import Icon from '../../lib/ui/Icon.svelte'
  import Select from '../../lib/ui/Select.svelte'
  import { dialogTrap } from './dialog'

  let { conv, onhit, onclose }: { conv: string | null; onhit: (hit: MessageSearchHit) => void; onclose: () => void } = $props()

  const uid = $props.id()
  const PERIODS: PeriodKind[] = ['all', 'day', 'week', 'month']
  const MIN_CHARS = 2

  let q = $state('')
  let onlyThis = $state(untrack(() => conv !== null))
  let period = $state<PeriodKind>('all')
  let sender = $state('')
  let hits = $state<MessageSearchHit[]>([])
  let pool = $state<MessageSearchHit[]>([])
  let next = $state<string | null>(null)
  let engine = $state<'fts5' | 'like' | null>(null)
  let loading = $state(false)
  let loadingMore = $state(false)
  let error = $state('')
  let searched = $state(false)
  let seq = 0

  const nodeName = (id: string) => app.nodes.get(id)?.long_name || app.nodes.get(id)?.short_name || id
  const brokers = $derived((app.status?.mqtt.brokers ?? []).filter((b) => b.enabled))
  const senders = $derived(senderOptions(pool))

  function params(cursor: string | null) {
    const r = periodRange(period, Math.floor(Date.now() / 1000))
    return { q: q.trim(), conv: onlyThis ? conv : null, sender: sender || null, since: r.since, until: r.until, cursor, limit: 30 }
  }

  async function run(more: boolean) {
    const mine = ++seq
    if (more) loadingMore = true
    else loading = true
    error = ''
    try {
      const res = await searchMessages(params(more ? next : null))
      if (mine !== seq) return
      hits = more ? mergePages(hits, res.hits) : res.hits
      pool = more ? mergePages(pool, res.hits) : sender ? pool : res.hits
      next = res.next
      engine = res.engine
      searched = true
    } catch (e) {
      if (mine !== seq) return
      error = e instanceof Error && e.message ? e.message : t('search.messages.error')
    } finally {
      if (mine === seq) {
        loading = false
        loadingMore = false
      }
    }
  }

  // Ricerca dopo 300 ms senza digitazione; il cambio dei filtri la rilancia da capo
  $effect(() => {
    const query = q.trim()
    void onlyThis
    void period
    void sender
    if (query.length < MIN_CHARS) {
      untrack(() => {
        seq++
        hits = []
        next = null
        searched = false
        loading = false
        error = ''
      })
      return
    }
    const timer = setTimeout(() => void run(false), 300)
    return () => clearTimeout(timer)
  })

  // I mittenti proposti vengono dai risultati senza filtro mittente: si azzerano se cambiano testo o altri filtri
  $effect(() => {
    void q
    void onlyThis
    void period
    untrack(() => {
      sender = ''
      pool = []
    })
  })

  function pickHit(h: MessageSearchHit) {
    onclose()
    onhit(h)
  }
</script>

<div class="ui-modalbg" role="presentation" onpointerdown={(e) => { if (e.target === e.currentTarget) onclose() }}>
  <div class="ms" role="dialog" aria-modal="true" aria-label={t('search.messages.title')} tabindex="-1" use:dialogTrap={onclose}>
    <div class="top">
      <h2>{t('search.messages.title')}</h2>
      <Button iconOnly kind="ghost" icon="x" label={t('search.close')} onclick={onclose} />
    </div>

    <Field label={t('search.messages.title')} for="{uid}-q">
      {#snippet children({ describedby })}
        <input id="{uid}-q" data-autofocus class="ui-input" type="search" autocomplete="off" spellcheck="false" aria-describedby={describedby} placeholder={t('search.messages.placeholder')} bind:value={q} />
      {/snippet}
    </Field>

    <div class="filters">
      {#if conv !== null}
        <label class="chk"><input type="checkbox" bind:checked={onlyThis} /> {t('search.messages.thisConversation')}</label>
      {/if}
      <Field label={t('search.messages.periodLabel')} for="{uid}-p">
        {#snippet children({ describedby })}
          <Select id="{uid}-p" bind:value={period} aria-describedby={describedby}>
            {#each PERIODS as p (p)}<option value={p}>{t(`search.messages.period.${p}` as MsgKey)}</option>{/each}
          </Select>
        {/snippet}
      </Field>
      <Field label={t('search.messages.sender')} for="{uid}-s">
        {#snippet children({ describedby })}
          <Select id="{uid}-s" bind:value={sender} aria-describedby={describedby}>
            <option value="">{t('search.messages.anySender')}</option>
            {#each senders as s (s.id)}<option value={s.id}>{s.name}</option>{/each}
          </Select>
        {/snippet}
      </Field>
    </div>

    <div class="res" aria-live="polite">
      {#if error}
        <Banner kind="danger" title={t('search.messages.error')}>{error}</Banner>
      {:else if loading}
        <p class="muted">{t('shell.loading')}</p>
      {:else if searched && hits.length === 0}
        <p class="muted">{t('search.messages.none')}</p>
      {/if}
      <ul>
        {#each hits as h (h.message.key)}
          <li>
            <button type="button" class="hit" onclick={() => pickHit(h)}>
              <span class="who">{h.message.from_name || nodeName(h.message.from)}</span>
              <span class="meta">{formatDate(h.message.time)} · {convLabel(hitConvKey(h), app.radios, nodeName, brokers)}</span>
              <span class="snip">{#each snippetParts(h.snippet ?? h.message.text) as p, k (k)}{#if p.hit}<mark>{p.text}</mark>{:else}{p.text}{/if}{/each}</span>
            </button>
          </li>
        {/each}
      </ul>
      {#if next}
        <Button onclick={() => run(true)} disabled={loadingMore}>{loadingMore ? t('shell.loading') : t('search.messages.loadMore')}</Button>
      {/if}
      {#if engine === 'like'}<p class="muted"><Icon name="info" size={14} /> {t('search.messages.engineLike')}</p>{/if}
    </div>
  </div>
</div>

<style>
  .ms { width: 100%; max-width: 640px; max-height: 100%; display: flex; flex-direction: column; gap: var(--space-3); background: var(--surface-raised); color: var(--ink); border: 1px solid var(--line-strong); border-radius: var(--radius-xl); box-shadow: var(--shadow-3); padding: var(--space-4); box-sizing: border-box; overflow: hidden; }
  :global(.vp-phone) .ms { height: 100%; max-width: none; border-radius: 0; }
  .top { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
  h2 { margin: 0; font: 600 18px/24px var(--font-sans); }
  .filters { display: flex; flex-wrap: wrap; gap: var(--space-3); align-items: flex-end; }
  .filters :global(.ui-field) { flex: 1; min-width: 140px; }
  .chk { display: inline-flex; align-items: center; gap: var(--space-2); min-height: var(--touch-min); font-size: 14px; flex: 1 0 100%; }
  .chk input { width: 18px; height: 18px; accent-color: var(--accent); }
  .res { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: var(--space-2); }
  ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); }
  .hit { width: 100%; text-align: left; display: flex; flex-direction: column; gap: 2px; min-height: var(--touch-min); background: none; border: 1px solid var(--line); border-radius: var(--radius-md); padding: var(--space-2) var(--space-3); color: var(--ink); cursor: pointer; font: 400 14px/20px var(--font-sans); }
  .hit:hover { background: var(--accent-soft); }
  .hit:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .who { font-weight: 600; }
  .meta { color: var(--ink-muted); font-size: 14px; }
  .snip { overflow-wrap: anywhere; }
  mark { background: var(--warn-soft); color: var(--ink); border-radius: 2px; padding: 0 1px; }
  .muted { margin: 0; color: var(--ink-muted); font-size: 14px; }
</style>
