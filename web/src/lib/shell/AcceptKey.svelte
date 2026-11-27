<script lang="ts">
  // «Accetta la nuova chiave»: toglie l'avviso di chiave cambiata di un nodo (solo amministratore).
  import Button from '../ui/Button.svelte'
  import { acceptNewKey } from '../alertactions'
  import { isGuest } from '../guest.svelte'
  import { t } from '../i18n/index.svelte'

  let { nodeId }: { nodeId: string } = $props()
  let busy = $state(false)
  let failed = $state(false)

  async function accept() {
    busy = true
    failed = false
    try {
      await acceptNewKey(nodeId)
    } catch {
      failed = true
    } finally {
      busy = false
    }
  }
</script>

{#if !isGuest()}
  <Button icon="check" disabled={busy} onclick={accept}>{t('shell.acceptKey')}</Button>
  {#if failed}<span class="ui-muted" role="alert">{t('shell.acceptKeyFailed')}</span>{/if}
{/if}
