<script lang="ts">
  import { MASK, pathLabel } from '../lib/config'
  import type { ConfigPreview } from '../lib/types'
  import Badge from '../lib/ui/Badge.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Modal from '../lib/ui/Modal.svelte'

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

  let confirming = $state(false)

  const show = (v: unknown) => {
    if (v === null || v === undefined) return '–'
    if (v === MASK) return MASK
    return typeof v === 'object' ? JSON.stringify(v) : String(v)
  }
</script>

<div class="diff">
  <h3>Rivedi modifiche</h3>
  {#if preview.changes.length === 0}
    <p class="muted">Nessuna modifica.</p>
  {:else}
    <div class="ui-tblwrap">
      <table class="ui-tbl">
        <thead>
          <tr><th>Campo</th><th>Attuale</th><th>Nuovo</th></tr>
        </thead>
        <tbody>
          {#each preview.changes as c (c.path)}
            <tr class:risky={c.risky}>
              <td class="wrap">
                {pathLabel(c.path)}
                {#if pathLabel(c.path) !== c.path}<br /><small class="muted ui-mono">{c.path}</small>{/if}
                {#if c.risky}<br /><Badge kind="danger" icon="alert">A rischio{c.reason ? `: ${c.reason}` : ''}</Badge>{/if}
              </td>
              <td class="wrap ui-mono">{show(c.old)}</td>
              <td class="wrap ui-mono">{show(c.new)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
  <p class="muted">Prima di scrivere viene salvata una copia di: {preview.backup_sections.join(', ') || '–'}.</p>
  <div class="btns">
    <Button
      kind="primary"
      disabled={busy || preview.changes.length === 0}
      onclick={() => (preview.risky ? (confirming = true) : onapply(false))}
    >
      Applica
    </Button>
    <Button onclick={oncancel}>Annulla</Button>
  </div>
</div>

<!-- Una conferma nuova per ogni anteprima: la casella non passa mai a un'altra modifica -->
{#key preview.preview_id}
  <Modal
    open={confirming}
    risk
    title="Modifica a rischio"
    riskLabel="Ho capito che questa modifica può isolare il nodo"
    confirmLabel="Applica comunque"
    onconfirm={() => {
      confirming = false
      onapply(true)
    }}
    oncancel={() => (confirming = false)}
  >
    <p>Una o più modifiche possono far perdere il contatto con il nodo o isolarlo dalla rete. Prima di scrivere viene comunque salvata una copia.</p>
  </Modal>
{/key}

<style>
  .diff { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-3); margin: var(--space-2) 0; border: 1px solid var(--line); border-radius: var(--radius-lg); background: var(--surface); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .wrap { white-space: normal; word-break: break-all; height: auto; padding-top: 6px; padding-bottom: 6px; }
  tr.risky td { background: var(--danger-soft); }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  .btns { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
