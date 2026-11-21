<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    pressed?: boolean
    label?: string
    children?: Snippet
    onclick?: () => void
  }
  let { pressed = $bindable(false), label, children, onclick }: Props = $props()
  function click() {
    pressed = !pressed
    onclick?.()
  }
</script>

<button type="button" class="ui-chip" aria-pressed={pressed} onclick={click}>{#if children}{@render children()}{:else}{label}{/if}</button>
