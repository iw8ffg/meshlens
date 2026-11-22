<script lang="ts">
  import { untrack } from 'svelte'
  import { ApiError } from '../lib/api'
  import { timeAgo } from '../lib/format'
  import { t } from '../lib/i18n/index.svelte'
  import {
    DEFAULT_WINDOW_MIN, WINDOW_OPTIONS, defaultChannel, isLikelyPublic, jobText, sfJobs, sfProbe, sfRequest, sfRouters,
    type SfRouter,
  } from '../lib/storeforward'
  import { adoptSfJobs, sf, setSfRouters } from '../lib/storeforward.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import Progress from '../lib/ui/Progress.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import Select from '../lib/ui/Select.svelte'
  import type { Radio } from '../lib/types'

  interface Props {
    radio: Radio
    onclose?: () => void
  }
  let { radio, onclose }: Props = $props()

  const OTHER = '__other'
  const NODE_ID = /^![0-9a-fA-F]{8}$/

  const routers = $derived(sf.routers.filter((r) => r.radio_id === radio.id))
  let routerSel = $state('')
  let otherId = $state('')
  let windowMin = $state(String(DEFAULT_WINDOW_MIN))
  let channel = $state(String(untrack(() => defaultChannel(radio.channels))))
  let busy = $state(false)
  let error = $state('')
  let info = $state('')
  let jobId = $state<string | null>(null)

  const routerId = $derived((routerSel === OTHER ? otherId.trim() : routerSel).toLowerCase())
  const idValid = $derived(NODE_ID.test(routerId))
  const chosen = $derived(radio.channels.find((c) => String(c.index) === channel))
  const publicWarn = $derived(chosen ? isLikelyPublic(chosen) : false)
  const job = $derived(jobId ? sf.jobs[jobId] ?? null : null)
  const active = $derived(job !== null && (job.status === 'waiting' || job.status === 'receiving'))
  const percent = $derived(
    job && job.expected ? Math.min(100, Math.round(((job.received + job.duplicates) / job.expected) * 100)) : null,
  )

  // Seleziona il primo router noto quando l'elenco arriva; scrive solo routerSel.
  $effect(() => {
    if (routerSel === '' && routers.length > 0) routerSel = routers[0].id
  })

  $effect(() => {
    sfRouters().then(setSfRouters).catch(() => {})
  })

  // Riaperta la finestra, riprende il recupero ancora in corso per questa radio (se c'e').
  $effect(() => {
    sfJobs()
      .then((list) => {
        const id = adoptSfJobs(list, untrack(() => radio.id))
        if (id && jobId === null) jobId = id
      })
      .catch(() => {})
  })

  function routerLabel(r: SfRouter): string {
    const name = r.name || r.id
    const seen = timeAgo(r.last_seen, Date.now() / 1000)
    return r.stats
      ? t('sf.routerLabelStats', { name, seen, saved: r.stats.messages_saved, max: r.stats.messages_max })
      : t('sf.routerLabel', { name, seen })
  }

  function msg(e: unknown): string {
    return e instanceof ApiError ? e.message : t('sf.failed')
  }

  async function probe() {
    if (busy) return
    if (!idValid) {
      error = t('sf.badId')
      return
    }
    busy = true
    error = ''
    info = ''
    try {
      await sfProbe({ radio_id: radio.id, router_id: routerId, channel_index: Number(channel) })
      info = t('sf.probeSent')
    } catch (e) {
      error = msg(e)
    } finally {
      busy = false
    }
  }

  async function start() {
    if (busy || active) return
    if (!idValid) {
      error = t('sf.badId')
      info = ''
      return
    }
    busy = true
    error = ''
    info = ''
    try {
      const j = await sfRequest({
        radio_id: radio.id, router_id: routerId, window_min: Number(windowMin), channel_index: Number(channel),
      })
      sf.jobs[j.id] = j
      jobId = j.id
    } catch (e) {
      error = msg(e)
    } finally {
      busy = false
    }
  }
</script>

<Modal open title={t('sf.title')} confirmLabel={t('sf.recover')} cancelLabel={t('common.close')} onconfirm={start} oncancel={() => onclose?.()}>
  <div class="sf">
    <Field label={t('sf.router')} for="sf-router">
      {#snippet children()}
        <Select id="sf-router" bind:value={routerSel} disabled={active}>
          {#each routers as r (r.id)}
            <option value={r.id}>{routerLabel(r)}</option>
          {/each}
          <option value={OTHER}>{t('sf.other')}</option>
        </Select>
      {/snippet}
    </Field>
    {#if routerSel === OTHER || routers.length === 0}
      <Field label={t('sf.otherId')} for="sf-other" hint={t('sf.otherHint')}>
        {#snippet children()}
          <input id="sf-other" class="ui-input ui-mono" bind:value={otherId} maxlength="9" placeholder="!a1b2c3d4" disabled={active}
            oninput={() => { if (routerSel !== OTHER) routerSel = OTHER }} />
        {/snippet}
      </Field>
    {/if}
    <div>
      <Button icon="refresh" disabled={busy || active || !idValid} onclick={probe}>{t('sf.probe')}</Button>
    </div>

    <Field label={t('sf.window')}>
      {#snippet children()}
        <Segmented
          label={t('sf.windowAria')}
          items={WINDOW_OPTIONS.map((o) => ({ value: String(o.min), label: o.label }))}
          bind:value={windowMin}
        />
      {/snippet}
    </Field>

    <Field label={t('sf.channel')} for="sf-channel">
      {#snippet children()}
        <Select id="sf-channel" bind:value={channel} disabled={active}>
          {#each radio.channels as c (c.index)}
            <option value={String(c.index)}>{c.name || t('sf.channelN', { n: c.index })}</option>
          {/each}
        </Select>
      {/snippet}
    </Field>
    {#if publicWarn}
      <Banner kind="warn" title={t('sf.publicWarn')} />
    {/if}

    <p class="note">{t('sf.note')}</p>

    {#if error}<Banner kind="danger" title={error} />{/if}
    {#if info}<Banner kind="info" title={info} />{/if}

    {#if job}
      <div class="job" role="status">
        <span class:fail={job.status === 'failed'}>{jobText(job)}</span>
        {#if job.status === 'waiting'}
          <div class="ui-progress indet" role="progressbar" aria-label={t('sf.job.waiting')}><i></i></div>
        {:else if job.status === 'receiving' && percent !== null}
          <Progress value={percent} label={t('sf.progress')} />
        {/if}
      </div>
    {/if}
  </div>
</Modal>

<style>
  .sf { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  .note { margin: 0; color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  .job { display: flex; flex-direction: column; gap: var(--space-2); font: 500 14px/20px var(--font-sans); }
  .fail { color: var(--danger); }
  .indet { overflow: hidden; }
  .indet i { display: block; width: 40%; animation: sf-slide 1.4s ease-in-out infinite; }
  :global(.vp-phone) .note { font-size: 14px; line-height: 20px; }
  @keyframes sf-slide { from { transform: translateX(-100%); } to { transform: translateX(250%); } }
  @media (prefers-reduced-motion: reduce) { .indet i { animation: none; width: 100%; } }
</style>
