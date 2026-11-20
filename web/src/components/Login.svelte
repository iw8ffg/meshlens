<script lang="ts">
  import { send, ApiError } from '../lib/api'
  import type { AuthStatus } from '../lib/types'

  let { status, onsuccess }: { status: AuthStatus; onsuccess: () => void } = $props()

  let pin = $state('')
  let confirm = $state('')
  let message = $state('')
  let busy = $state(false)

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
        message = `Troppi tentativi. Riprova tra ${err.retryAfter ?? '?'} secondi`
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
  <h1>MeshLens</h1>
  {#if remote}
    <p>Configura MeshLens dal PC</p>
  {:else}
    <form onsubmit={submit}>
      <h2>{setup ? 'Scegli un PIN' : 'Inserisci il PIN'}</h2>
      <input
        type="password"
        inputmode="numeric"
        autocomplete={setup ? 'new-password' : 'current-password'}
        maxlength="12"
        placeholder="PIN"
        bind:value={pin}
      />
      {#if setup}
        <input
          type="password"
          inputmode="numeric"
          autocomplete="new-password"
          maxlength="12"
          placeholder="Conferma PIN"
          bind:value={confirm}
        />
      {/if}
      <button type="submit" disabled={busy}>{setup ? 'Imposta PIN' : 'Entra'}</button>
      {#if message}<p class="err" role="alert">{message}</p>{/if}
    </form>
  {/if}
</main>

<style>
  main {
    max-width: 18rem;
    margin: 15vh auto;
    text-align: center;
  }
  form {
    display: flex;
    flex-direction: column;
    gap: 0.6rem;
  }
  input,
  button {
    padding: 0.5rem;
    font-size: 1rem;
  }
  .err {
    color: #f87171;
    margin: 0;
  }
</style>
