<script lang="ts">
  // «Avvisi nascosti: N — Mostra»: riporta in vista gli avvisi chiusi (solo amministratore).
  import { restoreHidden } from '../alertactions'
  import { isGuest } from '../guest.svelte'
  import { t } from '../i18n/index.svelte'
  import { app } from '../stores.svelte'

  let busy = $state(false)
  async function show() {
    busy = true
    try {
      await restoreHidden()
    } finally {
      busy = false
    }
  }
</script>

{#if !isGuest() && app.alertsHidden > 0}
  <p class="hidden-alerts ui-muted">
    {t('shell.alertsHidden', { n: app.alertsHidden })} —
    <button type="button" class="link" disabled={busy} onclick={show}>{t('shell.alertsShow')}</button>
  </p>
{/if}

<style>
  .hidden-alerts { margin: 0; padding: var(--space-1) var(--space-3); font: 400 14px/20px var(--font-sans); }
  .link { background: none; border: 0; padding: 0; min-height: 24px; color: var(--accent); font: inherit; text-decoration: underline; cursor: pointer; }
  .link:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
</style>
