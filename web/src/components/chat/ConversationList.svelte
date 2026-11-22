<script lang="ts">
  import { ago } from '../../lib/format'
  import { filterConversations, type ConvItem } from '../../lib/conversations'
  import { t, tn } from '../../lib/i18n/index.svelte'
  import Empty from '../../lib/ui/Empty.svelte'
  import type { Message } from '../../lib/types'

  // `now` serve all'orario relativo, `groups` alla ricerca nel testo dei messaggi caricati
  let {
    items,
    active,
    onopen,
    now,
    groups,
  }: { items: ConvItem[]; active: string; onopen: (key: string) => void; now: number; groups: Map<string, Message[]> } = $props()

  let query = $state('')
  const shown = $derived(filterConversations(items, query, groups))
</script>

<div class="convs">
  <div class="search">
    <input class="ui-input" type="search" aria-label={t('chat.searchConversations')} placeholder={t('chat.searchPlaceholder')} bind:value={query} />
  </div>
  {#if shown.length === 0}
    <Empty icon="chat" title={t('chat.noConversationMatch')} />
  {:else}
    <ul class="list">
      {#each shown as it (it.key)}
        <li>
          <button
            type="button"
            class="row"
            class:unread={it.unread > 0}
            aria-current={it.key === active ? 'true' : undefined}
            onclick={() => onopen(it.key)}
          >
            <span class="top">
              <span class="label">{it.label}</span>
              {#if it.lastTime > 0}<span class="time">{ago((now - it.lastTime) / 60)}</span>{/if}
            </span>
            <span class="bottom">
              <span class="preview">{it.kind === 'mqtt' ? t('chat.mqttConversationHint') : it.preview || t('chat.noMessagesYet')}</span>
              {#if it.unread > 0}
                <span class="count" role="img" aria-label={tn('shell.unread', it.unread)}>{it.unread}</span>
              {/if}
            </span>
          </button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .convs {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-height: 0;
    color: var(--ink);
  }
  .search {
    padding: var(--space-3);
    border-bottom: 1px solid var(--line);
    flex: none;
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    flex: 1;
    overflow: auto;
  }
  .row {
    display: flex;
    flex-direction: column;
    gap: 2px;
    width: 100%;
    min-height: var(--touch-min);
    padding: var(--space-2) var(--space-3);
    background: none;
    border: 0;
    border-bottom: 1px solid var(--line);
    color: var(--ink);
    text-align: left;
    font: 400 14px/20px var(--font-sans);
    cursor: pointer;
  }
  .row:hover {
    background: var(--surface-sunken);
  }
  .row:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: -2px;
  }
  .row[aria-current='true'] {
    background: var(--accent-soft);
  }
  .top,
  .bottom {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
  }
  .label,
  .preview {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .label {
    font-weight: 500;
  }
  .preview,
  .time {
    color: var(--ink-muted);
    font-size: 13px;
  }
  .time {
    flex: none;
  }
  .unread .label,
  .unread .preview {
    font-weight: 700;
    color: var(--ink);
  }
  .count {
    flex: none;
    min-width: 20px;
    padding: 0 6px;
    border-radius: var(--radius-pill);
    background: var(--accent);
    color: var(--on-accent);
    font: 700 12px/20px var(--font-sans);
    text-align: center;
  }
  :global(.vp-phone) .row {
    min-height: 56px;
  }
  :global(.vp-phone) .preview,
  :global(.vp-phone) .time,
  :global(.vp-phone) .count {
    font-size: 14px;
  }
</style>
