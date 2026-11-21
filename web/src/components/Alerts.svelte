<script lang="ts">
  import { app } from '../lib/stores.svelte'
  import type { Alert } from '../lib/types'

  let { onpick }: { onpick: (id: string) => void } = $props()
  let open = $state(false)

  function text(a: Alert): string {
    return a.kind === 'battery_low'
      ? `Batteria ${Math.round(a.value)}% — ${a.node_name}`
      : `Silenzioso da ${Math.round(a.value)} h — ${a.node_name}`
  }
</script>

{#if app.alerts.length > 0}
  <div class="alerts">
    <button class="head" aria-expanded={open} onclick={() => (open = !open)}>
      ⚠ {app.alerts.length} {app.alerts.length === 1 ? 'avviso' : 'avvisi'}
    </button>
    {#if open}
      <ul>
        {#each app.alerts as a (a.key)}
          <li><button onclick={() => onpick(a.node_id)}>{text(a)}</button></li>
        {/each}
      </ul>
    {/if}
  </div>
{/if}

<style>
  .alerts {
    background: #422006;
    border-bottom: 1px solid #854d0e;
    font-size: 13px;
  }
  button {
    display: block;
    width: 100%;
    text-align: left;
    background: none;
    border: 0;
    color: #fde68a;
    font: inherit;
    padding: 6px 12px;
    cursor: pointer;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
  }
  li button {
    padding-left: 28px;
    border-top: 1px solid #854d0e;
  }
</style>
