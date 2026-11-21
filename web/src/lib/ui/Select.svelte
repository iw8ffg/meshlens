<script lang="ts">
  import type { Snippet } from 'svelte'
  import type { HTMLSelectAttributes } from 'svelte/elements'

  interface Props extends Omit<HTMLSelectAttributes, 'children' | 'value'> {
    value?: string
    children: Snippet
  }
  let { value = $bindable(), children, class: cls = '', ...rest }: Props = $props()
</script>

<select class="ui-select {cls}" bind:value {...rest}>{@render children()}</select>
