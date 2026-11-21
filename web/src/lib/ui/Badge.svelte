<script lang="ts">
  import type { Snippet } from 'svelte'
  import Icon from './Icon.svelte'
  import type { IconName } from './icons'

  interface Props {
    kind?: 'neutral' | 'ok' | 'warn' | 'danger' | 'info'
    icon?: IconName
    children: Snippet
  }
  let { kind = 'neutral', icon, children }: Props = $props()
</script>

<span class="ui-badge {kind === 'neutral' ? '' : kind}">{#if icon}<Icon name={icon} size={14} />{/if}{@render children()}</span>
