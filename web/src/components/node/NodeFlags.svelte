<script lang="ts">
  // Segnaposto WP0: lo riempie WP4 (E3/E12, flag del nodo vicino a stella e mio). Props fissate dal contratto §10.2.
  import type { Node } from '../../lib/types'

  interface Props {
    node: Node
  }
  let { node }: Props = $props()
</script>
