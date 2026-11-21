<script lang="ts">
  import { getJSON, send, ApiError } from '../lib/api'
  import { app, setRadios, openConfig } from '../lib/stores.svelte'
  import { sortPorts, stateLabel } from '../lib/radios'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Badge from '../lib/ui/Badge.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Select from '../lib/ui/Select.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import Icon from '../lib/ui/Icon.svelte'
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
  let acting = $state(false) // azione su una radio in corso (Connetti/Scollega/Rimuovi)
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
    if (acting) return
    acting = true
    error = ''
    try {
      await send('POST', `/radios/${r.id}/${what}`)
    } catch (e) {
      error = msg(e)
    } finally {
      acting = false
    }
    await reload()
  }

  async function remove(r: Radio) {
    if (acting) return
    acting = true
    error = ''
    confirmId = null
    try {
      await send('DELETE', `/radios/${r.id}`)
    } catch (e) {
      error = msg(e)
    } finally {
      acting = false
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
    ble = []
    scanned = false
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

  const removing = $derived(app.radios.find((r) => r.id === confirmId) ?? null)
  const stateKind = (r: Radio): 'ok' | 'danger' | 'neutral' | 'warn' =>
    r.state === 'connected' ? 'ok' : r.state === 'error' ? 'danger' : r.state === 'disconnected' ? 'neutral' : 'warn'

  const live = (r: Radio) =>
    r.state === 'connected' || r.state === 'connecting' || r.state === 'reconnecting'
</script>

<section>
  <header>
    <h2>Radio</h2>
    {#if !adding}<Button kind="primary" icon="plus" onclick={openAdd}>Aggiungi radio</Button>{/if}
  </header>
  {#if error}<Banner kind="danger" title={error} />{/if}

  {#each app.radios as r (r.id)}
    <Card>
      <div class="radio">
        <div class="head">
          <Icon name={r.kind === 'usb' ? 'usb' : 'bt'} size={20} />
          <strong>{r.name}</strong>
          <Badge kind={stateKind(r)}>{stateLabel(r.state)}</Badge>
        </div>
        <div class="muted">
          {r.kind === 'usb' ? 'USB' : 'Bluetooth'} · <span class="ui-mono">{r.address}</span>{#if r.my_node_id}
            · nodo locale {r.my_node_name ?? ''} <span class="ui-mono">{r.my_node_id}</span>{/if}
        </div>
        {#if r.error}<Banner kind="danger" title="Errore della radio">{r.error}</Banner>{/if}
        <div class="btns">
          {#if live(r)}
            <Button disabled={acting} onclick={() => action(r, 'disconnect')}>Scollega</Button>
          {:else}
            <Button kind="primary" disabled={acting} onclick={() => action(r, 'connect')}>Connetti</Button>
          {/if}
          {#if r.state === 'connected' && r.my_node_id}
            <Button icon="settings" onclick={() => openConfig(r.my_node_id!, r.id)}>Configura</Button>
            <Button icon="key" onclick={() => openConfig(r.my_node_id!, r.id, 'adminkey')}>Chiave admin</Button>
          {/if}
          <Button kind="ghost" icon="trash" disabled={acting} onclick={() => (confirmId = r.id)}>Rimuovi</Button>
        </div>
      </div>
    </Card>
  {:else}
    {#if !adding}
      <Empty icon="radio" title="Nessuna radio configurata">Collega una radio via USB o Bluetooth per vedere la rete locale.</Empty>
    {/if}
  {/each}

  {#if adding}
    <Card>
      <form
        class="add"
        onsubmit={(e) => {
          e.preventDefault()
          add()
        }}
      >
        <h3>Aggiungi radio</h3>
        <Segmented
          label="Tipo di collegamento"
          items={[
            { value: 'usb', label: 'USB' },
            { value: 'ble', label: 'Bluetooth' },
          ]}
          value={kind}
          onchange={pickKind}
        />

        {#if kind === 'usb'}
          <Field label="Porta" for="radio-port">
            {#snippet children()}
              <Select id="radio-port" bind:value={address}>
                <option value="">Scegli una porta…</option>
                {#each sortedPorts as p (p.device)}
                  <option value={p.device} disabled={p.in_use_by !== null}>
                    {p.device} — {p.description || 'sconosciuta'}{p.likely_meshtastic
                      ? ' (Meshtastic?)'
                      : ''}{p.in_use_by !== null ? ' (in uso)' : ''}
                  </option>
                {/each}
              </Select>
            {/snippet}
          </Field>
          <div><Button icon="refresh" onclick={loadPorts}>Aggiorna elenco</Button></div>
        {:else}
          <div>
            <Button icon="bt" onclick={scan} disabled={scanning}>
              {scanning ? 'Ricerca in corso… circa 10 s' : 'Cerca'}
            </Button>
          </div>
          {#if scanned && ble.length === 0 && !scanning}<p class="muted">Nessuna radio trovata.</p>{/if}
          {#if ble.length > 0}
            <Field label="Radio trovata" for="radio-ble">
              {#snippet children()}
                <Select id="radio-ble" bind:value={address}>
                  <option value="">Scegli una radio…</option>
                  {#each ble as d (d.address)}
                    <option value={d.address}>{d.name} ({d.address})</option>
                  {/each}
                </Select>
              {/snippet}
            </Field>
          {/if}
          <p class="muted">
            Se Windows chiede un PIN, inserisci quello mostrato sullo schermo della radio. Se la radio non
            viene trovata, abbinala prima da Impostazioni Windows → Bluetooth.
          </p>
        {/if}

        <Field label="Nome" for="radio-name">
          {#snippet children()}
            <input id="radio-name" class="ui-input" bind:value={name} maxlength="40" placeholder="Es. Heltec base" />
          {/snippet}
        </Field>
        <div class="btns">
          <Button type="submit" kind="primary" disabled={busy || !address || !name.trim()}>Aggiungi</Button>
          <Button onclick={() => (adding = false)}>Annulla</Button>
        </div>
      </form>
    </Card>
  {/if}
</section>

<Modal open={removing !== null} title="Rimuovere la radio?" danger confirmLabel="Rimuovi" onconfirm={() => removing && remove(removing)} oncancel={() => (confirmId = null)}>
  <p>La radio "{removing?.name ?? ''}" verrà scollegata e rimossa dall'elenco. I dati già salvati restano.</p>
</Modal>

<style>
  section { padding: var(--space-4); display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-3); flex-wrap: wrap; }
  h2 { margin: 0; font: 600 18px/24px var(--font-sans); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  .radio, .add { display: flex; flex-direction: column; gap: var(--space-3); }
  .head { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); margin: 0; }
  .btns { display: flex; gap: var(--space-2); flex-wrap: wrap; align-items: center; }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
