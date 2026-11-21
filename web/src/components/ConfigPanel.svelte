<script lang="ts">
  import { onMount, untrack } from 'svelte'
  import {
    ApiError,
    applyConfig,
    configBackups,
    configJob,
    configSchema,
    previewConfig,
    previewRestore,
    radioAdminKey,
    readConfig,
    rebootNode,
    revealPsk,
    savedConfig,
    setFixedPosition,
  } from '../lib/api'
  import {
    CHANNEL_LABELS,
    MASK,
    SIMPLE_TABS,
    backupReasonLabel,
    cloneConfig,
    enumLabel,
    formChanges,
    genPsk,
    getPath,
    jobText,
    schemaField,
    setPath,
  } from '../lib/config'
  import { formatDate, timeAgo } from '../lib/format'
  import { app, configJobs, setConfigJob } from '../lib/stores.svelte'
  import type { ConfigBackup, ConfigDict, ConfigPreview, ConfigSaved, ConfigSchema, ConfigValue } from '../lib/types'
  import ConfigAdvanced from './ConfigAdvanced.svelte'
  import ConfigDiff from './ConfigDiff.svelte'
  import ConfigField from './ConfigField.svelte'

  let {
    nodeId,
    radioId = null,
    initialTab = null,
    now,
    onclose,
  }: {
    nodeId: string
    radioId?: string | null
    initialTab?: string | null
    now: number
    onclose: () => void
  } = $props()

  const TABS: [string, string][] = [
    ...SIMPLE_TABS.slice(0, 4).map((t): [string, string] => [t.id, t.label]),
    ['channels', 'Canali'],
    ['modules', 'Moduli'],
    ['advanced', 'Avanzate'],
    ['backups', 'Copie'],
    ['adminkey', 'Chiave admin'],
  ]

  const node = $derived(app.nodes.get(nodeId) ?? null)
  const nodeName = $derived(node?.long_name || node?.short_name || nodeId)
  const radios = $derived(app.radios.filter((r) => r.state === 'connected'))

  let tab = $state(untrack(() => initialTab) ?? 'general')
  let radio = $state<string>(
    untrack(
      () =>
        radioId ??
        app.radios.find((r) => r.state === 'connected' && r.my_node_id === nodeId)?.id ??
        app.radios.find((r) => r.state === 'connected')?.id ??
        '',
    ),
  )
  let schema = $state<ConfigSchema | null>(null)
  let saved = $state<ConfigSaved | null>(null)
  let edited = $state<ConfigDict>({})
  let backups = $state<ConfigBackup[]>([])
  let preview = $state<ConfigPreview | null>(null)
  let jobId = $state<number | null>(null)
  let err = $state('')
  let busy = $state(false)
  let pending = $state<'reboot' | 'fixed' | 'remove' | null>(null)
  let adminKey = $state('')
  let copied = $state(false)
  let revealed = $state<Record<number, string>>({})
  let lat = $state(untrack(() => (app.nodes.get(nodeId)?.lat ?? '').toString()))
  let lon = $state(untrack(() => (app.nodes.get(nodeId)?.lon ?? '').toString()))
  let alt = $state('')

  const job = $derived(jobId === null ? null : (configJobs.get(jobId) ?? null))
  const running = $derived(job?.status === 'running')
  const lock = $derived(running || busy)
  const local = $derived(app.radios.find((r) => r.id === radio)?.my_node_id === nodeId)
  const keyMissing = $derived(!!job?.error && /chiave admin/i.test(job.error))

  function msg(e: unknown): string {
    return e instanceof ApiError ? e.message : 'Operazione non riuscita'
  }

  function takeSaved(s: ConfigSaved | null) {
    saved = s
    edited = s ? cloneConfig(s.config) : {}
    revealed = {}
  }

  async function loadSaved() {
    try {
      takeSaved(await savedConfig(nodeId))
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) takeSaved(null)
      else err = msg(e)
    }
  }
  async function loadBackups() {
    try {
      backups = await configBackups(nodeId)
    } catch {
      /* elenco non disponibile */
    }
  }
  async function loadKey() {
    if (!radio) return
    try {
      adminKey = (await radioAdminKey(radio)).public_key_b64
    } catch {
      adminKey = ''
    }
  }

  onMount(() => {
    configSchema()
      .then((s) => (schema = s))
      .catch((e) => (err = msg(e)))
    loadSaved()
    loadBackups()
    loadKey()
  })

  // Un lavoro concluso: rilegge la lettura salvata e le copie (una sola volta per lavoro)
  const handled = new Set<number>()
  const finished = $derived(job && job.status !== 'running' ? job.id : null)
  $effect(() => {
    const id = finished
    if (id === null || handled.has(id)) return
    handled.add(id)
    untrack(() => {
      loadSaved()
      loadBackups()
    })
  })

  // Rete di sicurezza se il WebSocket perde un aggiornamento: interroga il lavoro finche' gira
  $effect(() => {
    if (!running || jobId === null) return
    const id = jobId
    const t = setInterval(() => {
      configJob(id)
        .then(setConfigJob)
        .catch(() => {})
    }, 2000)
    return () => clearInterval(t)
  })

  // Dopo una riconnessione del WebSocket un lavoro potrebbe essere finito senza che lo sapessimo
  $effect(() => {
    void app.reconnects
    untrack(() => {
      if (jobId !== null) {
        configJob(jobId)
          .then(setConfigJob)
          .catch(() => {})
      }
    })
  })

  async function run(fn: () => Promise<{ id: number } & Parameters<typeof setConfigJob>[0]>) {
    busy = true
    err = ''
    try {
      const j = await fn()
      setConfigJob(j)
      jobId = j.id
    } catch (e) {
      err = msg(e)
    } finally {
      busy = false
      pending = null
    }
  }

  const read = () => {
    preview = null
    run(() => readConfig(nodeId, radio ? { radio_id: radio } : {}))
  }

  async function review() {
    if (!saved) return
    busy = true
    err = ''
    try {
      const changes = formChanges(saved.config, edited)
      if (Object.keys(changes).length === 0) {
        err = 'Nessuna modifica da applicare'
        return
      }
      preview = await previewConfig(nodeId, changes)
    } catch (e) {
      err = msg(e)
    } finally {
      busy = false
    }
  }

  async function restore(b: ConfigBackup) {
    busy = true
    err = ''
    try {
      preview = await previewRestore(b.id)
    } catch (e) {
      err = msg(e)
    } finally {
      busy = false
    }
  }

  function apply(confirmRisky: boolean) {
    if (!preview) return
    const id = preview.preview_id
    preview = null
    run(() => applyConfig(nodeId, id, confirmRisky))
  }

  const reboot = () => run(() => rebootNode(nodeId, radio || undefined))

  function fixed() {
    const la = Number(lat)
    const lo = Number(lon)
    if (lat === '' || lon === '' || !Number.isFinite(la) || !Number.isFinite(lo) || Math.abs(la) > 90 || Math.abs(lo) > 180) {
      err = 'Coordinate non valide'
      pending = null
      return
    }
    run(() => setFixedPosition(nodeId, alt === '' ? { lat: la, lon: lo } : { lat: la, lon: lo, alt: Number(alt) }))
  }

  async function reveal(i: number) {
    err = ''
    try {
      revealed[i] = (await revealPsk(nodeId, i)).psk
    } catch (e) {
      err = msg(e)
    }
  }

  async function copyKey() {
    try {
      await navigator.clipboard.writeText(adminKey)
      copied = true
      setTimeout(() => (copied = false), 2000)
    } catch {
      err = 'Copia non riuscita: seleziona il testo a mano'
    }
  }

  const set = (path: string, v: ConfigValue) => setPath(edited, path, v)
  const channels = $derived((edited.channels ?? []).slice().sort((a, b) => a.index - b.index))
  const dirty = $derived(saved ? Object.keys(formChanges(saved.config, edited)).length : 0)
  const outcome = $derived.by(() => {
    if (!job || job.status === 'running') return ''
    if (job.status === 'failed') return job.error ?? 'Operazione non riuscita'
    if (job.kind === 'apply')
      return job.verify === 'verified'
        ? 'Applicato e verificato'
        : job.verify === 'mismatch'
          ? 'Applicato ma la verifica non coincide'
          : 'Applicato'
    return job.kind === 'read' ? 'Lettura completata' : 'Fatto'
  })
</script>

<div class="overlay" role="dialog" aria-modal="true" aria-label="Configura nodo">
  <div class="box">
    <header>
      <h2>Configura · {nodeName}</h2>
      <button class="x" aria-label="Chiudi" onclick={onclose}>✕</button>
    </header>
    <p class="muted">{nodeId}{local ? ' · nodo locale della radio' : ''}</p>

    <div class="row">
      <label>
        Radio
        <select bind:value={radio} disabled={lock} onchange={loadKey}>
          {#if radios.length === 0}<option value="">Nessuna radio connessa</option>{/if}
          {#each radios as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
        </select>
      </label>
      <button class="go" disabled={lock || !radio} onclick={read}>Leggi configurazione</button>
    </div>
    <p class="muted">
      {saved ? `Ultima lettura: ${timeAgo(saved.time, now)} (${formatDate(saved.time)})` : 'Nessuna lettura salvata: leggi prima la configurazione.'}
    </p>

    {#if err}<p class="err" role="alert">{err}</p>{/if}

    {#if job}
      <div class="job" class:bad={job.status === 'failed'}>
        {#if running}
          <span>{jobText(job.step, job.progress)}</span>
        {:else}
          <strong>{outcome}</strong>
        {/if}
        {#if keyMissing}
          <p>
            <button class="link" onclick={() => (tab = 'adminkey')}>Come aggiungere la chiave admin</button>
          </p>
          {#if adminKey}
            <code class="key">{adminKey}</code>
            <button onclick={copyKey}>{copied ? 'Copiata' : 'Copia'}</button>
          {/if}
        {/if}
        {#if !running}<button class="link" onclick={() => (jobId = null)}>Chiudi</button>{/if}
      </div>
    {/if}

    <nav class="tabs">
      {#each TABS as [id, label] (id)}
        <button class:on={tab === id} onclick={() => (tab = id)}>{label}</button>
      {/each}
    </nav>

    {#if preview}
      <ConfigDiff {preview} {busy} onapply={apply} oncancel={() => (preview = null)} />
    {/if}

    {#if tab === 'adminkey'}
      <h3>Chiave admin della radio</h3>
      <p class="muted">
        Il nodo da gestire accetta comandi solo da chi ha la sua chiave pubblica tra le "Admin key" (massimo 3).
      </p>
      {#if adminKey}
        <code class="key">{adminKey}</code>
        <button onclick={copyKey}>{copied ? 'Copiata' : 'Copia'}</button>
      {:else}
        <p class="muted">Chiave non disponibile: la radio deve essere connessa.</p>
      {/if}
      <ol>
        <li>Apri l'app Meshtastic sul nodo da gestire.</li>
        <li>Vai in Sicurezza → Admin key e incolla la chiave.</li>
        <li>Salva.</li>
      </ol>
    {:else if tab === 'backups'}
      <h3>Copie di sicurezza</h3>
      {#each backups as b (b.id)}
        <div class="bk">
          <span>
            {formatDate(b.time)} · {backupReasonLabel(b.reason)}{b.label ? ` · ${b.label}` : ''}
            <small class="muted">({b.sections.join(', ')})</small>
          </span>
          <button disabled={lock} onclick={() => restore(b)}>Ripristina</button>
        </div>
      {:else}
        <p class="muted">Nessuna copia.</p>
      {/each}
    {:else if !saved || !schema}
      <p class="muted">{schema ? 'Leggi la configurazione per modificarla.' : 'Caricamento…'}</p>
    {:else if tab === 'advanced'}
      <ConfigAdvanced {schema} {edited} disabled={lock} />
    {:else if tab === 'channels'}
      {#each channels as c (c.index)}
        <details open={c.index === 0}>
          <summary>
            Canale {c.index}{c.name ? ` · ${c.name}` : ''} <small class="muted">{enumLabel('channel.role', String(c.role ?? ''))}</small>
          </summary>
          {#if c.index === 0}<p class="warn">Il canale 0 è quello principale: modificarlo può isolare il nodo.</p>{/if}
          {#each ['role', 'name', 'position_precision', 'uplink_enabled', 'downlink_enabled'] as f (f)}
            {#if schema.channel[f]}
              <ConfigField
                path={f === 'role' ? 'channel.role' : `channels.${c.index}.${f}`}
                field={schema.channel[f]}
                label={CHANNEL_LABELS[f]}
                value={getPath(edited, `channels.${c.index}.${f}`)}
                disabled={lock}
                onchange={(v) => set(`channels.${c.index}.${f}`, v)}
              />
            {/if}
          {/each}
          <div class="psk">
            <span class="lbl">{CHANNEL_LABELS.psk}</span>
            <code>{c.psk !== MASK && c.psk ? 'nuova chiave (da applicare)' : (revealed[c.index] ?? MASK)}</code>
            <button disabled={lock} onclick={() => reveal(c.index)}>Mostra</button>
            <button disabled={lock} onclick={() => set(`channels.${c.index}.psk`, genPsk())}>Genera nuova</button>
            {#if c.psk !== MASK}
              <button disabled={lock} onclick={() => set(`channels.${c.index}.psk`, MASK)}>Annulla</button>
            {/if}
          </div>
          {#if c.index === 0 && c.psk !== MASK}<p class="warn">Una nuova chiave sul canale 0 ti separa da tutti i nodi che non la conoscono.</p>{/if}
        </details>
      {/each}
    {:else}
      {#each SIMPLE_TABS.filter((t) => t.id === tab) as t (t.id)}
        {#each t.fields as f (f.path)}
          {@const sf = schemaField(schema, f.path)}
          {#if sf}
            <ConfigField
              path={f.path}
              field={sf}
              label={f.label}
              help={f.help}
              value={getPath(edited, f.path)}
              disabled={lock}
              onchange={(v) => set(f.path, v)}
            />
          {/if}
        {/each}
      {/each}
      {#if tab === 'position'}
        <h3>Posizione fissa</h3>
        <div class="row">
          <label>Latitudine <input bind:value={lat} inputmode="decimal" /></label>
          <label>Longitudine <input bind:value={lon} inputmode="decimal" /></label>
          <label>Altitudine (m) <input bind:value={alt} inputmode="decimal" placeholder="opzionale" /></label>
        </div>
        {#if pending === 'fixed' || pending === 'remove'}
          <p class="warn">{pending === 'fixed' ? 'Impostare la posizione fissa?' : 'Rimuovere la posizione fissa?'} Il nodo si riavvierà.</p>
          <button class="go" disabled={lock} onclick={() => (pending === 'fixed' ? fixed() : run(() => setFixedPosition(nodeId, { remove: true })))}>Conferma</button>
          <button onclick={() => (pending = null)}>Annulla</button>
        {:else}
          <button disabled={lock || !radio} onclick={() => (pending = 'fixed')}>Imposta posizione fissa</button>
          <button disabled={lock || !radio} onclick={() => (pending = 'remove')}>Rimuovi posizione fissa</button>
        {/if}
      {/if}
    {/if}

    {#if saved && schema && tab !== 'adminkey' && tab !== 'backups'}
      <div class="foot">
        <button class="go" disabled={lock || dirty === 0 || !!preview} onclick={review}>Rivedi modifiche{dirty ? ` (${dirty})` : ''}</button>
        {#if pending === 'reboot'}
          <span>Riavviare il nodo?</span>
          <button class="danger" disabled={lock} onclick={reboot}>Conferma</button>
          <button onclick={() => (pending = null)}>Annulla</button>
        {:else}
          <button class="danger" disabled={lock || !radio} onclick={() => (pending = 'reboot')}>Riavvia nodo</button>
        {/if}
      </div>
    {/if}
  </div>
</div>

<style>
  .overlay {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  .box {
    background: #111827;
    border: 1px solid #374151;
    border-radius: 8px;
    width: min(720px, 96vw);
    max-height: 92dvh;
    overflow: auto;
    padding: 10px 14px;
  }
  header {
    display: flex;
    align-items: center;
  }
  h2 {
    flex: 1;
    font-size: 17px;
    margin: 0;
  }
  h3 {
    font-size: 14px;
    margin: 12px 0 4px;
  }
  .x {
    background: none;
    border: 0;
    color: inherit;
    font-size: 18px;
    cursor: pointer;
  }
  .muted {
    color: #9ca3af;
    font-size: 12px;
  }
  .err {
    color: #f87171;
  }
  .warn {
    color: #fbbf24;
    font-size: 13px;
  }
  .row {
    display: flex;
    gap: 8px;
    align-items: flex-end;
    flex-wrap: wrap;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 3px;
    font-size: 13px;
  }
  .job {
    border: 1px solid #374151;
    border-radius: 6px;
    padding: 6px 8px;
    margin: 6px 0;
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    align-items: center;
  }
  .job.bad {
    border-color: #ef4444;
    color: #f87171;
  }
  .tabs {
    display: flex;
    flex-wrap: wrap;
    border-bottom: 1px solid #1f2937;
    margin: 8px 0;
  }
  .tabs button {
    background: none;
    border: 0;
    border-bottom: 2px solid transparent;
    color: inherit;
    padding: 6px 10px;
    cursor: pointer;
    font: inherit;
  }
  .tabs button.on {
    border-bottom-color: #2563eb;
    color: #93c5fd;
  }
  .key {
    display: block;
    word-break: break-all;
    background: #1f2937;
    padding: 6px;
    border-radius: 4px;
    margin: 6px 0;
    font-size: 12px;
  }
  .bk {
    display: flex;
    justify-content: space-between;
    gap: 8px;
    align-items: center;
    padding: 4px 0;
    border-bottom: 1px solid #1f2937;
    font-size: 13px;
  }
  details {
    border: 1px solid #1f2937;
    border-radius: 6px;
    padding: 4px 8px;
    margin: 6px 0;
  }
  summary {
    cursor: pointer;
    font-size: 14px;
  }
  .psk {
    display: flex;
    gap: 6px;
    align-items: center;
    flex-wrap: wrap;
    margin: 8px 0;
    font-size: 13px;
  }
  .psk code {
    word-break: break-all;
    font-size: 12px;
  }
  .foot {
    display: flex;
    gap: 8px;
    align-items: center;
    flex-wrap: wrap;
    margin-top: 12px;
    padding-top: 8px;
    border-top: 1px solid #1f2937;
  }
  button,
  select,
  input {
    font: inherit;
  }
  button:not(.x):not(.link):not(.tabs button),
  select,
  input {
    padding: 6px 10px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 4px;
  }
  button {
    cursor: pointer;
  }
  button:disabled {
    opacity: 0.5;
    cursor: default;
  }
  button.go {
    background: #2563eb;
    border-color: #2563eb;
    color: #fff;
  }
  button.danger {
    color: #f87171;
  }
  button.link {
    background: none;
    border: 0;
    color: #93c5fd;
    text-decoration: underline;
    padding: 0;
  }
</style>
