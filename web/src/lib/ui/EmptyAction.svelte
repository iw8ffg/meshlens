<script lang="ts">
  // Azioni suggerite negli stati vuoti (WP1, E1): «Collega una radio», «Configura MQTT», guida di avvio.
  // Nessun contenitore proprio: si inserisce nello snippet `action` di uno stato vuoto; senza azioni non produce markup.
  import { t } from '../i18n/index.svelte'
  import { visibleNodes } from '../filters'
  import { emptyActions } from '../onboarding'
  import { openOnboarding } from '../onboarding.svelte'
  import { navigate } from '../shell/navigate'
  import { app } from '../stores.svelte'
  import Button from './Button.svelte'

  interface Props {
    kind: 'nodes' | 'network' | 'radios' | 'chat'
  }
  let { kind }: Props = $props()

  const actions = $derived(
    emptyActions(kind, {
      nodeCount: visibleNodes(app.nodes.values()).length,
      radioCount: app.radios.length,
      brokerCount: app.status?.mqtt?.connected ? 1 : 0,
      connectedRadios: app.radios.filter((r) => r.state === 'connected').length,
      convCount: app.radioMessages.length,
    }),
  )
</script>

{#each actions as a, i (a.labelKey)}
  <Button kind={i === 0 ? 'primary' : 'default'} onclick={() => (a.tab === null ? openOnboarding() : navigate(a.tab))}>{t(a.labelKey)}</Button>
{/each}
