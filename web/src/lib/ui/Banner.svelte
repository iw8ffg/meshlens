<script lang="ts">
  import type { Snippet } from 'svelte'
  import Icon from './Icon.svelte'

  interface Props {
    kind?: 'info' | 'ok' | 'warn' | 'danger'
    title: string
    children?: Snippet
    action?: Snippet
  }
  let { kind = 'info', title, children, action }: Props = $props()
  const icon = $derived(kind === 'ok' ? 'check' : kind === 'info' ? 'info' : 'alert')
</script>

<div class="ui-banner {kind}" role={kind === 'danger' ? 'alert' : 'status'}>
  <Icon name={icon} size={20} />
  <div style="flex: 1; min-width: 0">
    <div class="bt">{title}</div>
    {#if children}<div>{@render children()}</div>{/if}
  </div>
  {#if action}{@render action()}{/if}
</div>
