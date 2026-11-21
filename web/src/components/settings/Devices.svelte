<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
  import { ApiError, getJSON, send } from '../../lib/api'
  import { ago } from '../../lib/format'
  import { deviceLabel, pinError } from '../../lib/settings'
  import type { AuthStatus, SessionInfo } from '../../lib/types'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Field from '../../lib/ui/Field.svelte'

  let status = $state<AuthStatus | null>(null)
  let sessions = $state<SessionInfo[]>([])
  let listError = $state('')
  let current = $state('')
  let next = $state('')
  let confirm = $state('')
  let pinMsg = $state('')
  let pinOk = $state('')
  let busy = $state(false)
  let now = $state(Date.now() / 1000)
  const tick = setInterval(() => (now = Date.now() / 1000), 30_000)
  onDestroy(() => clearInterval(tick))

  const lan = $derived((status?.pin_min ?? 4) >= 6)
  const others = $derived(sessions.filter((s) => !s.current).length)
  const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

  async function loadStatus() {
    try {
      status = await getJSON<AuthStatus>('/auth/status')
    } catch {
      /* il banner del PIN corto resta nascosto */
    }
  }

  async function loadSessions() {
    try {
      sessions = await getJSON<SessionInfo[]>('/auth/sessions')
      listError = ''
    } catch (e) {
      listError = errMsg(e, 'Elenco dei dispositivi non disponibile')
    }
  }

  onMount(() => {
    void loadStatus()
    void loadSessions()
  })

  // Dentro il modulo di Impostazioni: Invio cambia il PIN invece di salvare le impostazioni
  function onPinKey(e: KeyboardEvent) {
    if (e.key !== 'Enter') return
    e.preventDefault()
    if (!busy && current && next && confirm) void changePin()
  }

  async function changePin() {
    pinMsg = pinOk = ''
    const err = pinError(next, lan)
    if (err) {
      pinMsg = err
      return
    }
    if (next !== confirm) {
      pinMsg = 'I due PIN non coincidono'
      return
    }
    busy = true
    try {
      await send('POST', '/auth/pin', { current_pin: current, new_pin: next })
      current = next = confirm = ''
      pinOk = 'PIN cambiato: gli altri dispositivi dovranno inserire quello nuovo'
      await Promise.all([loadStatus(), loadSessions()])
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) pinMsg = 'PIN attuale errato'
      else if (e instanceof ApiError && e.status === 429)
        pinMsg = e.retryAfter ? `Troppi tentativi: riprova tra ${e.retryAfter} secondi` : 'Troppi tentativi: riprova più tardi'
      else pinMsg = errMsg(e, 'Cambio del PIN non riuscito')
    } finally {
      busy = false
    }
  }

  async function revoke(s: SessionInfo) {
    listError = ''
    try {
      await send('DELETE', `/auth/sessions/${encodeURIComponent(s.id)}`)
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) listError = errMsg(e, 'Uscita non riuscita')
    }
    await loadSessions()
  }

  async function revokeOthers() {
    listError = ''
    try {
      await send('POST', '/auth/sessions/revoke-others')
    } catch (e) {
      listError = errMsg(e, 'Uscita non riuscita')
    }
    await loadSessions()
  }
</script>

<Card>
  <section class="sec">
    <h3>Accesso e dispositivi</h3>
    {#if status?.pin_short}
      <Banner kind="warn" title="Il PIN ha meno di 6 cifre: per l'accesso dalla rete cambialo con uno più lungo" />
    {/if}

    <!-- niente <form>: questa scheda sta dentro il modulo delle impostazioni -->
    <div class="pin" role="group" aria-labelledby="pin-title">
      <h4 id="pin-title">Cambia PIN</h4>
      <div class="grid">
        <Field label="PIN attuale" for="pin-cur">
          {#snippet children()}
            <input id="pin-cur" class="ui-input ui-mono" type="password" inputmode="numeric" autocomplete="current-password" maxlength="12" disabled={busy} bind:value={current} onkeydown={onPinKey} />
          {/snippet}
        </Field>
        <Field label="Nuovo PIN" for="pin-new" hint={lan ? 'Da 6 a 12 cifre' : 'Da 4 a 12 cifre'}>
          {#snippet children({ describedby })}
            <input id="pin-new" class="ui-input ui-mono" type="password" inputmode="numeric" autocomplete="new-password" maxlength="12" aria-describedby={describedby} disabled={busy} bind:value={next} onkeydown={onPinKey} />
          {/snippet}
        </Field>
        <Field label="Ripeti il nuovo PIN" for="pin-conf" error={confirm && next !== confirm ? 'I due PIN non coincidono' : undefined}>
          {#snippet children({ describedby, invalid })}
            <input id="pin-conf" class="ui-input ui-mono" class:err={invalid} type="password" inputmode="numeric" autocomplete="new-password" maxlength="12" aria-describedby={describedby} aria-invalid={invalid} disabled={busy} bind:value={confirm} onkeydown={onPinKey} />
          {/snippet}
        </Field>
      </div>
      <div><Button onclick={changePin} disabled={busy || !current || !next || !confirm}>Cambia PIN</Button></div>
      {#if pinMsg}<Banner kind="danger" title={pinMsg} />{/if}
      {#if pinOk}<Banner kind="ok" title={pinOk} />{/if}
    </div>

    <h4>Dispositivi collegati</h4>
    {#if listError}<Banner kind="danger" title={listError} />{/if}
    <ul class="devices">
      {#each sessions as s (s.id)}
        <li>
          <div class="who">
            <span class="name">{deviceLabel(s.user_agent)}{#if s.current} <span class="me">· Questo dispositivo</span>{/if}</span>
            <span class="muted"><span class="ui-mono">{s.ip ?? 'IP sconosciuto'}</span> · ultimo accesso {ago((now - s.last_seen) / 60)}</span>
          </div>
          {#if !s.current}<Button onclick={() => revoke(s)}>Esci</Button>{/if}
        </li>
      {/each}
    </ul>
    {#if others > 0}
      <div><Button kind="danger" onclick={revokeOthers}>Esci da tutti gli altri</Button></div>
    {/if}
  </section>
</Card>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  h4 { margin: 0; font: 600 14px/20px var(--font-sans); }
  .pin { display: flex; flex-direction: column; gap: var(--space-3); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--space-3); }
  .devices { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .devices li { display: flex; justify-content: space-between; align-items: center; gap: var(--space-3); flex-wrap: wrap; min-height: 44px; }
  .who { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .name { font: 500 14px/20px var(--font-sans); }
  .me { color: var(--ink-muted); font-weight: 400; }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
