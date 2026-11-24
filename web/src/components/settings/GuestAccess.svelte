<script lang="ts">
  // Accesso ospite (WP6, E19): PIN ospite e interruttore. Il PIN e l'accensione si gestiscono
  // solo da questo PC (il server lo impone); dalla rete si puo' solo spegnere.
  import { onMount } from 'svelte'
  import { ApiError } from '../../lib/api'
  import { clearGuestPin, guestPinError, guestStatus, setGuestEnabled, setGuestPin, GUEST_PIN_MAX, GUEST_PIN_MIN } from '../../lib/guest'
  import { t } from '../../lib/i18n/index.svelte'
  import type { GuestStatus } from '../../lib/types'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Field from '../../lib/ui/Field.svelte'
  import Switch from '../../lib/ui/Switch.svelte'

  let status = $state<GuestStatus | null>(null)
  let loadError = $state(false)
  let pin = $state('')
  let confirm = $state('')
  let error = $state('')
  let ok = $state('')
  let busy = $state(false)
  let enabled = $state(false)

  const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : t('guest.card.failed'))

  function apply(s: GuestStatus) {
    status = s
    enabled = s.enabled
  }

  async function load() {
    try {
      apply(await guestStatus())
      loadError = false
    } catch {
      loadError = true
    }
  }

  onMount(() => void load())

  async function run(fn: () => Promise<GuestStatus>, okMsg = '') {
    error = ok = ''
    busy = true
    try {
      apply(await fn())
      ok = okMsg
    } catch (e) {
      error = errMsg(e)
      if (status) enabled = status.enabled // l'interruttore torna com'era
    } finally {
      busy = false
    }
  }

  async function savePin() {
    const err = guestPinError(pin)
    if (err) {
      error = err
      ok = ''
      return
    }
    if (pin !== confirm) {
      error = t('guest.mismatch')
      ok = ''
      return
    }
    await run(() => setGuestPin(pin), t('guest.card.pinSaved'))
    if (!error) pin = confirm = ''
  }

  // Dentro il modulo di Impostazioni: Invio salva il PIN ospite invece delle impostazioni
  function onPinKey(e: KeyboardEvent) {
    if (e.key !== 'Enter') return
    e.preventDefault()
    if (!busy && pin && confirm) void savePin()
  }

  const canTurnOn = $derived(!!status?.local && !!status?.pin_set)
</script>

<Card>
  <section class="sec">
    <h3>{t('guest.card.title')}</h3>
    <p class="ui-hint">{t('guest.card.intro')}</p>
    {#if loadError}
      <Banner kind="danger" title={t('guest.card.loadFailed')} />
    {:else if status}
      {#if !status.local}<Banner kind="info" title={t('guest.card.localOnly')} />{/if}
      {#if status.enabled && !status.lan_access}<Banner kind="warn" title={t('guest.card.lanOff')} />{/if}

      <div>
        <Switch
          bind:checked={enabled}
          label={t('guest.card.enabled')}
          disabled={busy || (!status.enabled && !canTurnOn)}
          onchange={(v) => void run(() => setGuestEnabled(v))} />
      </div>
      {#if !status.pin_set}<p class="ui-hint">{t('guest.card.noPin')}</p>{/if}
      {#if status.enabled}<p class="ui-hint">{t('guest.card.sessions', { n: status.sessions })}</p>{/if}

      {#if status.local}
        <!-- niente <form>: questa scheda sta dentro il modulo delle impostazioni -->
        <div class="pin" role="group" aria-labelledby="guest-pin-title">
          <h4 id="guest-pin-title">{status.pin_set ? t('guest.card.pinSet') : t('guest.card.pinMissing')}</h4>
          <div class="grid">
            <Field label={t('guest.card.newPin')} for="guest-pin" hint={t('guest.card.hint', { min: GUEST_PIN_MIN, max: GUEST_PIN_MAX })}>
              {#snippet children({ describedby })}
                <input id="guest-pin" class="ui-input ui-mono" type="password" inputmode="numeric" autocomplete="new-password" maxlength="12" aria-describedby={describedby} disabled={busy} bind:value={pin} onkeydown={onPinKey} />
              {/snippet}
            </Field>
            <Field label={t('guest.card.repeat')} for="guest-pin2" error={confirm && pin !== confirm ? t('guest.mismatch') : undefined}>
              {#snippet children({ describedby, invalid })}
                <input id="guest-pin2" class="ui-input ui-mono" class:err={invalid} type="password" inputmode="numeric" autocomplete="new-password" maxlength="12" aria-describedby={describedby} aria-invalid={invalid} disabled={busy} bind:value={confirm} onkeydown={onPinKey} />
              {/snippet}
            </Field>
          </div>
          <div class="btns">
            <Button onclick={savePin} disabled={busy || !pin || !confirm}>{status.pin_set ? t('guest.card.changePin') : t('guest.card.setPin')}</Button>
            {#if status.pin_set}
              <Button kind="danger" disabled={busy} onclick={() => void run(clearGuestPin, t('guest.card.pinCleared'))}>{t('guest.card.clearPin')}</Button>
            {/if}
          </div>
        </div>
      {/if}
      {#if error}<Banner kind="danger" title={error} />{/if}
      {#if ok}<Banner kind="ok" title={ok} />{/if}
    {/if}
  </section>
</Card>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  h4 { margin: 0; font: 600 14px/20px var(--font-sans); }
  .pin { display: flex; flex-direction: column; gap: var(--space-3); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: var(--space-3); }
  .btns { display: flex; gap: var(--space-2); flex-wrap: wrap; }
</style>
