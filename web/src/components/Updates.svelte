<script lang="ts">
  import { onMount } from 'svelte'
  import { ApiError, checkUpdate, downloadUpdate, getJSON, installUpdate, send, updateStatus } from '../lib/api'
  import { formatBytes, jobPercent } from '../lib/maps'
  import { setUpdateJob, setUpdateStatus, updates } from '../lib/stores.svelte'
  import { canInstall, updateLabel } from '../lib/update'
  import type { AppSettings } from '../lib/settings'

  let version = $state('')
  let tokenSet = $state(false)
  let replacing = $state(false)
  let tokenInput = $state('')
  let autoCheck = $state(true)
  let loadError = $state('')
  let error = $state('')
  let info = $state('')
  let busy = $state(false)
  let confirming = $state(false)
  let installing = $state(false)

  const status = $derived(updates.status)
  const job = $derived(updates.job)
  const running = $derived(job?.status === 'running')
  const percent = $derived(
    job ? jobPercent(job) : null,
  )
  const installable = $derived(canInstall(status, job))

  const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

  async function loadStatus() {
    try {
      setUpdateStatus(await updateStatus())
    } catch {
      /* resta l'ultimo stato noto */
    }
  }

  onMount(async () => {
    try {
      const s = await getJSON<AppSettings>('/settings')
      tokenSet = !!s.update_token
      autoCheck = s.update_auto_check ?? true
    } catch {
      loadError = 'Impostazioni di aggiornamento non disponibili'
    }
    try {
      version = (await getJSON<{ version: string }>('/version')).version
    } catch {
      /* la versione resta vuota */
    }
    void loadStatus()
  })

  // Download in corso: rilegge lo stato ogni 3 s (rete di sicurezza se il WebSocket non arriva)
  $effect(() => {
    if (!running) return
    const t = setInterval(() => void loadStatus(), 3000)
    return () => clearInterval(t)
  })

  async function saveSettings(body: Record<string, unknown>, done: string) {
    error = info = ''
    try {
      await send<AppSettings>('PUT', '/settings', body)
      info = done
      return true
    } catch (e) {
      error = errMsg(e, 'Salvataggio non riuscito')
      return false
    }
  }

  async function saveToken() {
    const v = tokenInput.trim()
    if (v === '') {
      // campo vuoto: il token resta invariato
      replacing = false
      return
    }
    if (await saveSettings({ update_token: v }, 'Token salvato')) {
      tokenSet = true
      tokenInput = ''
      replacing = false
    }
  }

  async function removeToken() {
    if (await saveSettings({ update_token: '' }, 'Token rimosso')) {
      tokenSet = false
      tokenInput = ''
      replacing = false
    }
  }

  async function toggleAuto(e: Event) {
    const value = (e.currentTarget as HTMLInputElement).checked
    if (!(await saveSettings({ update_auto_check: value }, 'Impostazione salvata'))) autoCheck = !value
  }

  async function check() {
    error = info = ''
    busy = true
    try {
      setUpdateStatus(await checkUpdate())
    } catch (e) {
      error = errMsg(e, 'Controllo non riuscito')
    } finally {
      busy = false
    }
  }

  async function download() {
    error = info = ''
    busy = true
    try {
      setUpdateJob(await downloadUpdate())
    } catch (e) {
      error = errMsg(e, 'Download non avviato')
    } finally {
      busy = false
    }
  }

  async function install() {
    error = info = ''
    busy = true
    try {
      await installUpdate()
      installing = true
      confirming = false
    } catch (e) {
      error = errMsg(e, 'Installazione non avviata')
    } finally {
      busy = false
    }
  }

  const when = (c: string | number | null) => {
    if (c === null) return '—'
    const d = typeof c === 'number' ? new Date(c * 1000) : new Date(c)
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString('it-IT')
  }
</script>

<fieldset>
  <legend>Aggiornamenti</legend>
  {#if loadError}
    <p class="err">{loadError}</p>
  {/if}
  <p class="line">Versione attuale: <b>{status?.current ?? (version || '—')}</b></p>
  <p class="line" class:err={!!status?.error} role="status">{updateLabel(status)}</p>
  {#if status?.checked_at}<p class="muted">Ultimo controllo: {when(status.checked_at)}</p>{/if}

  <div class="tok">
    <span class="lbl" id="upd-token-label">Token GitHub (repository privato)</span>
    {#if tokenSet && !replacing}
      <div class="row wrap">
        <span class="mask" aria-labelledby="upd-token-label">••••</span>
        <button type="button" onclick={() => (replacing = true)}>Sostituisci</button>
        <button type="button" class="danger" onclick={removeToken}>Rimuovi token</button>
      </div>
    {:else}
      <div class="row wrap">
        <input
          type="password"
          autocomplete="off"
          aria-labelledby="upd-token-label"
          placeholder={tokenSet ? 'Nuovo token (vuoto = invariato)' : 'github_pat_…'}
          bind:value={tokenInput}
        />
        <button type="button" onclick={saveToken}>Salva token</button>
        {#if replacing}<button type="button" onclick={() => ((replacing = false), (tokenInput = ''))}>Annulla</button>{/if}
      </div>
    {/if}
    <details>
      <summary>Come creare il token</summary>
      <ol class="guide">
        <li>GitHub → Settings → Developer settings → Personal access tokens → Fine-grained tokens → Generate new token.</li>
        <li>Repository access: Only select repositories → iw8ffg/meshlens.</li>
        <li>Permissions: Contents → Read-only.</li>
        <li>Copia il token e incollalo qui.</li>
      </ol>
    </details>
  </div>

  <label class="check">
    <input type="checkbox" bind:checked={autoCheck} onchange={toggleAuto} />
    Controlla automaticamente ogni giorno
  </label>

  <div class="row wrap">
    <button type="button" disabled={busy || running || installing} onclick={check}>Controlla ora</button>
  </div>

  {#if status?.available}
    {#if status.notes}
      <div class="notes">
        <b>Novità di {status.latest}</b>
        <pre>{status.notes}</pre>
      </div>
    {/if}

    {#if running && job}
      <div class="job" role="status">
        <div>Download in corso…</div>
        {#if percent !== null}
          <progress max="100" value={percent}></progress>
          <span>{percent}% ({formatBytes(job.bytes_done)} di {formatBytes(job.bytes_total ?? 0)})</span>
        {:else}
          <progress></progress>
          <span>{formatBytes(job.bytes_done)}</span>
        {/if}
      </div>
    {:else if job?.status === 'failed'}
      <p class="err" role="alert">Download non riuscito: {job.error ?? 'errore sconosciuto'}</p>
    {:else if job?.status === 'done'}
      <p class="ok">Download completato e verificato.</p>
    {/if}

    {#if installing}
      <p class="ok" role="status">Installazione in corso: MeshLens si riapre a breve.</p>
    {:else if confirming}
      <div class="confirm" role="dialog" aria-label="Conferma installazione">
        <p>MeshLens si chiuderà per qualche secondo e si riaprirà aggiornato</p>
        <span class="row">
          <button type="button" class="primary" disabled={busy} onclick={install}>Installa</button>
          <button type="button" onclick={() => (confirming = false)}>Annulla</button>
        </span>
      </div>
    {:else}
      <div class="row wrap">
        {#if !running && job?.status !== 'done'}
          <button type="button" class="primary" disabled={busy} onclick={download}>
            {job?.status === 'failed' ? 'Riprova download' : 'Scarica'}
          </button>
        {/if}
        <button type="button" class="primary" disabled={!installable || busy} onclick={() => (confirming = true)}>
          Installa e riavvia
        </button>
      </div>
      {#if status.can_install === false}
        <p class="muted">L'installazione è disponibile solo nella versione installata di MeshLens (non in sviluppo).</p>
      {/if}
    {/if}
  {/if}

  {#if error}<p class="err" role="alert">{error}</p>{/if}
  {#if info}<p class="ok" role="status">{info}</p>{/if}
</fieldset>

<style>
  fieldset {
    border: 1px solid #374151;
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .line {
    margin: 0;
    font-size: 13px;
  }
  .lbl {
    font-size: 13px;
  }
  .tok {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
  .mask {
    font-size: 13px;
    letter-spacing: 2px;
  }
  .check {
    display: flex;
    gap: 6px;
    align-items: center;
    font-size: 13px;
  }
  .row {
    display: flex;
    gap: 6px;
    align-items: center;
  }
  .wrap {
    flex-wrap: wrap;
  }
  .guide {
    margin: 4px 0 0;
    padding-left: 18px;
    font-size: 13px;
  }
  .notes {
    font-size: 13px;
  }
  .notes pre {
    margin: 4px 0 0;
    white-space: pre-wrap;
    overflow-wrap: anywhere;
    font: inherit;
    max-height: 200px;
    overflow: auto;
  }
  .job,
  .confirm {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 8px;
    border: 1px solid #374151;
    border-radius: 6px;
    font-size: 13px;
  }
  .confirm p {
    margin: 0;
  }
  progress {
    width: 100%;
  }
  input[type='password'] {
    padding: 5px 8px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    font: inherit;
    flex: 1;
    min-width: 0;
  }
  button {
    padding: 6px 12px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    cursor: pointer;
    font: inherit;
  }
  button:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
  button.primary {
    background: #2563eb;
    border-color: #2563eb;
  }
  button.danger {
    background: #b91c1c;
    border-color: #b91c1c;
  }
  .muted {
    color: #9ca3af;
    margin: 0;
    font-size: 12px;
  }
  @media (max-width: 767px) {
    .muted {
      font-size: 13px;
    }
    button,
    input:not([type='checkbox']) {
      min-height: 40px;
    }
  }
  .err {
    color: #f87171;
    margin: 0;
  }
  .ok {
    color: #34d399;
    margin: 0;
  }
</style>
