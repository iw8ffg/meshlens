<script lang="ts">
  import { onDestroy } from 'svelte'
  import { send, ApiError } from '../lib/api'
  import Field from '../lib/ui/Field.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Logo from '../lib/shell/Logo.svelte'
  import MeshtasticBadge from '../lib/shell/MeshtasticBadge.svelte'
  import { pinError } from '../lib/settings'
  import { t } from '../lib/i18n/index.svelte'
  import type { AuthStatus } from '../lib/types'

  let { status, onsuccess }: { status: AuthStatus; onsuccess: () => void } = $props()

  let pin = $state('')
  let confirm = $state('')
  let message = $state('')
  let busy = $state(false)
  let lock = $state(0)
  let timer: ReturnType<typeof setInterval> | null = null

  function stopTimer() {
    if (timer) clearInterval(timer)
    timer = null
  }
  onDestroy(stopTimer)

  // Blocco temporaneo: conto alla rovescia, poi si puo' riprovare
  function startLock(seconds: number) {
    stopTimer()
    lock = Math.max(1, Math.round(seconds))
    timer = setInterval(() => {
      lock -= 1
      if (lock <= 0) {
        stopTimer()
        message = ''
      }
    }, 1000)
  }

  const setup = $derived(!status.pin_set && status.is_local)
  const remote = $derived(!status.pin_set && !status.is_local)
  // Primo PIN con l'accesso dalla rete attivo: almeno 6 cifre. Al login valgono anche i PIN
  // di 4-5 cifre già impostati.
  const minLen = $derived(setup ? (status.pin_min ?? 4) : 4)

  async function submit(e: Event) {
    e.preventDefault()
    message = ''
    const invalid = pinError(pin, minLen >= 6)
    if (invalid) {
      message = invalid
      return
    }
    if (setup && pin !== confirm) {
      message = t('login.mismatch')
      return
    }
    busy = true
    try {
      // /auth/setup imposta il PIN e il cookie di sessione: niente login aggiuntivo
      await send('POST', setup ? '/auth/setup' : '/auth/login', { pin })
      pin = confirm = ''
      onsuccess()
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        if (err.retryAfter) startLock(err.retryAfter)
        message = err.retryAfter ? t('login.tooMany') : t('login.tooManyLater')
      } else if (err instanceof ApiError && err.status === 401) {
        message = t('login.wrong')
      } else if (err instanceof ApiError && err.status === 400) {
        message = err.message.charAt(0).toUpperCase() + err.message.slice(1)
      } else {
        message = t('login.error')
      }
    } finally {
      busy = false
    }
  }
</script>

<main>
  <div class="card ui-card">
    <div class="brand">
      <Logo size={56} />
      <h1>MeshLens</h1>
    </div>
    {#if remote}
      <Banner kind="info" title={t('login.remoteTitle')}>{t('login.remoteBody')}</Banner>
    {:else}
      <form onsubmit={submit} novalidate>
        <h2>{setup ? t('login.setupTitle') : t('login.enterTitle')}</h2>
        {#if setup}<p class="ui-muted sub">{t('login.setupSub', { min: minLen })}</p>{/if}
        <Field label={t('login.pin')} for="pin" hint={setup ? undefined : t('login.hint')}>
          {#snippet children({ describedby, invalid })}
            <input
              id="pin"
              class="ui-input mono"
              class:err={invalid}
              type="password"
              inputmode="numeric"
              autocomplete={setup ? 'new-password' : 'current-password'}
              maxlength="12"
              aria-describedby={describedby}
              disabled={busy || lock > 0}
              bind:value={pin}
            />
          {/snippet}
        </Field>
        {#if setup}
          <Field label={t('login.repeat')} for="pin2" error={confirm && pin !== confirm ? t('login.mismatch') : undefined}>
            {#snippet children({ describedby, invalid })}
              <input
                id="pin2"
                class="ui-input mono"
                class:err={invalid}
                type="password"
                inputmode="numeric"
                autocomplete="new-password"
                maxlength="12"
                aria-describedby={describedby}
                disabled={busy}
                bind:value={confirm}
              />
            {/snippet}
          </Field>
        {/if}
        <Button type="submit" kind="primary" block disabled={busy || lock > 0}>
          {#if busy}{t('login.verifying')}{:else if lock > 0}{t('login.retryIn', { n: lock })}{:else}{setup ? t('login.set') : t('login.enter')}{/if}
        </Button>
        {#if message}<Banner kind="danger" title={message}>{#if lock > 0}{t('login.retryBanner', { n: lock })}{/if}</Banner>{/if}
      </form>
    {/if}
  </div>
  <MeshtasticBadge />
</main>

<style>
  main {
    min-height: 100dvh;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: var(--space-6);
    padding: calc(var(--space-4) + env(safe-area-inset-top)) var(--space-4) calc(var(--space-4) + env(safe-area-inset-bottom));
    background: var(--bg);
    color: var(--ink);
  }
  .card {
    width: 100%;
    max-width: 380px;
    display: flex;
    flex-direction: column;
    gap: var(--space-5);
    box-sizing: border-box;
    padding: var(--space-6);
  }
  .brand {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-2);
  }
  h1 {
    margin: 0;
    font: 600 24px/32px var(--font-sans);
  }
  h2 {
    margin: 0;
    font: 600 18px/24px var(--font-sans);
  }
  .sub {
    margin: 0;
    font: 400 14px/20px var(--font-sans);
  }
  form {
    display: flex;
    flex-direction: column;
    gap: var(--space-4);
  }
</style>
