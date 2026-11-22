<script lang="ts">
  import { ApiError, coverageCheck, preparePlan, startCoverage } from '../lib/api'
  import { checklist, validInterval } from '../lib/coverage'
  import { app, coverage } from '../lib/stores.svelte'
  import { t } from '../lib/i18n/index.svelte'
  import type { CoverageCheck, CoverageMode, CoveragePlan } from '../lib/types'
  import CoveragePlanFlow from './CoveragePlanFlow.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Check from '../lib/ui/Check.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Icon from '../lib/ui/Icon.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import Select from '../lib/ui/Select.svelte'

  let { onprepared }: { onprepared?: () => void } = $props()

  const connected = $derived(app.radios.filter((r) => r.state === 'connected'))
  const radioNodeIds = $derived(new Set(app.radios.map((r) => r.my_node_id).filter((x): x is string => !!x)))
  let radioPick = $state('')
  let query = $state('')
  let mobilePick = $state('')
  let mode = $state<CoverageMode>('rangetest')
  let interval = $state(30)
  let check = $state<CoverageCheck | null>(null)
  let busy = $state(false)
  let error = $state('')
  let askApprox = $state('')
  let showHelp = $state(false)
  let privateChannel = $state(false)
  let plan = $state<CoveragePlan | null>(null)
  let prepBusy = $state(false)
  let prepError = $state('')

  async function prepare() {
    prepBusy = true
    prepError = ''
    try {
      plan = await preparePlan({ radio_id: radioId, mobile_id: mobileId, interval_s: interval, private_channel: privateChannel })
    } catch (e) {
      prepError = e instanceof Error ? e.message : t('coverage.error')
    } finally {
      prepBusy = false
    }
  }

  // Radio di base: la prima collegata, se quella scelta sparisce (derivato, nessun effetto)
  const radioId = $derived(connected.some((r) => r.id === radioPick) ? radioPick : (connected[0]?.id ?? ''))

  const label = (n: { long_name: string | null; short_name: string | null; id: string }) =>
    `${n.long_name || n.short_name || n.id} (${n.id})`

  const candidates = $derived.by(() => {
    const all = [...app.nodes.values()].filter((n) => !n.is_local_radio && !radioNodeIds.has(n.id))
    const q = query.trim().toLowerCase()
    if (q) {
      return all
        .filter((n) => `${n.long_name ?? ''} ${n.short_name ?? ''} ${n.id}`.toLowerCase().includes(q))
        .slice(0, 30)
    }
    const mine = all.filter((n) => n.is_mine)
    return mine.length ? mine : all.slice(0, 30)
  })

  // Il nodo scelto deve restare tra i candidati
  const mobileId = $derived(candidates.some((n) => n.id === mobilePick) ? mobilePick : (candidates[0]?.id ?? ''))

  const steps = $derived(checklist(check, mode))
  const hasActive = $derived(coverage.sessions.some((s) => s.ended === null))
  const canStart = $derived(check?.gps_ok === true && check.radio_connected && !busy && !!radioId && !!mobileId && !hasActive && validInterval(interval))

  // Controllo ogni 5 s
  $effect(() => {
    const r = radioId
    const m = mobileId
    check = null
    askApprox = ''
    if (!r || !m) return
    let live = true
    const run = () =>
      coverageCheck(r, m)
        .then((c) => {
          if (live) check = c
        })
        .catch(() => {
          if (live) check = null
        })
    run()
    const t = setInterval(run, 5000)
    return () => {
      live = false
      clearInterval(t)
    }
  })

  async function start(accept: boolean) {
    busy = true
    error = ''
    askApprox = ''
    try {
      const s = await startCoverage({
        radio_id: radioId,
        mobile_id: mobileId,
        mode,
        interval_s: interval,
        ...(check?.base_position ? { base_lat: check.base_position.lat, base_lon: check.base_position.lon } : {}),
        ...(accept ? { accept_approx: true } : {}),
      })
      if (!coverage.sessions.some((x) => x.id === s.id)) coverage.sessions.unshift(s)
    } catch (e) {
      if (e instanceof ApiError && e.code === 'approx_position') askApprox = e.message
      else error = e instanceof Error ? e.message : t('coverage.error')
    } finally {
      busy = false
    }
  }
</script>

<Card>
  <section class="setup">
    <h3>{t('coverage.setup.title')}</h3>
    <Field label={t('coverage.setup.baseRadio')} for="cov-radio">
      {#snippet children()}
        <Select id="cov-radio" bind:value={() => radioId, (v) => (radioPick = v)} disabled={!connected.length}>
          {#each connected as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
          {#if !connected.length}<option value="">{t('coverage.setup.noRadio')}</option>{/if}
        </Select>
      {/snippet}
    </Field>
    <Field label={t('coverage.setup.mobile')} for="cov-mobile">
      {#snippet children()}
        <input class="ui-input" type="search" aria-label={t('coverage.setup.searchAria')} placeholder={t('coverage.setup.searchPh')} bind:value={query} />
        <Select id="cov-mobile" bind:value={() => mobileId, (v) => (mobilePick = v)} disabled={!candidates.length}>
          {#each candidates as n (n.id)}<option value={n.id}>{label(n)}</option>{/each}
          {#if !candidates.length}<option value="">{t('coverage.setup.noNode')}</option>{/if}
        </Select>
      {/snippet}
    </Field>
    <div class="fld">
      <span class="ui-lbl" id="cov-mode">{t('coverage.setup.mode')}</span>
      <Segmented
        label={t('coverage.setup.mode')}
        items={[
          { value: 'rangetest', label: t('coverage.setup.rangetest') },
          { value: 'position', label: t('coverage.setup.position') },
        ]}
        bind:value={mode}
      />
      <span class="ui-hint">{t('coverage.setup.modeHint')}</span>
    </div>
    <Field label={t('coverage.setup.interval')} for="cov-int" error={validInterval(interval) ? undefined : t('coverage.setup.intervalErr')}>
      {#snippet children({ invalid })}
        <input id="cov-int" class="ui-input ui-mono" class:err={invalid} type="number" min="10" max="600" bind:value={interval} />
      {/snippet}
    </Field>

    <ul class="guide" aria-label={t('coverage.setup.guide')}>
      {#each steps as s (s.key)}
        <li>
          <span class="mark" class:ok={s.ok === true} class:warn={s.ok === false}>
            <Icon name={s.ok === true ? 'check' : s.ok === false ? 'alert' : 'minus'} size={16} />
          </span>
          <span>
            {s.label}
            {#if s.hint}<small>{s.hint}</small>{/if}
          </span>
        </li>
      {/each}
    </ul>

    <Check bind:checked={privateChannel} label={t('coverage.setup.private')} />
    <div class="btns">
      <Button disabled={prepBusy || !radioId || !mobileId || !validInterval(interval) || !!plan} onclick={prepare}>{t('coverage.setup.prepare')}</Button>
      <Button kind="primary" disabled={!canStart} onclick={() => start(false)}>{t('coverage.setup.start')}</Button>
    </div>
    {#if prepError}<Banner kind="danger" title={prepError} />{/if}
    {#if plan}
      {#key plan.plan_id}
        <CoveragePlanFlow {plan} kind="prepare" oncancel={() => (plan = null)} onfinished={onprepared} />
      {/key}
    {/if}

    {#if askApprox}
      <Banner kind="warn" title={t('coverage.setup.approx')}>
        {askApprox}
        {#snippet action()}
          <Button disabled={busy} onclick={() => start(true)}>{t('coverage.setup.continue')}</Button>
          <Button kind="ghost" onclick={() => (askApprox = '')}>{t('common.cancel')}</Button>
        {/snippet}
      </Banner>
    {/if}
    {#if error}<Banner kind="danger" title={error} />{/if}

    <button class="link" aria-expanded={showHelp} onclick={() => (showHelp = !showHelp)}>
      <Icon name={showHelp ? 'chevD' : 'chevR'} size={16} /> {t('coverage.setup.howto')}
    </button>
    {#if showHelp}
      <div class="help">
        <ol>
          <li>{t('coverage.setup.help1')}</li>
          <li>{t('coverage.setup.help2')}</li>
          <li>{t('coverage.setup.help3')}</li>
          <li>{t('coverage.setup.help4')}</li>
          <li>{t('coverage.setup.help5')}</li>
        </ol>
        <p>{t('coverage.setup.helpNote')}</p>
      </div>
    {/if}
  </section>
</Card>

<style>
  .setup { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  .fld { display: flex; flex-direction: column; gap: 6px; }
  .btns { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .guide { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); font: 400 14px/20px var(--font-sans); }
  .guide li { display: flex; gap: var(--space-2); }
  .guide small { display: block; color: var(--ink-muted); font-size: 13px; }
  .mark { width: 20px; display: grid; place-items: center; color: var(--ink-muted); }
  .mark.ok { color: var(--ok); }
  .mark.warn { color: var(--warn); }
  .link { display: inline-flex; align-items: center; gap: var(--space-1); min-height: var(--touch-min); background: none; border: 0; color: var(--accent); font: 500 14px/20px var(--font-sans); cursor: pointer; text-align: left; padding: 0; }
  .help { font: 400 14px/20px var(--font-sans); color: var(--ink); }
  .help ol { margin: 0 0 var(--space-2); padding-left: 20px; }
  .help p { margin: 0; color: var(--ink-muted); }
</style>
