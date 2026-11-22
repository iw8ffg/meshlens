<script lang="ts">
  import { NODE_SORTS, type NodeSortKey } from '../lib/nodesort'
  import { t } from '../lib/i18n/index.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Select from '../lib/ui/Select.svelte'

  let { value, hasOrigin, onchange }: { value: NodeSortKey; hasOrigin: boolean; onchange: (k: NodeSortKey) => void } = $props()
  const uid = $props.id()
  // Senza origine «Distanza» non e' selezionabile: l'elenco ordina per recente, quindi lo mostra anche il controllo
  // (anche quando la scelta arriva salvata da una sessione precedente).
  const shown = $derived<NodeSortKey>(!hasOrigin && value === 'distance' ? 'recent' : value)

  function pick(e: Event) {
    onchange((e.currentTarget as HTMLSelectElement).value as NodeSortKey)
  }
</script>

<div class="sortbar">
  <Field label={t('nodes.sortBy')} for="{uid}-sort" hint={hasOrigin ? undefined : t('nodes.sortNeedOrigin')}>
    {#snippet children({ describedby })}
      <Select id="{uid}-sort" aria-describedby={describedby} value={shown} onchange={pick}>
        {#each NODE_SORTS as s (s.key)}
          <option value={s.key} disabled={s.key === 'distance' && !hasOrigin}>{t(s.labelKey)}</option>
        {/each}
      </Select>
    {/snippet}
  </Field>
</div>

<style>
  .sortbar {
    padding: var(--space-2) var(--space-3);
    border-bottom: 1px solid var(--line);
  }
</style>
