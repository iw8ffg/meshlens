<script module lang="ts">
  export interface Column {
    key: string
    label: string
    /** Colonna numerica: a destra, in mono. */
    num?: boolean
    /** Colonna fissa a sinistra (la prima, «Nodo»). */
    fix?: boolean
    sortable?: boolean
  }
</script>

<script lang="ts" generics="T">
  import type { Snippet } from 'svelte'
  import Icon from './Icon.svelte'

  interface Props {
    columns: Column[]
    rows: T[]
    rowKey: (row: T) => string
    cell: Snippet<[T, Column]>
    sortKey?: string
    sortDir?: 'asc' | 'desc'
    onsort?: (key: string) => void
    selectedKey?: string | null
    onrowclick?: (row: T) => void
    caption?: string
  }
  let { columns, rows, rowKey, cell, sortKey, sortDir = 'asc', onsort, selectedKey = null, onrowclick, caption }: Props = $props()
</script>

<!-- Su telefono la tabella scorre in orizzontale nel suo contenitore; la colonna fissa resta ferma. -->
<div class="ui-tblwrap">
  <table class="ui-tbl">
    {#if caption}<caption class="ui-sr">{caption}</caption>{/if}
    <thead>
      <tr>
        {#each columns as c (c.key)}
          <th class:num={c.num} class:fix={c.fix} class:sorted={sortKey === c.key} scope="col" aria-sort={sortKey === c.key ? (sortDir === 'asc' ? 'ascending' : 'descending') : undefined}>
            {#if c.sortable && onsort}
              <button type="button" onclick={() => onsort(c.key)}>
                {c.label}
                {#if sortKey === c.key}<Icon name={sortDir === 'asc' ? 'chevU' : 'chevD'} size={14} />{/if}
              </button>
            {:else}
              {c.label}
            {/if}
          </th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each rows as r (rowKey(r))}
        <tr class:sel={selectedKey === rowKey(r)} onclick={onrowclick ? () => onrowclick(r) : undefined}>
          {#each columns as c (c.key)}
            <td class:num={c.num} class:fix={c.fix}>{@render cell(r, c)}</td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
