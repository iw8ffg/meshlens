<script lang="ts">
  // Scheda del righello (in alto a sinistra, stile della scheda copertura).
  import Button from '../ui/Button.svelte'
  import { t } from '../i18n/index.svelte'

  interface Props {
    text: string
    onclear: () => void
    onclose: () => void
  }
  let { text, onclear, onclose }: Props = $props()
</script>

<div class="rulerbar" role="status">
  <b>{text}</b>
  <div class="row">
    <Button onclick={onclear}>{t('map.ruler.restart')}</Button>
    <Button kind="ghost" onclick={onclose}>{t('map.ruler.close')}</Button>
  </div>
</div>

<style>
  .rulerbar {
    max-width: 280px;
    padding: var(--space-3);
    border-radius: var(--radius-lg);
    border: 1px solid var(--line);
    background: var(--surface);
    color: var(--ink);
    box-shadow: var(--shadow-2);
    font-size: 14px;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    pointer-events: auto;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
</style>
