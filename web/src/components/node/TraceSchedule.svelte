<script lang="ts">
  // Segnaposto WP0: lo riempie WP5 (E14, traceroute automatici). Props fissate dal contratto §10.2.
  import type { Node } from '../../lib/types'

  interface Props {
    node: Node
  }
  let { node }: Props = $props()
</script>
