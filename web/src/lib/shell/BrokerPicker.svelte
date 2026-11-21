<script lang="ts">
  import Field from '../ui/Field.svelte'
  import Select from '../ui/Select.svelte'
  import type { BrokerStatus } from '../types'

  let { id, brokers, value = $bindable('') }: { id: string; brokers: BrokerStatus[]; value: string } = $props()

  const active = $derived(brokers.filter((b) => b.enabled))
</script>

{#if active.length > 1}
  <Field label="Broker" for={id}>
    {#snippet children({ describedby })}
      <Select {id} bind:value aria-describedby={describedby}>
        {#each active as b (b.id)}<option value={b.id}>{b.connected ? b.name : `${b.name} (non connesso)`}</option>{/each}
      </Select>
    {/snippet}
  </Field>
{/if}
