<script lang="ts">
  import { app } from '../stores.svelte'
  import { brokerLabel } from '../brokers'
  import Badge from './Badge.svelte'

  let { id }: { id: string | null | undefined } = $props()
  const label = $derived(brokerLabel(id, app.status?.mqtt.brokers))
</script>

{#if label}<Badge>{label}</Badge>{/if}
