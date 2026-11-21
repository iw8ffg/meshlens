<script lang="ts">
  import type { Snippet } from 'svelte'
  import Icon from './Icon.svelte'
  import Button from './Button.svelte'

  interface Props {
    kind?: 'info' | 'ok' | 'warn' | 'danger'
    /** Millisecondi prima di `onclose`; 0 = resta finché non lo chiudi. */
    duration?: number
    onclose?: () => void
    children: Snippet
  }
  let { kind = 'info', duration = 5000, onclose, children }: Props = $props()
  const icon = $derived(kind === 'ok' ? 'check' : kind === 'info' ? 'info' : 'alert')
  const color = $derived(kind === 'info' ? 'var(--accent)' : `var(--${kind})`)

  $effect(() => {
    if (!duration) return
    const t = setTimeout(() => onclose?.(), duration)
    return () => clearTimeout(t)
  })
</script>

<div class="ui-toast" role="status">
  <span style="color: {color}; display: inline-flex"><Icon name={icon} size={20} /></span>
  <span style="flex: 1">{@render children()}</span>
  {#if onclose}<Button kind="ghost" iconOnly icon="x" label="Chiudi" onclick={onclose} />{/if}
</div>
