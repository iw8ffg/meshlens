<script lang="ts">
  // Badge solo testuale: il logo ufficiale non è incluso finché non si verifica la trademark policy.
  import { t } from '../i18n/index.svelte'
</script>

<div class="mb">
  <span class="chip">{t('shell.badge')}</span>
  <p>{t('shell.badgeNote')}</p>
</div>

<style>
  .mb { display: flex; flex-direction: column; align-items: center; gap: var(--space-2); text-align: center; color: var(--ink-muted); }
  .chip { display: inline-flex; align-items: center; min-height: 28px; padding: 0 var(--space-3); border: 1px dashed var(--line-strong); border-radius: var(--radius-sm); font: 600 13px/16px var(--font-sans); color: var(--ink); }
  p { margin: 0; max-width: 340px; font: 400 12px/16px var(--font-sans); }
  :global(.vp-phone) .chip, :global(.vp-phone) p { font-size: 14px; line-height: 20px; }
</style>
