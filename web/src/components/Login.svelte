<script lang="ts">
  import { onDestroy } from 'svelte'
  import { send, ApiError } from '../lib/api'
  import Field from '../lib/ui/Field.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Logo from '../lib/shell/Logo.svelte'
  import MeshtasticBadge from '../lib/shell/MeshtasticBadge.svelte'
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

  async function submit(e: Event) {
    e.preventDefault()
    message = ''
    if (!/^\d{4,12}$/.test(pin)) {
      message = 'Il PIN deve avere da 4 a 12 cifre'
      return
    }
    if (setup && pin !== confirm) {
      message = 'I due PIN non coincidono'
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
        message = err.retryAfter ? 'Troppi tentativi' : 'Troppi tentativi: riprova tra qualche minuto'
      } else if (err instanceof ApiError && err.status === 401) {
        message = 'PIN errato'
      } else {
        message = 'Errore di accesso'
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
      <Banner kind="info" title="Configura MeshLens dal PC">Il primo PIN si sceglie dal computer su cui gira MeshLens.</Banner>
    {:else}
      <form onsubmit={submit} novalidate>
        <h2>{setup ? 'Scegli un PIN' : 'Inserisci il PIN'}</h2>
        {#if setup}<p class="ui-muted sub">Da 4 a 12 cifre. Servirà per aprire MeshLens da questo e dagli altri dispositivi.</p>{/if}
        <Field label="PIN" for="pin" hint={setup ? undefined : 'Da 4 a 12 cifre'}>
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
          <Field label="Ripeti il PIN" for="pin2" error={confirm && pin !== confirm ? 'I due PIN non coincidono' : undefined}>
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
          {#if busy}Verifica in corso…{:else if lock > 0}Riprova tra {lock} s{:else}{setup ? 'Imposta PIN' : 'Entra'}{/if}
        </Button>
        {#if message}<Banner kind="danger" title={message}>{#if lock > 0}Riprova tra {lock} secondi.{/if}</Banner>{/if}
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
