<script lang="ts">
  import { untrack } from 'svelte'
  import { ApiError, applyPlan, configJob } from '../lib/api'
  import { MASK, pathLabel } from '../lib/config'
  import { prepareStatus } from '../lib/coverage'
  import { app, configJobs, setConfigJob } from '../lib/stores.svelte'
  import { t } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
  import type { CoveragePlan } from '../lib/types'
  import Button from '../lib/ui/Button.svelte'
  import Badge from '../lib/ui/Badge.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Check from '../lib/ui/Check.svelte'

  // Il genitore lo monta con {#key plan.plan_id}: la conferma di rischio non passa mai a un altro piano.
  let {
    plan,
    kind,
    oncancel,
    onfinished,
  }: { plan: CoveragePlan; kind: 'prepare' | 'restore'; oncancel: () => void; onfinished?: () => void } = $props()

  let understood = $state(false)
  let busy = $state(false)
  let error = $state('')
  let jobIds = $state<number[]>([])

  const risky = $derived(plan.steps.some((s) => s.preview.risky))
  const empty = $derived(plan.steps.every((s) => s.preview.changes.length === 0))
  const started = $derived(jobIds.length > 0)
  const status = $derived(
    prepareStatus({ steps: plan.steps, jobs: jobIds.map((id) => configJobs.get(id) ?? null) }, kind),
  )

  let notified = false
  $effect(() => {
    if (started && status.finished && !notified) {
      notified = true
      untrack(() => onfinished?.())  // il genitore puo' leggere e scrivere il proprio stato
    }
  })

  // Rilegge i lavori non terminati (il WebSocket puo' aver perso aggiornamenti)
  async function refresh() {
    for (const id of jobIds) {
      const cur = configJobs.get(id)
      if (cur && cur.status !== 'running') continue
      try {
        setConfigJob(await configJob(id))
      } catch {
        /* riprova al prossimo giro */
      }
    }
  }
  // dopo una riconnessione del WebSocket
  $effect(() => {
    void app.reconnects
    if (untrack(() => jobIds.length) > 0) untrack(refresh)
  })
  // ogni 5 s finche' qualche lavoro e' in corso
  $effect(() => {
    if (!started) return
    const t = setInterval(() => {
      if (!status.finished) void refresh()
    }, 5000)
    return () => clearInterval(t)
  })

  const show = (v: unknown) => {
    if (v === null || v === undefined) return '–'
    if (v === MASK) return MASK
    return typeof v === 'object' ? JSON.stringify(v) : String(v)
  }
  const roleOf = (role: string) => (role === 'mobile' ? t('coverage.role.mobile') : t('coverage.role.base'))

  async function apply() {
    busy = true
    error = ''
    try {
      const r = await applyPlan(plan.plan_id, risky && understood)
      for (const j of r.jobs) setConfigJob(j)
      jobIds = r.jobs.map((j) => j.id)
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('coverage.failedOp')
    } finally {
      busy = false
    }
  }
</script>

<div class="flow">
  <h3>{kind === 'prepare' ? t('coverage.flow.prepare') : t('coverage.flow.restore')}</h3>
  {#each plan.steps as s (s.node_id)}
    <div class="step">
      <div><b>{roleOf(s.role)}</b> <span class="ui-mono muted">{s.node_id}</span></div>
      {#if s.preview.changes.length === 0}
        <p class="muted">{t('coverage.flow.none')}</p>
      {:else}
        <div class="ui-tblwrap">
          <table class="ui-tbl">
            <thead><tr><th>{t('coverage.flow.field')}</th><th>{t('coverage.flow.current')}</th><th>{t('coverage.flow.new')}</th></tr></thead>
            <tbody>
              {#each s.preview.changes as c (c.path)}
                <tr class:risky={c.risky}>
                  <td class="wrap">
                    {pathLabel(c.path)}
                    {#if c.risky}<br /><Badge kind="danger" icon="alert">{t('coverage.flow.risky')}{c.reason ? `: ${translateServer(c.reason)}` : ''}</Badge>{/if}
                  </td>
                  <td class="wrap ui-mono">{show(c.old)}</td>
                  <td class="wrap ui-mono">{show(c.new)}</td>
                </tr>
              {/each}
            </tbody>
          </table>
        </div>
      {/if}
      <p class="muted">{t('coverage.flow.backup', { sections: s.preview.backup_sections.join(', ') || '–' })}</p>
    </div>
  {/each}

  {#if !started}
    {#if risky}
      <Check risk bind:checked={understood} label={t('coverage.flow.ack')} />
    {/if}
    <div class="btns">
      <Button kind="primary" disabled={busy || empty || (risky && !understood)} onclick={apply}>{t('coverage.flow.apply')}</Button>
      <Button onclick={oncancel}>{t('common.cancel')}</Button>
    </div>
  {:else}
    <ul class="prog" aria-label={t('coverage.flow.progress')}>
      {#each status.nodes as n (n.node_id)}
        <li class={n.state}><b>{n.role}</b>: {n.text}</li>
      {/each}
    </ul>
    <p class:err={status.failed} class="sum">{status.summary}</p>
    {#if status.finished}<div><Button onclick={oncancel}>{t('common.close')}</Button></div>{/if}
  {/if}
  {#if error}<Banner kind="danger" title={error} />{/if}
</div>

<style>
  .flow { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  .step { display: flex; flex-direction: column; gap: var(--space-2); }
  h3, p { margin: 0; }
  h3 { font: 600 15px/20px var(--font-sans); }
  .wrap { white-space: normal; word-break: break-all; padding-top: 6px; padding-bottom: 6px; height: auto; }
  tr.risky td { background: var(--danger-soft); }
  .err, li.failed { color: var(--danger); }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  .btns { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .prog { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-1); }
  li.ok { color: var(--ok); }
  li.mismatch { color: var(--warn); }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
