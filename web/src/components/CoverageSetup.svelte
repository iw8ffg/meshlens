<script lang="ts">
  import { ApiError, coverageCheck, preparePlan, startCoverage } from '../lib/api'
  import { checklist, validInterval } from '../lib/coverage'
  import { app, coverage } from '../lib/stores.svelte'
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
      prepError = e instanceof Error ? e.message : 'Errore'
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
      else error = e instanceof Error ? e.message : 'Errore'
    } finally {
      busy = false
    }
  }
</script>

<Card>
  <section class="setup">
    <h3>Nuova prova</h3>
    <Field label="Radio di base" for="cov-radio">
      {#snippet children()}
        <Select id="cov-radio" bind:value={radioPick} disabled={!connected.length}>
          {#each connected as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
          {#if !connected.length}<option value="">Nessuna radio collegata</option>{/if}
        </Select>
      {/snippet}
    </Field>
    <Field label="Nodo mobile" for="cov-mobile">
      {#snippet children()}
        <input class="ui-input" type="search" aria-label="Cerca il nodo mobile" placeholder="Cerca per nome o id" bind:value={query} />
        <Select id="cov-mobile" bind:value={mobilePick} disabled={!candidates.length}>
          {#each candidates as n (n.id)}<option value={n.id}>{label(n)}</option>{/each}
          {#if !candidates.length}<option value="">Nessun nodo trovato</option>{/if}
        </Select>
      {/snippet}
    </Field>
    <div class="fld">
      <span class="ui-lbl" id="cov-mode">Modalità</span>
      <Segmented
        label="Modalità"
        items={[
          { value: 'rangetest', label: 'Range Test' },
          { value: 'position', label: 'Solo posizione' },
        ]}
        bind:value={mode}
      />
      <span class="ui-hint">Range Test è la modalità consigliata.</span>
    </div>
    <Field label="Intervallo (secondi)" for="cov-int" error={validInterval(interval) ? undefined : "L'intervallo deve essere tra 10 e 600 secondi."}>
      {#snippet children({ invalid })}
        <input id="cov-int" class="ui-input ui-mono" class:err={invalid} type="number" min="10" max="600" bind:value={interval} />
      {/snippet}
    </Field>

    <ul class="guide" aria-label="Guida">
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

    <Check bind:checked={privateChannel} label="Usa un canale privato temporaneo a precisione piena (le due radio saranno isolate dalla rete pubblica durante la prova)" />
    <div class="btns">
      <Button disabled={prepBusy || !radioId || !mobileId || !validInterval(interval) || !!plan} onclick={prepare}>Prepara le radio</Button>
      <Button kind="primary" disabled={!canStart} onclick={() => start(false)}>Avvia prova</Button>
    </div>
    {#if prepError}<Banner kind="danger" title={prepError} />{/if}
    {#if plan}
      {#key plan.plan_id}
        <CoveragePlanFlow {plan} kind="prepare" oncancel={() => (plan = null)} onfinished={onprepared} />
      {/key}
    {/if}

    {#if askApprox}
      <Banner kind="warn" title="Posizioni approssimate">
        {askApprox}
        {#snippet action()}
          <Button disabled={busy} onclick={() => start(true)}>Continua</Button>
          <Button kind="ghost" onclick={() => (askApprox = '')}>Annulla</Button>
        {/snippet}
      </Banner>
    {/if}
    {#if error}<Banner kind="danger" title={error} />{/if}

    <button class="link" aria-expanded={showHelp} onclick={() => (showHelp = !showHelp)}>
      <Icon name={showHelp ? 'chevD' : 'chevR'} size={16} /> Come preparare le radio
    </button>
    {#if showHelp}
      <div class="help">
        <ol>
          <li>Imposta lo stesso canale privato su entrambe le radio, con posizione a precisione piena.</li>
          <li>Sul nodo mobile attiva Range Test come mittente, ogni 30 s.</li>
          <li>Sulla base attiva Range Test come ricevitore (mittente 0).</li>
          <li>Sul mobile imposta la posizione ogni 30 s, con smart position a intervallo minimo 30 s.</li>
          <li>A fine prova spegni il modulo Range Test.</li>
        </ol>
        <p>Durante la prova il telefono non serve: MeshLens registra da solo.</p>
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
