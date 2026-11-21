<script lang="ts">
  import { T } from '../../lib/strings/messaggi'
  import type { Message } from '../../lib/types'

  interface Props {
    /** Messaggio citato, se presente nella lista. */
    replyTo: Message | null
    missing: boolean
    nodeName: (id: string) => string
    onjump: (key: string) => void
  }
  let { replyTo, missing, nodeName, onjump }: Props = $props()

  const who = $derived(replyTo ? (replyTo.direction === 'out' ? T.you : (replyTo.from_name ?? nodeName(replyTo.from))) : '')
  const preview = $derived(replyTo ? (replyTo.text.length > 60 ? `${replyTo.text.slice(0, 60)}…` : replyTo.text) : '')
</script>

{#if replyTo}
  <button type="button" class="quote" title={T.quoteGoto(who)} onclick={() => onjump(replyTo.key)}>
    {T.quoteLabel(who, preview)}
  </button>
{:else if missing}
  <span class="quote gone">{T.replyMissing}</span>
{/if}

<style>
  .quote {
    display: block;
    max-width: 100%;
    margin: 0 0 var(--space-1);
    padding: var(--space-1) var(--space-2);
    box-sizing: border-box;
    text-align: left;
    background: var(--surface-sunken);
    border: 0;
    border-left: 3px solid var(--accent);
    border-radius: var(--radius-sm);
    color: var(--ink-muted);
    font: 400 13px/18px var(--font-sans);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  button.quote {
    cursor: pointer;
  }
  button.quote:hover {
    background: var(--accent-soft);
  }
  button.quote:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  .gone {
    font-style: italic;
  }
  :global(.vp-phone) .quote {
    font-size: 14px;
    min-height: 24px;
  }
</style>
