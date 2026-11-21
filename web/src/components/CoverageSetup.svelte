<script lang="ts">
  import { ApiError, coverageCheck, startCoverage } from '../lib/api'
  import { checklist, validInterval } from '../lib/coverage'
  import { app, coverage } from '../lib/stores.svelte'
  import type { CoverageCheck, CoverageMode } from '../lib/types'

  const connected = $derived(app.radios.filter((r) => r.state === 'connected'))
  const radioNodeIds = $derived(new Set(app.radios.map((r) => r.my_node_id).filter((x): x is string => !!x)))
  let radioId = $state('')
  let query = $state('')
  let mobileId = $state('')
  let mode = $state<CoverageMode>('rangetest')
  let interval = $state(30)
  let check = $state<CoverageCheck | null>(null)
  let busy = $state(false)
  let error = $state('')
  let askApprox = $state('')
  let showHelp = $state(false)

  // Radio di base: la prima collegata, se quella scelta sparisce
  $effect(() => {
    if (!connected.some((r) => r.id === radioId)) radioId = connected[0]?.id ?? ''
  })

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
  $effect(() => {
    if (!candidates.some((n) => n.id === mobileId)) mobileId = candidates[0]?.id ?? ''
  })

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

<section class="setup">
  <h3>Nuova prova</h3>
  <label>
    Radio di base
    <select bind:value={radioId} disabled={!connected.length}>
      {#each connected as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
      {#if !connected.length}<option value="">Nessuna radio collegata</option>{/if}
    </select>
  </label>
  <label>
    Nodo mobile
    <input type="search" placeholder="Cerca per nome o id" bind:value={query} />
    <select bind:value={mobileId} disabled={!candidates.length}>
      {#each candidates as n (n.id)}<option value={n.id}>{label(n)}</option>{/each}
      {#if !candidates.length}<option value="">Nessun nodo trovato</option>{/if}
    </select>
  </label>
  <fieldset>
    <legend>Modalità</legend>
    <label class="inline"><input type="radio" bind:group={mode} value="rangetest" /> Range Test (consigliata)</label>
    <label class="inline"><input type="radio" bind:group={mode} value="position" /> Solo posizione</label>
  </fieldset>
  <label>
    Intervallo (secondi)
    <input type="number" min="10" max="600" bind:value={interval} />
  </label>

  <ul class="guide" aria-label="Guida">
    {#each steps as s (s.key)}
      <li>
        <span class="mark" class:ok={s.ok === true} class:warn={s.ok === false}>
          {s.ok === true ? '✓' : s.ok === false ? '⚠' : '—'}
        </span>
        <span>
          {s.label}
          {#if s.hint}<small>{s.hint}</small>{/if}
        </span>
      </li>
    {/each}
  </ul>

  <button class="start" disabled={!canStart} onclick={() => start(false)}>Avvia prova</button>
  {#if askApprox}
    <div class="confirm" role="alertdialog">
      <p>{askApprox}</p>
      <button onclick={() => start(true)} disabled={busy}>Continua con posizioni approssimate</button>
      <button class="ghost" onclick={() => (askApprox = '')}>Annulla</button>
    </div>
  {/if}
  {#if !validInterval(interval)}<p class="err">L'intervallo deve essere tra 10 e 600 secondi.</p>{/if}
  {#if error}<p class="err">{error}</p>{/if}

  <button class="link" aria-expanded={showHelp} onclick={() => (showHelp = !showHelp)}>
    {showHelp ? '▾' : '▸'} Come preparare le radio
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

<style>
  .setup {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 10px 12px;
  }
  h3 {
    margin: 0;
    font-size: 1em;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 4px;
    font-size: 0.9em;
  }
  label.inline {
    flex-direction: row;
    align-items: center;
  }
  fieldset {
    border: 1px solid #374151;
    border-radius: 6px;
    margin: 0;
  }
  select,
  input[type='search'],
  input[type='number'] {
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 4px;
    padding: 6px;
    font: inherit;
  }
  .guide {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 0.9em;
  }
  .guide li {
    display: flex;
    gap: 8px;
  }
  .guide small {
    display: block;
    color: #9ca3af;
  }
  .mark {
    width: 1.2em;
    text-align: center;
    color: #9ca3af;
  }
  .mark.ok {
    color: #2e9d4b;
  }
  .mark.warn {
    color: #d9a400;
  }
  button {
    padding: 8px 10px;
    border: 0;
    border-radius: 6px;
    background: #2563eb;
    color: #fff;
    font: inherit;
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  button.ghost {
    background: #374151;
  }
  button.link {
    background: none;
    color: #93c5fd;
    text-align: left;
    padding: 2px 0;
  }
  .confirm {
    border: 1px solid #d9a400;
    border-radius: 6px;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .confirm p {
    margin: 0;
  }
  .err {
    color: #f87171;
    margin: 0;
  }
  .help {
    font-size: 0.9em;
    color: #d1d5db;
  }
  .help ol {
    margin: 0 0 6px;
    padding-left: 20px;
  }
</style>
