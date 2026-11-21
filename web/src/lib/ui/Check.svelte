<script lang="ts">
  import type { Snippet } from 'svelte'
  import Icon from './Icon.svelte'

  interface Props {
    checked?: boolean
    label?: string
    /** Casella di conferma a rischio: bordo danger. */
    risk?: boolean
    disabled?: boolean
    children?: Snippet
  }
  let { checked = $bindable(false), label, risk = false, disabled = false, children }: Props = $props()
</script>

<label class="ui-check" class:risk>
  <input type="checkbox" bind:checked {disabled} />
  <span class="bx">{#if checked}<Icon name="check" size={14} />{/if}</span>
  <span>{#if children}{@render children()}{:else}{label}{/if}</span>
</label>
