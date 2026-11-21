<script lang="ts">
  interface Props {
    width?: string
    tall?: boolean
  }
  let { width = '100%', tall = false }: Props = $props()
</script>

<!-- Segnaposto fisso, senza animazione continua. -->
<span class="ui-skel" class:tall style="width: {width}" aria-hidden="true"></span>
