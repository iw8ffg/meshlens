<script lang="ts">
  // WP4 (E10): messaggi predefiniti delle radio con tastiera/rotella (T-Deck, T-Pager).
  // Il separatore | lo gestisce MeshLens; limite di 200 byte con i separatori.
  import { ApiError, getJSON } from '../lib/api'
  import { CANNED_MAX_BYTES, cannedBytes, cannedError, getCanned, putCanned } from '../lib/canned'
  import { t } from '../lib/i18n/index.svelte'
  import type { AppSettings } from '../lib/settings'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'

  let { nodeId, radioId, lock }: { nodeId: string; radioId: string | null; lock: boolean } = $props()

  let items = $state<{ id: number; text: string }[]>([])
  let nextId = 0
  let loaded = $state(false)
  let busy = $state(false)
  let error = $state('')
  let info = $state('')

  const texts = $derived(items.map((i) => i.text))
  const bytes = $derived(cannedBytes(texts))
  const problem = $derived(cannedError(texts))

  const setList = (list: string[]) => (items = list.map((text) => ({ id: nextId++, text })))
  const errText = (e: unknown) => (e instanceof ApiError ? e.message : t('canned.failed'))

  async function read() {
    busy = true
    error = ''
    info = ''
    try {
      setList((await getCanned(nodeId, radioId ?? undefined)).messages)
      loaded = true
    } catch (e) {
      error = errText(e)
    } finally {
      busy = false
    }
  }

  async function write() {
    if (problem) return
    busy = true
    error = ''
    info = ''
    try {
      setList((await putCanned(nodeId, texts, radioId ?? undefined)).messages)
      info = t('canned.written')
    } catch (e) {
      error = errText(e)
    } finally {
      busy = false
    }
  }

  async function useQuick() {
    error = ''
    info = ''
    try {
      const quick = (await getJSON<AppSettings>('/settings')).quick_replies ?? []
      const out: string[] = []
      for (const q of quick) {
        if (q.includes('|')) continue
        if (cannedBytes([...out, q]) > CANNED_MAX_BYTES) break
        out.push(q)
      }
      setList(out)
      loaded = true
      if (out.length < quick.length) info = t('canned.quickTruncated', { n: out.length, total: quick.length })
    } catch (e) {
      error = errText(e)
    }
  }

  function move(i: number, d: -1 | 1) {
    const j = i + d
    if (j < 0 || j >= items.length) return
    const copy = items.slice()
    ;[copy[i], copy[j]] = [copy[j], copy[i]]
    items = copy
  }
</script>

<section class="cc">
  <h3>{t('canned.title')}</h3>
  <p class="muted">{t('canned.note')}</p>
  <div class="row">
    <Button icon="download" disabled={lock || busy} onclick={read}>{t('canned.read')}</Button>
    <Button disabled={busy} onclick={useQuick}>{t('canned.useQuick')}</Button>
  </div>
  {#if loaded}
    <ol>
      {#each items as it, i (it.id)}
        <li>
          <input class="ui-input" aria-label={t('canned.item', { n: i + 1 })} maxlength="200" bind:value={it.text} disabled={busy} />
          <Button kind="ghost" iconOnly icon="back" label={t('canned.up')} disabled={busy || i === 0} onclick={() => move(i, -1)} class="up" />
          <Button kind="ghost" iconOnly icon="back" label={t('canned.down')} disabled={busy || i === items.length - 1} onclick={() => move(i, 1)} class="down" />
          <Button kind="ghost" iconOnly icon="trash" label={t('canned.remove')} disabled={busy} onclick={() => (items = items.filter((x) => x.id !== it.id))} />
        </li>
      {/each}
    </ol>
    <div class="row">
      <Button icon="plus" disabled={busy} onclick={() => (items = [...items, { id: nextId++, text: '' }])}>{t('canned.add')}</Button>
      <span class="count" class:over={bytes > CANNED_MAX_BYTES}>{t('canned.bytes', { n: bytes, max: CANNED_MAX_BYTES })}</span>
    </div>
    {#if problem}<p class="err">{t(problem)}</p>{/if}
    <div><Button kind="primary" disabled={lock || busy || !!problem} onclick={write}>{t('canned.write')}</Button></div>
  {/if}
  {#if error}<Banner kind="danger" title={error} />{/if}
  {#if info}<Banner kind="ok" title={info} />{/if}
</section>

<style>
  .cc {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  h3 {
    margin: var(--space-2) 0 0;
    font: 600 14px/20px var(--font-sans);
  }
  .muted {
    margin: 0;
    color: var(--ink-muted);
    font-size: 13px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
  ol {
    margin: 0;
    padding-left: var(--space-5, 24px);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  li {
    display: flex;
    gap: var(--space-1);
    align-items: center;
  }
  li input {
    flex: 1;
    min-width: 0;
  }
  li :global(.up svg) {
    transform: rotate(90deg);
  }
  li :global(.down svg) {
    transform: rotate(-90deg);
  }
  .count {
    font-size: 13px;
    color: var(--ink-muted);
    font-variant-numeric: tabular-nums;
  }
  .count.over,
  .err {
    color: var(--danger);
  }
  .err {
    margin: 0;
    font-size: 14px;
  }
  :global(.vp-phone) .muted,
  :global(.vp-phone) .count {
    font-size: 14px;
  }
  :global(.vp-phone) li :global(.ui-btn) {
    min-width: 44px;
    min-height: 44px;
  }
</style>
