<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLButtonAttributes } from 'svelte/elements'
  import Icon from './Icon.svelte'
  import type { IconName } from './icons'

  interface Props extends Omit<HTMLButtonAttributes, 'children'> {
    kind?: 'default' | 'primary' | 'danger' | 'ghost'
    icon?: IconName
    /** Pulsante solo icona: serve `label` come aria-label. */
    iconOnly?: boolean
    label?: string
    block?: boolean
    children?: Snippet
  }
  let { kind = 'default', icon, iconOnly = false, label, block = false, type = 'button', children, class: cls = '', ...rest }: Props = $props()
</script>

<button {type} class="ui-btn {kind === 'default' ? '' : kind} {iconOnly ? 'icon' : ''} {block ? 'block' : ''} {cls}" aria-label={iconOnly ? label : undefined} {...rest}>
  {#if icon}<Icon name={icon} size={iconOnly ? 18 : 16} />{/if}
  {#if !iconOnly}{#if children}{@render children()}{:else if label}<span>{label}</span>{/if}{/if}
</button>
