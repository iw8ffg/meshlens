<script lang="ts">
  import { onDestroy, onMount } from 'svelte'
  import { ApiError, getJSON, send } from '../../lib/api'
  import { ago } from '../../lib/format'
  import { t } from '../../lib/i18n/index.svelte'
  import { deviceLabel, pinError } from '../../lib/settings'
  import type { AuthStatus, SessionInfo } from '../../lib/types'
  import Badge from '../../lib/ui/Badge.svelte'
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
      listError = errMsg(e, t('settings.dev.listFailed'))
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
      pinMsg = t('settings.dev.mismatch')
      return
    }
    busy = true
    try {
      await send('POST', '/auth/pin', { current_pin: current, new_pin: next })
      current = next = confirm = ''
      pinOk = t('settings.dev.changed')
      await Promise.all([loadStatus(), loadSessions()])
    } catch (e) {
      if (e instanceof ApiError && e.status === 403) pinMsg = t('settings.dev.wrong')
      else if (e instanceof ApiError && e.status === 429)
        pinMsg = e.retryAfter ? t('settings.dev.tooMany', { n: e.retryAfter }) : t('settings.dev.tooManyLater')
      else pinMsg = errMsg(e, t('settings.dev.changeFailed'))
    } finally {
      busy = false
    }
  }

  async function revoke(s: SessionInfo) {
    listError = ''
    try {
      await send('DELETE', `/auth/sessions/${encodeURIComponent(s.id)}`)
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 404)) listError = errMsg(e, t('settings.dev.logoutFailed'))
    }
    await loadSessions()
  }

  async function revokeOthers() {
    listError = ''
    try {
      await send('POST', '/auth/sessions/revoke-others')
    } catch (e) {
      listError = errMsg(e, t('settings.dev.logoutFailed'))
    }
    await loadSessions()
  }
</script>

<Card>
  <section class="sec">
    <h3>{t('settings.dev.title')}</h3>
    {#if status?.pin_short}
      <Banner kind="warn" title={t('settings.dev.pinShort')} />
    {/if}

    <!-- niente <form>: questa scheda sta dentro il modulo delle impostazioni -->
    <div class="pin" role="group" aria-labelledby="pin-title">
      <h4 id="pin-title">{t('settings.dev.changePin')}</h4>
      <div class="grid">
        <Field label={t('settings.dev.current')} for="pin-cur">
          {#snippet children()}
            <input id="pin-cur" class="ui-input ui-mono" type="password" inputmode="numeric" autocomplete="current-password" maxlength="12" disabled={busy} bind:value={current} onkeydown={onPinKey} />
          {/snippet}
        </Field>
        <Field label={t('settings.dev.new')} for="pin-new" hint={lan ? t('settings.dev.hint6') : t('settings.dev.hint4')}>
          {#snippet children({ describedby })}
            <input id="pin-new" class="ui-input ui-mono" type="password" inputmode="numeric" autocomplete="new-password" maxlength="12" aria-describedby={describedby} disabled={busy} bind:value={next} onkeydown={onPinKey} />
          {/snippet}
        </Field>
        <Field label={t('settings.dev.repeat')} for="pin-conf" error={confirm && next !== confirm ? t('settings.dev.mismatch') : undefined}>
          {#snippet children({ describedby, invalid })}
            <input id="pin-conf" class="ui-input ui-mono" class:err={invalid} type="password" inputmode="numeric" autocomplete="new-password" maxlength="12" aria-describedby={describedby} aria-invalid={invalid} disabled={busy} bind:value={confirm} onkeydown={onPinKey} />
          {/snippet}
        </Field>
      </div>
      <div><Button onclick={changePin} disabled={busy || !current || !next || !confirm}>{t('settings.dev.changePin')}</Button></div>
      {#if pinMsg}<Banner kind="danger" title={pinMsg} />{/if}
      {#if pinOk}<Banner kind="ok" title={pinOk} />{/if}
    </div>

    <h4>{t('settings.dev.connected')}</h4>
    {#if listError}<Banner kind="danger" title={listError} />{/if}
    <ul class="devices">
      {#each sessions as s (s.id)}
        <li>
          <div class="who">
            <span class="name">{deviceLabel(s.user_agent)}{#if s.role === 'guest'} <Badge kind="info" icon="eye">{t('guest.sessionRole')}</Badge>{/if}{#if s.current} <span class="me">{t('settings.dev.thisDevice')}</span>{/if}</span>
            <span class="muted"><span class="ui-mono">{s.ip ?? t('settings.dev.unknownIp')}</span> · {t('settings.dev.lastSeen', { ago: ago((now - s.last_seen) / 60) })}</span>
          </div>
          {#if !s.current}<Button onclick={() => revoke(s)}>{t('settings.dev.logout')}</Button>{/if}
        </li>
      {/each}
    </ul>
    {#if others > 0}
      <div><Button kind="danger" onclick={revokeOthers}>{t('settings.dev.logoutOthers')}</Button></div>
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
