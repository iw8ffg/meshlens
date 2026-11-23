<script lang="ts">
  // Impostazioni → Automazioni (WP5: E14 traceroute periodici, E15 bot e webhook). Nessuna prop.
  import { onDestroy, onMount } from 'svelte'
  import { getJSON } from '../../lib/api'
  import { startAutomation } from '../../lib/automation.svelte'
  import type { AppSettings } from '../../lib/settings'
  import BotCard from './automations/BotCard.svelte'
  import TraceCard from './automations/TraceCard.svelte'
  import WebhookCard from './automations/WebhookCard.svelte'

  let settings = $state<AppSettings | null>(null)
  let stop: (() => void) | null = null

  async function reload(): Promise<void> {
    try {
      settings = await getJSON<AppSettings>('/settings')
    } catch {
      /* la sezione resta vuota: le altre impostazioni funzionano */
    }
  }

  onMount(() => {
    stop = startAutomation()
    void reload()
  })
  onDestroy(() => stop?.())
</script>

{#if settings}
  <div class="auto">
    <TraceCard {settings} onsaved={(s) => (settings = s)} />
    <BotCard {settings} onsaved={(s) => (settings = s)} {reload} />
    <WebhookCard {settings} onsaved={(s) => (settings = s)} {reload} />
  </div>
{/if}

<style>
  .auto {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
</style>
