<script lang="ts">
  import { onMount } from 'svelte'
  import { getCountries } from '../lib/api'
  import { app } from '../lib/stores.svelte'
  import { t } from '../lib/i18n/index.svelte'
  import { activeFilters, clearFilter, clearAllFilters } from '../lib/filters'
  import { countryName } from '../lib/format'
  import Icon from '../lib/ui/Icon.svelte'

  let { compact = false }: { compact?: boolean } = $props()

  let names = $state<Record<string, string>>({})

  onMount(async () => {
    try {
      const list = await getCountries()
      names = Object.fromEntries(list.map((c) => [c.code, c.name]))
    } catch {
      // senza nomi si mostra il codice
    }
  })

  const items = $derived(activeFilters(app.filter, (code) => countryName(code, names[code])))
</script>

{#if items.length > 0}
  <div class="af" class:compact>
    {#if !compact}<span class="lead">{t('nodes.activeFilters')}</span>{/if}
    {#each items as a (a.key)}
      <span class="ui-chip chip">
        {a.label}
        <button type="button" class="x" aria-label={t('nodes.removeFilter', { label: a.label })} onclick={() => (app.filter = clearFilter(app.filter, a.key))}>
          <Icon name="x" size={14} />
        </button>
      </span>
    {/each}
    <button type="button" class="ui-chip reset" onclick={() => (app.filter = clearAllFilters(app.filter))}>{t('nodes.clearFilters')}</button>
  </div>
{/if}

<style>
  .af {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2);
    padding: var(--space-3);
    border-bottom: 1px solid var(--line);
    font-size: 13px;
  }
  .af.compact {
    padding: 0;
    border-bottom: 0;
    justify-content: center;
  }
  .lead {
    color: var(--ink-muted);
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: var(--space-1);
  }
  .x {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border: 0;
    background: transparent;
    color: inherit;
    cursor: pointer;
    padding: 0;
    min-width: 24px;
    min-height: 24px;
    border-radius: var(--radius-pill);
  }
  .x:focus-visible,
  .reset:focus-visible {
    outline: 2px solid var(--focus-ring);
    outline-offset: 2px;
  }
  :global(.vp-phone) .af {
    font-size: 14px;
  }
  :global(.vp-phone) .chip,
  :global(.vp-phone) .reset {
    min-height: var(--touch-min);
  }
  :global(.vp-phone) .x {
    min-width: var(--touch-min);
    min-height: var(--touch-min);
  }
</style>
