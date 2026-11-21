<script lang="ts">
  import { T } from '../../lib/strings/messaggi'
  import type { ReactionChip } from '../../lib/reactions'

  let { reactions }: { reactions: ReactionChip[] } = $props()
</script>

{#if reactions.length}
  <ul class="chips">
    {#each reactions as r (r.emoji)}
      <li class="chip" class:mine={r.mine} title={T.reactionTitle(r.emoji, r.names.join(', '))}>
        <span class="em">{r.emoji}</span>
        {#if r.count > 1}<span class="n">{r.count}</span>{/if}
      </li>
    {/each}
  </ul>
{/if}

<style>
  .chips {
    list-style: none;
    margin: var(--space-1) 0 0;
    padding: 0;
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-1);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 0 var(--space-2);
    min-height: 24px;
    background: var(--surface-sunken);
    border: 1px solid var(--line);
    border-radius: 12px;
    color: var(--ink);
    font: 500 14px/20px var(--font-sans);
  }
  .chip.mine {
    background: var(--accent-soft);
    border-color: var(--accent);
  }
  .n {
    font-size: 14px;
    color: var(--ink-muted);
  }
</style>
