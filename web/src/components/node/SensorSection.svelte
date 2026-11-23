<script lang="ts">
  // Segnaposto WP0: lo riempie WP2 (E9, sensori). Props fissate dal contratto §10.2.
  import type { Node } from '../../lib/types'

  interface Props {
    node: Node
  }
  let { node }: Props = $props()
</script>
