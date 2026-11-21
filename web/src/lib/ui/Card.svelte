<script lang="ts">
  import type { Snippet } from 'svelte'

  interface Props {
    flat?: boolean
    risk?: boolean
    children: Snippet
  }
  let { flat = false, risk = false, children }: Props = $props()
</script>

<div class="ui-card" class:flat class:risk>{@render children()}</div>
