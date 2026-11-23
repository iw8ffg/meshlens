<script lang="ts">
  // WP4 (E13): comandi admin con conferma (riavvio, ora, azzeramento elenco nodi, spegnimento).
  // Verso un nodo remoto solo se ha la chiave pubblica di questa radio tra le admin key.
  import { ApiError, readConfig } from '../lib/api'
  import { getAdminStatus, runAdminCommand, type AdminCommand } from '../lib/config'
  import { formatDate } from '../lib/format'
  import { t } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
  import { configJobs } from '../lib/stores.svelte'
  import type { AdminStatus, ConfigJob } from '../lib/types'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import type { IconName } from '../lib/ui/icons'

  let {
    nodeId,
    radioId,
    local,
    lock,
    onjob,
    onkeytab,
  }: {
    nodeId: string
    radioId: string | null
    local: boolean
    lock: boolean
    onjob: (j: ConfigJob) => void
    /** Apre la scheda «Chiave admin» del pannello. */
    onkeytab?: () => void
  } = $props()

  let status = $state<AdminStatus | null>(null)
  let error = $state('')
  let busy = $state(false)
  let pending = $state<AdminCommand | null>(null)
  let verifyJob = $state<number | null>(null)
  let sentAt = $state(0)

  const authorized = $derived(local || status?.authorized === true)

  async function load() {
    error = ''
    try {
      status = await getAdminStatus(nodeId, radioId)
    } catch (e) {
      status = null
      error = e instanceof ApiError ? e.message : t('config.cmd.failed')
    }
  }

  const key = $derived(`${nodeId}|${radioId ?? ''}`)
  $effect(() => {
    void key
    void load()
  })

  // finita la lettura della sezione Sicurezza: si ricontrolla l'autorizzazione
  const verifyDone = $derived(verifyJob !== null && configJobs.get(verifyJob)?.status !== 'running' && configJobs.has(verifyJob))
  $effect(() => {
    if (!verifyDone) return
    verifyJob = null
    void load()
  })

  async function verify() {
    busy = true
    error = ''
    try {
      const j = await readConfig(nodeId, radioId ? { radio_id: radioId, sections: ['security'] } : { sections: ['security'] })
      onjob(j)
      verifyJob = j.id
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('config.cmd.failed')
    } finally {
      busy = false
    }
  }

  function ask(c: AdminCommand) {
    sentAt = Date.now() / 1000
    pending = c
  }

  async function run() {
    const c = pending
    pending = null
    if (!c) return
    busy = true
    error = ''
    try {
      onjob(await runAdminCommand(nodeId, c, radioId))
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('config.cmd.failed')
    } finally {
      busy = false
    }
  }

  const COMMANDS: { id: AdminCommand; icon: IconName }[] = [
    { id: 'reboot', icon: 'refresh' },
    { id: 'set_time', icon: 'clock' },
    { id: 'nodedb_reset', icon: 'trash' },
    { id: 'shutdown', icon: 'power' },
  ]
  const label = (c: AdminCommand) => t(`config.cmd.${c}` as 'config.cmd.reboot')
  const body = (c: AdminCommand) =>
    c === 'set_time' ? t('config.cmd.set_time.body', { time: formatDate(sentAt) }) : t(`config.cmd.${c}.body` as 'config.cmd.reboot.body')
</script>

<section class="ca">
  <h3>{t('config.cmd.title')}</h3>
  <p class="muted">{t('config.cmd.intro')}</p>
  {#if !local && status && status.authorized !== true}
    <Banner kind="warn" title={translateServer(status.reason ?? '')}>
      {#snippet action()}
        <Button disabled={lock || busy} onclick={verify}>{t('config.cmd.verify')}</Button>
        {#if onkeytab}<Button kind="ghost" icon="key" onclick={onkeytab}>{t('config.cmd.keyTab')}</Button>{/if}
      {/snippet}
    </Banner>
  {/if}
  <div class="cmds">
    {#each COMMANDS as c (c.id)}
      <Button kind={c.id === 'shutdown' || c.id === 'nodedb_reset' ? 'danger' : 'default'} icon={c.icon} disabled={lock || busy || !authorized} onclick={() => ask(c.id)}>{label(c.id)}</Button>
    {/each}
  </div>
  {#if error}<Banner kind="danger" title={error} />{/if}
</section>

<Modal
  open={pending !== null}
  title={pending ? t('config.cmd.confirmTitle', { cmd: label(pending) }) : ''}
  danger={pending === 'shutdown' || pending === 'nodedb_reset'}
  risk={pending === 'shutdown' || pending === 'nodedb_reset'}
  riskLabel={pending === 'shutdown' ? (local ? t('config.cmd.shutdown.riskLocal') : t('config.cmd.shutdown.riskRemote')) : t('config.cmd.nodedb_reset.risk')}
  confirmLabel={pending ? label(pending) : ''}
  onconfirm={run}
  oncancel={() => (pending = null)}
>
  <p>{pending ? body(pending) : ''}</p>
  {#if pending === 'shutdown' && !local}<p>{t('config.cmd.shutdown.remote')}</p>{/if}
</Modal>

<style>
  .ca {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  h3 {
    margin: var(--space-2) 0 0;
    font: 600 14px/20px var(--font-sans);
  }
  .muted {
    margin: 0;
    color: var(--ink-muted);
    font-size: 13px;
  }
  .cmds {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
  }
  :global(.vp-phone) .muted {
    font-size: 14px;
  }
  :global(.vp-phone) .cmds :global(.ui-btn) {
    min-height: 44px;
  }
</style>
