<script lang="ts">
  import type { Snippet } from 'svelte'
  import Icon from './Icon.svelte'
  import type { IconName } from './icons'

  interface Props {
    icon?: IconName
    title: string
    children?: Snippet
    action?: Snippet
  }
  let { icon = 'info', title, children, action }: Props = $props()
</script>

<div class="ui-empty">
  <div class="ic"><Icon name={icon} size={26} /></div>
  <h3>{title}</h3>
  {#if children}<p>{@render children()}</p>{/if}
  {#if action}{@render action()}{/if}
</div>
