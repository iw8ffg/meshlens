<script lang="ts">
  import { onMount } from 'svelte'
  import { getCountries } from '../lib/api'
  import { app } from '../lib/stores.svelte'
  import { AGE_OPTIONS, SOURCE_OPTIONS, toggleIn } from '../lib/nodes'
  import Flag from '../lib/ui/Flag.svelte'
  import Icon from '../lib/ui/Icon.svelte'
  import Check from '../lib/ui/Check.svelte'
  import Button from '../lib/ui/Button.svelte'

  type Country = { code: string; name: string; nodes: number }

  let countries = $state<Country[]>([])
  let error = $state('')

  async function loadCountries() {
    error = ''
    try {
      const list = await getCountries()
      countries = [...list].sort((a, b) => {
        if (a.code === 'none') return 1
        if (b.code === 'none') return -1
        return b.nodes - a.nodes
      })
    } catch {
      error = 'Elenco nazioni non disponibile'
    }
  }

  onMount(loadCountries)

  const countryLabel = $derived(app.filter.countries.length === 0 ? 'tutte' : String(app.filter.countries.length))
</script>

<div class="filters">
  <div class="search">
    <Icon name="search" size={18} />
    <input class="ui-input" type="search" placeholder="Cerca nome, id, modello o ruolo…" aria-label="Cerca nodi" bind:value={app.filter.text} />
  </div>
  <div class="row" role="group" aria-label="Ultimo contatto">
    {#each AGE_OPTIONS as o (o.label)}
      <button type="button" class="ui-chip" aria-pressed={app.filter.maxAgeH === o.hours} onclick={() => (app.filter.maxAgeH = o.hours)}>{o.label}</button>
    {/each}
  </div>
  <div class="row" role="group" aria-label="Fonte">
    {#each SOURCE_OPTIONS as o (o.value)}
      <button type="button" class="ui-chip" aria-pressed={app.filter.sources.includes(o.value)} onclick={() => (app.filter.sources = toggleIn(app.filter.sources, o.value))}>{o.label}</button>
    {/each}
  </div>
  <div class="row" role="group" aria-label="Preferiti">
    <button type="button" class="ui-chip" aria-pressed={!!app.filter.favorites} onclick={() => (app.filter.favorites = !app.filter.favorites)}>Preferiti</button>
  </div>
  <Check bind:checked={app.filter.links} label="Collegamenti" />
  <details>
    <summary>Nazioni ({countryLabel})</summary>
    {#if error}<p class="err">{error} <Button onclick={loadCountries}>Riprova</Button></p>{/if}
    <div class="row wrap">
      <button type="button" class="ui-chip" aria-pressed={app.filter.countries.length === 0} onclick={() => (app.filter.countries = [])}>Tutte</button>
      {#each countries as c (c.code)}
        <button type="button" class="ui-chip" aria-pressed={app.filter.countries.includes(c.code)} onclick={() => (app.filter.countries = toggleIn(app.filter.countries, c.code))}>
          {#if c.code !== 'none'}<Flag code={c.code} name={c.name} />{/if}{c.code === 'none' ? 'Sconosciuta' : c.name}
          <span class="n">{c.nodes}</span>
        </button>
      {/each}
    </div>
  </details>
</div>

<style>
  .filters {
    padding: var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
    border-bottom: 1px solid var(--line);
  }
  .search {
    position: relative;
    display: flex;
    align-items: center;
    color: var(--ink-muted);
  }
  .search :global(.ui-ic) {
    position: absolute;
    left: var(--space-3);
    pointer-events: none;
  }
  .search .ui-input {
    padding-left: 38px;
  }
  .row {
    display: flex;
    gap: var(--space-2);
    flex-wrap: wrap;
  }
  .row.wrap {
    max-height: 220px;
    overflow: auto;
    margin-top: var(--space-2);
  }
  summary {
    min-height: var(--touch-min);
    display: flex;
    align-items: center;
    cursor: pointer;
    color: var(--ink);
    font: 600 14px/20px var(--font-sans);
  }
  .n {
    font-family: var(--font-mono);
    color: var(--ink-muted);
    font-size: 12px;
  }
  .err {
    color: var(--danger);
    margin: 0;
  }
  :global(.vp-phone) .n {
    font-size: 14px;
  }
</style>
