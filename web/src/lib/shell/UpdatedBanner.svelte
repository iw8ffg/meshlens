<script lang="ts">
  import Icon from '../ui/Icon.svelte'
  import { staleVersion, ver } from '../appversion.svelte'
  import { t } from '../i18n/index.svelte'

  const next = $derived(staleVersion(ver))
</script>

{#if next}
  <div class="bar" role="status" aria-live="polite">
    <Icon name="check" size={18} />
    <span class="txt">{t('shell.updatedReload', { version: next })}</span>
    <button type="button" onclick={() => location.reload()}>{t('shell.reload')}</button>
  </div>
{/if}

<style>
  .bar {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-2) var(--space-3);
    color: var(--ink);
    background: var(--ok-soft);
    font: 500 14px/20px var(--font-sans);
    border-bottom: 1px solid var(--line);
  }
  .txt {
    flex: 1;
    min-width: 0;
  }
  button {
    min-height: 32px;
    padding: 0 var(--space-3);
    background: var(--surface);
    color: var(--ink);
    border: 1px solid var(--line-strong);
    border-radius: var(--radius-md);
    font: 500 14px/20px var(--font-sans);
    cursor: pointer;
  }
  button:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  :global(.vp-phone) button {
    min-height: var(--touch-min);
  }
</style>
