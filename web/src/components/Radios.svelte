<script lang="ts">
  import { getJSON, send, ApiError } from '../lib/api'
  import { app, setRadios } from '../lib/stores.svelte'
  import { sortPorts, stateClass, stateLabel } from '../lib/radios'
  import type { BleDevice, Port, Radio } from '../lib/types'

  let adding = $state(false)
  let kind = $state<'usb' | 'ble'>('usb')
  let ports = $state<Port[]>([])
  let ble = $state<BleDevice[]>([])
  let scanning = $state(false)
  let scanned = $state(false)
  let address = $state('')
  let name = $state('')
  let busy = $state(false)
  let error = $state('')
  let confirmId = $state<string | null>(null)

  const sortedPorts = $derived(sortPorts(ports))

  function msg(e: unknown): string {
    return e instanceof ApiError ? e.message : 'Operazione non riuscita'
  }

  async function reload() {
    try {
      setRadios(await getJSON<Radio[]>('/radios'))
    } catch {
      /* lo stato arriva comunque dal WebSocket */
    }
  }

  async function action(r: Radio, what: 'connect' | 'disconnect') {
    error = ''
    try {
      await send('POST', `/radios/${r.id}/${what}`)
    } catch (e) {
      error = msg(e)
    }
    await reload()
  }

  async function remove(r: Radio) {
    error = ''
    confirmId = null
    try {
      await send('DELETE', `/radios/${r.id}`)
    } catch (e) {
      error = msg(e)
    }
    await reload()
  }

  async function loadPorts() {
    try {
      ports = await getJSON<Port[]>('/radios/ports')
    } catch (e) {
      error = msg(e)
    }
  }

  function openAdd() {
    adding = true
    error = ''
    pickKind('usb')
  }

  function pickKind(k: 'usb' | 'ble') {
    kind = k
    address = ''
    name = ''
    if (k === 'usb') loadPorts()
  }

  async function scan() {
    scanning = true
    error = ''
    try {
      ble = await send<BleDevice[]>('POST', '/radios/ble-scan')
      scanned = true
    } catch (e) {
      error = msg(e)
    } finally {
      scanning = false
    }
  }

  async function add() {
    busy = true
    error = ''
    try {
      await send('POST', '/radios', { kind, address, name: name.trim() })
      adding = false
      await reload()
    } catch (e) {
      error = msg(e)
    } finally {
      busy = false
    }
  }

  const live = (r: Radio) =>
    r.state === 'connected' || r.state === 'connecting' || r.state === 'reconnecting'
</script>

<section>
  <h3>Radio</h3>
  {#if error}<p class="err" role="alert">{error}</p>{/if}

  {#each app.radios as r (r.id)}
    <div class="radio">
      <div class="head">
        <span class="dot {stateClass(r.state)}" aria-hidden="true"></span>
        <strong>{r.name}</strong>
        <span class="muted">{r.kind === 'usb' ? 'USB' : 'Bluetooth'} · {r.address}</span>
      </div>
      <div class="muted">
        {stateLabel(r.state)}{#if r.my_node_id}
          · nodo locale {r.my_node_name ?? ''} {r.my_node_id}{/if}
      </div>
      {#if r.error}<div class="err">{r.error}</div>{/if}
      <div class="btns">
        {#if live(r)}
          <button onclick={() => action(r, 'disconnect')}>Scollega</button>
        {:else}
          <button onclick={() => action(r, 'connect')}>Connetti</button>
        {/if}
        {#if confirmId === r.id}
          <span>Rimuovere "{r.name}"?</span>
          <button class="danger" onclick={() => remove(r)}>Conferma</button>
          <button onclick={() => (confirmId = null)}>Annulla</button>
        {:else}
          <button class="danger" onclick={() => (confirmId = r.id)}>Rimuovi</button>
        {/if}
      </div>
    </div>
  {:else}
    <p class="muted">Nessuna radio configurata.</p>
  {/each}

  {#if !adding}
    <button onclick={openAdd}>Aggiungi radio</button>
  {:else}
    <form
      class="add"
      onsubmit={(e) => {
        e.preventDefault()
        add()
      }}
    >
      <h4>Aggiungi radio</h4>
      <div class="btns">
        <button type="button" class:on={kind === 'usb'} onclick={() => pickKind('usb')}>USB</button>
        <button type="button" class:on={kind === 'ble'} onclick={() => pickKind('ble')}>Bluetooth</button>
      </div>

      {#if kind === 'usb'}
        <label>
          Porta
          <select bind:value={address}>
            <option value="">Scegli una porta…</option>
            {#each sortedPorts as p (p.device)}
              <option value={p.device} disabled={p.in_use_by !== null}>
                {p.device} — {p.description || 'sconosciuta'}{p.likely_meshtastic
                  ? ' (Meshtastic?)'
                  : ''}{p.in_use_by !== null ? ' (in uso)' : ''}
              </option>
            {/each}
          </select>
        </label>
        <button type="button" onclick={loadPorts}>Aggiorna elenco</button>
      {:else}
        <button type="button" onclick={scan} disabled={scanning}>
          {scanning ? 'Ricerca in corso… ~10 s' : 'Cerca'}
        </button>
        {#if scanned && ble.length === 0 && !scanning}<p class="muted">Nessuna radio trovata.</p>{/if}
        {#if ble.length > 0}
          <label>
            Radio trovata
            <select bind:value={address}>
              <option value="">Scegli una radio…</option>
              {#each ble as d (d.address)}
                <option value={d.address}>{d.name} ({d.address})</option>
              {/each}
            </select>
          </label>
        {/if}
        <p class="muted">
          Se Windows chiede un PIN, inserisci quello mostrato sullo schermo della radio. Se la radio non
          viene trovata, abbinala prima da Impostazioni Windows → Bluetooth.
        </p>
      {/if}

      <label>
        Nome
        <input bind:value={name} maxlength="40" placeholder="Es. Heltec base" />
      </label>
      <div class="btns">
        <button type="submit" disabled={busy || !address || !name.trim()}>Aggiungi</button>
        <button type="button" onclick={() => (adding = false)}>Annulla</button>
      </div>
    </form>
  {/if}
</section>

<style>
  section {
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  h3,
  h4 {
    margin: 0;
  }
  .radio,
  .add {
    border: 1px solid #1f2937;
    border-radius: 6px;
    padding: 8px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  .head {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .muted {
    color: #9ca3af;
    font-size: 0.85em;
  }
  .err {
    color: #f87171;
  }
  .dot {
    width: 10px;
    height: 10px;
    border-radius: 50%;
    flex: none;
  }
  .green {
    background: #22c55e;
  }
  .yellow {
    background: #eab308;
  }
  .red {
    background: #ef4444;
  }
  .gray {
    background: #6b7280;
  }
  .btns {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    align-items: center;
  }
  button,
  select,
  input {
    font: inherit;
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
  button.on {
    border-color: #2563eb;
    color: #93c5fd;
  }
  button.danger {
    color: #f87171;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 4px;
  }
</style>
