<script lang="ts">
  // Contenuto dei popup della mappa (nodo, collegamento, punto Range Test): HTML con i token.
  import SourceMark from '../ui/SourceMark.svelte'
  import type { SourceKind } from '../ui/logic'

  interface Props {
    title: string
    subtitle?: string
    source?: SourceKind
    mine?: boolean
    rows?: { label: string; value: string }[]
  }
  let { title, subtitle, source, mine = false, rows = [] }: Props = $props()
</script>

<div class="np">
  <div class="head">
    {#if source}<SourceMark {source} size={18} />{/if}
    <b class="title">{title}</b>
    {#if mine}<span class="mine" title="Mio nodo">★ Mio nodo</span>{/if}
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
  .mine {
    color: var(--brand-amber);
    font-size: 12px;
    white-space: nowrap;
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
  dd {
    margin: 0;
    font-family: var(--font-mono);
    font-size: 13px;
    text-align: right;
  }
</style>
