<script lang="ts">
  // Segnaposto WP0: lo riempie WP1 (azione suggerita negli stati vuoti). Props fissate dal contratto §10.2.
  interface Props {
    kind: 'nodes' | 'network' | 'radios' | 'chat'
  }
  let { kind }: Props = $props()
</script>
