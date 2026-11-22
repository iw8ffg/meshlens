<script lang="ts">
  // Contenuto dei popup della mappa (nodo, collegamento, punto Range Test): HTML con i token.
  import SourceMark from '../ui/SourceMark.svelte'
  import type { SourceKind } from '../ui/logic'
  import Icon from '../ui/Icon.svelte'
  import type { IconName } from '../ui/icons'
  import { onDestroy } from 'svelte'
  import { t } from '../i18n/index.svelte'

  interface Props {
    title: string
    subtitle?: string
    source?: SourceKind
    mine?: boolean
    favorite?: boolean
    rows?: { label: string; value: string }[]
    /** `onclick` che risolve a `true` mostra «Copiato» per 2 s. */
    actions?: { label: string; icon: IconName; onclick: () => void | boolean | Promise<void | boolean>; disabled?: boolean }[]
  }
  let { title, subtitle, source, mine = false, favorite = false, rows = [], actions = [] }: Props = $props()

  let copied = $state(false)
  let copiedTimer: ReturnType<typeof setTimeout> | null = null
  onDestroy(() => {
    if (copiedTimer) clearTimeout(copiedTimer)
  })

  async function run(a: NonNullable<Props['actions']>[number]) {
    const r = await a.onclick()
    if (r !== true) return
    copied = true
    if (copiedTimer) clearTimeout(copiedTimer)
    copiedTimer = setTimeout(() => {
      copied = false
      copiedTimer = null
    }, 2000)
  }
</script>

<div class="np">
  <div class="head">
    {#if source}<SourceMark {source} size={18} />{/if}
    <b class="title">{title}</b>
    {#if mine}<span class="flag mine" title={t('nodes.mine')}>⌂ {t('nodes.mine')}</span>{/if}
    {#if favorite}<span class="flag fav" title={t('nodes.favorite')}>★ {t('nodes.favorite')}</span>{/if}
  </div>
  {#if subtitle}<div class="sub">{subtitle}</div>{/if}
  {#if rows.length > 0}
    <dl>
      {#each rows as r (r.label)}
        <dt>{r.label}</dt>
        <dd>{r.value}</dd>
      {/each}
    </dl>
  {/if}
  {#if actions.length > 0}
    <div class="acts">
      {#each actions as a (a.label)}
        <button type="button" class="act" disabled={a.disabled} onclick={() => run(a)}>
          <Icon name={a.icon} size={16} />
          <span>{a.label}</span>
        </button>
      {/each}
    </div>
    <div class="copied" role="status">{copied ? t('waypoints.copied') : ''}</div>
  {/if}
</div>

<style>
  .np {
    min-width: 180px;
    max-width: 260px;
    color: var(--ink);
    font-family: var(--font-sans);
    font-size: 14px;
    line-height: 20px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding-right: var(--space-6);
  }
  .title {
    font-weight: 600;
    overflow-wrap: anywhere;
  }
  .head {
    flex-wrap: wrap;
  }
  .flag {
    font-size: 12px;
    white-space: nowrap;
  }
  .mine {
    color: var(--accent-ink);
  }
  .fav {
    color: var(--brand-amber);
  }
  .sub {
    color: var(--ink-muted);
    font-size: 12px;
    line-height: 16px;
  }
  dl {
    display: grid;
    grid-template-columns: auto 1fr;
    gap: 2px var(--space-3);
    margin: var(--space-2) 0 0;
  }
  dt {
    color: var(--ink-muted);
  }
  .acts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin-top: var(--space-3);
  }
  .act {
    display: inline-flex;
    align-items: center;
    gap: var(--space-2);
    min-height: var(--control-h-desktop);
    padding: 0 var(--space-3);
    border-radius: var(--radius-md);
    border: 1px solid var(--line-strong);
    background: var(--surface-raised);
    color: var(--ink);
    font: 500 14px/20px var(--font-sans);
    cursor: pointer;
  }
  .act:hover:not(:disabled) {
    background: var(--surface-sunken);
  }
  .act:focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
  }
  .act:disabled {
    opacity: 0.5;
    cursor: default;
  }
  :global(.vp-phone) .act {
    min-height: var(--control-h-phone);
    min-width: var(--touch-min);
  }
  .copied {
    min-height: 16px;
    margin-top: var(--space-1);
    color: var(--accent-ink);
    font-size: 12px;
    line-height: 16px;
  }
  dd {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 13px;
    text-align: right;
  }
</style>
