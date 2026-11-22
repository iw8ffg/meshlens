<script lang="ts">
  import { locale } from '../lib/i18n/index.svelte'
  import { onMount } from 'svelte'
  import { ApiError, checkUpdate, downloadUpdate, getJSON, installUpdate, send, updateStatus } from '../lib/api'
  import { formatBytes, jobPercent } from '../lib/maps'
  import { setUpdateJob, setUpdateStatus, updates } from '../lib/stores.svelte'
  import { canInstall, updateLabel } from '../lib/update'
  import type { AppSettings } from '../lib/settings'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import Progress from '../lib/ui/Progress.svelte'
  import Switch from '../lib/ui/Switch.svelte'

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

  async function toggleAuto(value: boolean) {
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
    return Number.isNaN(d.getTime()) ? '—' : d.toLocaleString(locale())
  }
</script>

<Card>
  <section class="sec">
    <h3>Aggiornamenti</h3>
    {#if loadError}
      <Banner kind="danger" title={loadError} />
    {/if}
    <p class="line">Versione attuale: <b class="ui-mono">{status?.current ?? (version || '—')}</b></p>
    <p class="line" class:err={!!status?.error} role="status">{updateLabel(status)}</p>
    {#if status?.checked_at}<p class="muted">Ultimo controllo: {when(status.checked_at)}</p>{/if}

    <div class="tok">
      <span class="ui-lbl" id="upd-token-label">Token GitHub (repository privato)</span>
      {#if tokenSet && !replacing}
        <div class="row">
          <span class="mask ui-mono" aria-labelledby="upd-token-label">••••</span>
          <Button onclick={() => (replacing = true)}>Sostituisci</Button>
          <Button kind="danger" onclick={removeToken}>Rimuovi token</Button>
        </div>
      {:else}
        <div class="row">
          <input
            class="ui-input ui-mono grow"
            type="password"
            autocomplete="off"
            aria-labelledby="upd-token-label"
            placeholder={tokenSet ? 'Nuovo token (vuoto = invariato)' : 'github_pat_…'}
            bind:value={tokenInput}
          />
          <Button kind="primary" onclick={saveToken}>Salva token</Button>
          {#if replacing}<Button onclick={() => ((replacing = false), (tokenInput = ''))}>Annulla</Button>{/if}
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
        <p class="muted">Il token deve essere creato dal proprietario del repository. Se sei un collaboratore, usa un token classico con permesso «repo».</p>
      </details>
    </div>

    <Switch bind:checked={autoCheck} label="Controlla automaticamente ogni giorno" onchange={toggleAuto} />

    <div class="row">
      <Button icon="refresh" disabled={busy || running || installing} onclick={check}>Controlla ora</Button>
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
            <Progress value={percent} label="Avanzamento del download" text="{percent}% ({formatBytes(job.bytes_done)} di {formatBytes(job.bytes_total ?? 0)})" />
          {:else}
            <Progress value={100} label="Download in corso" text={formatBytes(job.bytes_done)} />
          {/if}
        </div>
      {:else if job?.status === 'failed'}
        <Banner kind="danger" title="Download non riuscito">{job.error ?? 'errore sconosciuto'}</Banner>
      {:else if job?.status === 'done'}
        <Banner kind="ok" title="Download completato e verificato" />
      {/if}

      {#if installing}
        <Banner kind="info" title="Installazione in corso">MeshLens si riapre a breve.</Banner>
      {:else}
        <div class="row">
          {#if !running && job?.status !== 'done'}
            <Button kind="primary" icon="download" disabled={busy} onclick={download}>
              {job?.status === 'failed' ? 'Riprova download' : 'Scarica'}
            </Button>
          {/if}
          <Button kind="primary" icon="power" disabled={!installable || busy} onclick={() => (confirming = true)}>
            Installa e riavvia
          </Button>
        </div>
        {#if status.frozen === false}
          <p class="muted">L'installazione è disponibile solo nella versione installata di MeshLens (non in sviluppo).</p>
        {/if}
      {/if}
    {/if}

    {#if error}<Banner kind="danger" title={error} />{/if}
    {#if info}<Banner kind="ok" title={info} />{/if}
  </section>
</Card>

<Modal open={confirming} title="Installare l'aggiornamento?" confirmLabel="Installa" onconfirm={install} oncancel={() => (confirming = false)}>
  <p>MeshLens si chiuderà per qualche secondo e si riaprirà aggiornato</p>
</Modal>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .line { font: 400 14px/20px var(--font-sans); }
  .tok { display: flex; flex-direction: column; gap: var(--space-2); }
  .mask { letter-spacing: 2px; }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .grow { flex: 1; min-width: 160px; width: auto; }
  .guide { margin: var(--space-1) 0 0; padding-left: 18px; font: 400 14px/20px var(--font-sans); }
  .notes { font: 400 14px/20px var(--font-sans); }
  .notes pre { margin: var(--space-1) 0 0; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; max-height: 200px; overflow: auto; }
  .job { display: flex; flex-direction: column; gap: var(--space-2); padding: var(--space-3); border: 1px solid var(--line); border-radius: var(--radius-md); font: 400 14px/20px var(--font-sans); }
  details { font: 400 14px/20px var(--font-sans); }
  summary { cursor: pointer; min-height: var(--touch-min); display: flex; align-items: center; }
  summary:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  .err { color: var(--danger); }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
