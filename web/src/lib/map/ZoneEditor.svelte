<script lang="ts">
  // Segnaposto WP0: lo riempie WP3 (editor di una zona sulla mappa), lo usa WP2 (regole geofence).
  // Poligono come coppie [lon, lat], chiuso implicitamente, almeno 3 punti. Props fissate dal contratto §10.2.
  let {
    value = $bindable<[number, number][] | null>(null),
    onchange,
  }: { value?: [number, number][] | null; onchange?: (polygon: [number, number][] | null) => void } = $props()
</script>
