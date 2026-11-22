<script lang="ts">
  import { t } from '../../lib/i18n/index.svelte'
  import Card from '../../lib/ui/Card.svelte'
</script>

<Card>
  <section class="sec">
    <h3>{t('settings.diag.title')}</h3>
    <p class="ui-hint">{t('settings.diag.body')}</p>
    <div class="row">
      <a class="ui-btn" href="/api/diagnostics/bundle" download>{t('settings.diag.download')}</a>
    </div>
  </section>
</Card>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  a.ui-btn { text-decoration: none; }
</style>
