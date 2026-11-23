<script lang="ts">
  // Segnaposto WP0: lo riempie WP3 (E16, contatto ATAK). Props fissate dal contratto §10.2.
  import type { Node } from '../../lib/types'

  interface Props {
    node: Node
  }
  let { node }: Props = $props()
</script>
