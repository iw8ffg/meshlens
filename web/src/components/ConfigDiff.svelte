<script lang="ts">
  import { MASK, pathLabel } from '../lib/config'
  import type { ConfigPreview } from '../lib/types'

  let {
    preview,
    busy = false,
    onapply,
    oncancel,
  }: {
    preview: ConfigPreview
    busy?: boolean
    onapply: (confirmRisky: boolean) => void
    oncancel: () => void
  } = $props()

  let understood = $state(false)

  const show = (v: unknown) => {
    if (v === null || v === undefined) return '–'
    if (v === MASK) return MASK
    return typeof v === 'object' ? JSON.stringify(v) : String(v)
  }
</script>

<div class="diff">
  <h4>Rivedi modifiche</h4>
  {#if preview.changes.length === 0}
    <p class="muted">Nessuna modifica.</p>
  {:else}
    <table>
      <thead>
        <tr><th>Campo</th><th>Attuale</th><th>Nuovo</th></tr>
      </thead>
      <tbody>
        {#each preview.changes as c (c.path)}
          <tr class:risky={c.risky}>
            <td>
              {pathLabel(c.path)}
              {#if pathLabel(c.path) !== c.path}<br /><small class="muted">{c.path}</small>{/if}
              {#if c.risky}<br /><small class="why">A rischio{c.reason ? `: ${c.reason}` : ''}</small>{/if}
            </td>
            <td>{show(c.old)}</td>
            <td>{show(c.new)}</td>
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
  <p class="muted">Prima di scrivere viene salvata una copia di: {preview.backup_sections.join(', ') || '–'}.</p>
  {#if preview.risky}
    <label class="ack">
      <input type="checkbox" bind:checked={understood} />
      Ho capito che questa modifica può isolare il nodo
    </label>
  {/if}
  <div class="btns">
    <button
      class="go"
      disabled={busy || preview.changes.length === 0 || (preview.risky && !understood)}
      onclick={() => onapply(preview.risky && understood)}
    >
      Applica
    </button>
    <button onclick={oncancel}>Annulla</button>
  </div>
</div>

<style>
  .diff {
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 8px;
    margin: 8px 0;
  }
  h4 {
    margin: 0 0 6px;
  }
  table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  th,
  td {
    text-align: left;
    padding: 4px;
    border-bottom: 1px solid #1f2937;
    vertical-align: top;
    word-break: break-all;
  }
  tr.risky td {
    background: rgba(239, 68, 68, 0.15);
  }
  .why {
    color: #f87171;
  }
  .muted {
    color: #9ca3af;
    font-size: 12px;
  }
  .ack {
    display: flex;
    gap: 8px;
    align-items: center;
    color: #f87171;
    margin: 8px 0;
  }
  .btns {
    display: flex;
    gap: 6px;
    margin-top: 6px;
  }
  button {
    font: inherit;
    padding: 6px 12px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 4px;
    cursor: pointer;
  }
  button.go {
    background: #2563eb;
    border-color: #2563eb;
    color: #fff;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
</style>
