<script lang="ts">
  import { ICONS, type IconName } from './icons'

  interface Props {
    name: IconName
    size?: number
    label?: string
  }
  let { name, size = 18, label }: Props = $props()
  const Cmp = $derived(ICONS[name])
</script>

{#if label}
  <Cmp class="ui-ic" {size} strokeWidth={1.75} role="img" aria-label={label} />
{:else}
  <Cmp class="ui-ic" {size} strokeWidth={1.75} aria-hidden="true" />
{/if}
