<script lang="ts">
  import { onMount } from 'svelte'
  import { getJSON } from '../lib/api'
  import { flag } from '../lib/format'
  import { app } from '../lib/stores.svelte'

  type Country = { code: string; name: string; nodes: number }
  const AGES: [string, number | null][] = [
    ['Tutti', null],
    ['2 h', 2],
    ['24 h', 24],
    ['7 g', 168],
  ]

  let countries = $state<Country[]>([])
  let error = $state('')

  onMount(async () => {
    try {
      const list = await getJSON<Country[]>('/countries')
      countries = [...list].sort((a, b) => {
        if (a.code === 'none') return 1
        if (b.code === 'none') return -1
        return b.nodes - a.nodes
      })
    } catch {
      error = 'Elenco nazioni non disponibile'
    }
  })

  function toggle(code: string) {
    const c = app.filter.countries
    app.filter.countries = c.includes(code) ? c.filter((x) => x !== code) : [...c, code]
  }
</script>

<div class="filters">
  <input type="search" placeholder="Cerca nome o id…" aria-label="Cerca nodi" bind:value={app.filter.text} />
  <div class="row" role="group" aria-label="Ultimo contatto">
    {#each AGES as [label, h] (label)}
      <button class="chip" class:on={app.filter.maxAgeH === h} onclick={() => (app.filter.maxAgeH = h)}>{label}</button>
    {/each}
  </div>
  <details>
    <summary>Nazioni ({app.filter.countries.length === 0 ? 'tutte' : app.filter.countries.length})</summary>
    {#if error}<p class="err">{error}</p>{/if}
    <button class="chip" onclick={() => (app.filter.countries = [])}>Tutte</button>
    <ul>
      {#each countries as c (c.code)}
        <li>
          <label>
            <input type="checkbox" checked={app.filter.countries.includes(c.code)} onchange={() => toggle(c.code)} />
            <span>{c.code === 'none' ? '❔' : flag(c.code)} {c.name}</span>
            <span class="n">{c.nodes}</span>
          </label>
        </li>
      {/each}
    </ul>
  </details>
</div>

<style>
  .filters {
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    border-bottom: 1px solid #1f2937;
  }
  input[type='search'] {
    padding: 6px 8px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
  }
  .row {
    display: flex;
    gap: 6px;
  }
  .chip {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 999px;
    padding: 3px 10px;
    cursor: pointer;
  }
  .chip.on {
    background: #2563eb;
    border-color: #2563eb;
  }
  ul {
    list-style: none;
    margin: 6px 0 0;
    padding: 0;
    max-height: 200px;
    overflow: auto;
  }
  label {
    display: flex;
    gap: 6px;
    align-items: center;
    padding: 2px 0;
    cursor: pointer;
  }
  .n {
    margin-left: auto;
    color: #9ca3af;
    font-size: 12px;
  }
  .err {
    color: #f87171;
  }
</style>
