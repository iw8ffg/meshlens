<script lang="ts">
  // × «Chiudi» di un avviso: solo per l'amministratore (l'ospite è in sola lettura).
  import Button from '../ui/Button.svelte'
  import { dismiss } from '../alertactions'
  import { isGuest } from '../guest.svelte'
  import { t } from '../i18n/index.svelte'

  let { alertKey, text }: { alertKey: string; text: string } = $props()
  let busy = $state(false)
  let failed = $state(false)

  async function close() {
    busy = true
    failed = false
    try {
      await dismiss(alertKey)
    } catch {
      failed = true
    } finally {
      busy = false
    }
  }
</script>

{#if !isGuest()}
  <Button kind="ghost" iconOnly icon="x" label={t('shell.alertDismissAria', { text })} title={t('shell.alertDismiss')} disabled={busy} onclick={close} />
  {#if failed}<span class="ui-muted" role="alert">{t('shell.alertDismissFailed')}</span>{/if}
{/if}
