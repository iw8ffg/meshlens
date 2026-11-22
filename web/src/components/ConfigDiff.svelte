<script lang="ts">
  import { MASK, pathLabel } from '../lib/config'
  import { t } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
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
  <h3>{t('config.diff.title')}</h3>
  {#if preview.changes.length === 0}
    <p class="muted">{t('config.diff.none')}</p>
  {:else}
    <div class="ui-tblwrap">
      <table class="ui-tbl">
        <thead>
          <tr><th>{t('config.diff.field')}</th><th>{t('config.diff.current')}</th><th>{t('config.diff.new')}</th></tr>
        </thead>
        <tbody>
          {#each preview.changes as c (c.path)}
            <tr class:risky={c.risky}>
              <td class="wrap">
                {pathLabel(c.path)}
                {#if pathLabel(c.path) !== c.path}<br /><small class="muted ui-mono">{c.path}</small>{/if}
                {#if c.risky}<br /><Badge kind="danger" icon="alert">{t('config.diff.risky')}{c.reason ? `: ${translateServer(c.reason)}` : ''}</Badge>{/if}
              </td>
              <td class="wrap ui-mono">{show(c.old)}</td>
              <td class="wrap ui-mono">{show(c.new)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
  <p class="muted">{t('config.diff.backup', { sections: preview.backup_sections.join(', ') || '–' })}</p>
  <div class="btns">
    <Button
      kind="primary"
      disabled={busy || preview.changes.length === 0}
      onclick={() => (preview.risky ? (confirming = true) : onapply(false))}
    >
      {t('config.diff.apply')}
    </Button>
    <Button onclick={oncancel}>{t('common.cancel')}</Button>
  </div>
</div>

<!-- Una conferma nuova per ogni anteprima: la casella non passa mai a un'altra modifica -->
{#key preview.preview_id}
  <Modal
    open={confirming}
    risk
    title={t('config.diff.riskTitle')}
    riskLabel={t('config.diff.riskLabel')}
    confirmLabel={t('config.diff.applyAnyway')}
    onconfirm={() => {
      confirming = false
      onapply(true)
    }}
    oncancel={() => (confirming = false)}
  >
    <p>{t('config.diff.riskBody')}</p>
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
