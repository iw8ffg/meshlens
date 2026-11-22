<script lang="ts">
  import type { SourceKind } from './logic'
  import { t } from '../i18n/index.svelte'

  interface Props {
    source: SourceKind
    size?: number
  }
  let { source, size = 20 }: Props = $props()
  const color = $derived(source === 'radio' ? 'var(--src-radio)' : source === 'mqtt' ? 'var(--src-mqtt)' : 'var(--src-both)')
  const name = $derived(source === 'radio' ? 'Radio' : source === 'mqtt' ? 'MQTT' : t('common.sourceBoth'))
</script>

<span class="ui-src" title={name}>
  <svg width={size} height={size} viewBox="0 0 20 20" role="img" aria-label={name}>
    {#if source === 'both'}
      <circle cx="10" cy="10" r="4" fill="none" stroke={color} stroke-width="2" />
      <circle cx="10" cy="10" r="8" fill="none" stroke={color} stroke-width="1.5" />
    {:else if source === 'mqtt'}
      <circle cx="10" cy="10" r="6" fill="none" stroke={color} stroke-width="2.5" stroke-dasharray="3 2.2" />
    {:else}
      <circle cx="10" cy="10" r="6" fill="none" stroke={color} stroke-width="2.5" />
    {/if}
  </svg>
</span>
