<script lang="ts">
  import { getJSON, send, ApiError } from '../lib/api'
  import { app, setRadios, openConfig } from '../lib/stores.svelte'
  import { sortPorts, stateLabel } from '../lib/radios'
  import { t } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
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
  import StoreForward from './StoreForward.svelte'
  import Toast from '../lib/ui/Toast.svelte'
  import { clearSfNotice, sf } from '../lib/storeforward.svelte'
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
  let sfRadioId = $state<string | null>(null) // radio per cui e' aperto «Recupera messaggi persi»

  const sortedPorts = $derived(sortPorts(ports))

  function msg(e: unknown): string {
    return e instanceof ApiError ? e.message : t('radios.failed')
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

  const sfRadio = $derived(app.radios.find((r) => r.id === sfRadioId && r.state === 'connected') ?? null)
  const removing = $derived(app.radios.find((r) => r.id === confirmId) ?? null)
  const stateKind = (r: Radio): 'ok' | 'danger' | 'neutral' | 'warn' =>
    r.state === 'connected' ? 'ok' : r.state === 'error' ? 'danger' : r.state === 'disconnected' ? 'neutral' : 'warn'

  const live = (r: Radio) =>
    r.state === 'connected' || r.state === 'connecting' || r.state === 'reconnecting'
</script>

<section>
  <header>
    <h2>{t('radios.title')}</h2>
    {#if !adding}<Button kind="primary" icon="plus" onclick={openAdd}>{t('radios.add')}</Button>{/if}
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
          {r.kind === 'usb' ? t('radios.usb') : t('radios.bluetooth')} · <span class="ui-mono">{r.address}</span>{#if r.my_node_id}
            {t('radios.localNode', { name: r.my_node_name ?? '' })} <span class="ui-mono">{r.my_node_id}</span>{/if}
        </div>
        {#if r.error}<Banner kind="danger" title={t('radios.errorTitle')}>{translateServer(r.error)}</Banner>{/if}
        <div class="btns">
          {#if live(r)}
            <Button disabled={acting} onclick={() => action(r, 'disconnect')}>{t('radios.disconnect')}</Button>
          {:else}
            <Button kind="primary" disabled={acting} onclick={() => action(r, 'connect')}>{t('radios.connect')}</Button>
          {/if}
          {#if r.state === 'connected' && r.my_node_id}
            <Button icon="settings" onclick={() => openConfig(r.my_node_id!, r.id)}>{t('radios.configure')}</Button>
            <Button icon="key" onclick={() => openConfig(r.my_node_id!, r.id, 'adminkey')}>{t('radios.adminKey')}</Button>
          {/if}
          {#if r.state === 'connected'}
            <Button icon="refresh" onclick={() => (sfRadioId = r.id)}>{t('radios.sf')}</Button>
          {/if}
          <Button kind="ghost" icon="trash" disabled={acting} onclick={() => (confirmId = r.id)}>{t('radios.remove')}</Button>
        </div>
      </div>
    </Card>
  {:else}
    {#if !adding}
      <Empty icon="radio" title={t('radios.empty.title')}>{t('radios.empty.body')}</Empty>
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
        <h3>{t('radios.add')}</h3>
        <Segmented
          label={t('radios.kind')}
          items={[
            { value: 'usb', label: t('radios.usb') },
            { value: 'ble', label: t('radios.bluetooth') },
          ]}
          value={kind}
          onchange={pickKind}
        />

        {#if kind === 'usb'}
          <Field label={t('radios.port')} for="radio-port">
            {#snippet children()}
              <Select id="radio-port" bind:value={address}>
                <option value="">{t('radios.pickPort')}</option>
                {#each sortedPorts as p (p.device)}
                  <option value={p.device} disabled={p.in_use_by !== null}>
                    {p.device} — {p.description || t('radios.unknownPort')}{p.likely_meshtastic
                      ? ` ${t('radios.maybe')}`
                      : ''}{p.in_use_by !== null ? ` ${t('radios.inUse')}` : ''}
                  </option>
                {/each}
              </Select>
            {/snippet}
          </Field>
          <div><Button icon="refresh" onclick={loadPorts}>{t('radios.refresh')}</Button></div>
        {:else}
          <div>
            <Button icon="bt" onclick={scan} disabled={scanning}>
              {scanning ? t('radios.scanning') : t('radios.scan')}
            </Button>
          </div>
          {#if scanned && ble.length === 0 && !scanning}<p class="muted">{t('radios.noneFound')}</p>{/if}
          {#if ble.length > 0}
            <Field label={t('radios.found')} for="radio-ble">
              {#snippet children()}
                <Select id="radio-ble" bind:value={address}>
                  <option value="">{t('radios.pickRadio')}</option>
                  {#each ble as d (d.address)}
                    <option value={d.address}>{d.name} ({d.address})</option>
                  {/each}
                </Select>
              {/snippet}
            </Field>
          {/if}
          <p class="muted">
            {t('radios.bleNote')}
          </p>
        {/if}

        <Field label={t('radios.name')} for="radio-name">
          {#snippet children()}
            <input id="radio-name" class="ui-input" bind:value={name} maxlength="40" placeholder={t('radios.namePh')} />
          {/snippet}
        </Field>
        <div class="btns">
          <Button type="submit" kind="primary" disabled={busy || !address || !name.trim()}>{t('radios.addBtn')}</Button>
          <Button onclick={() => (adding = false)}>{t('common.cancel')}</Button>
        </div>
      </form>
    </Card>
  {/if}
</section>

{#if sfRadio}
  <StoreForward radio={sfRadio} onclose={() => (sfRadioId = null)} />
{/if}

{#if sf.notice}
  <div class="sf-toast"><Toast kind="ok" onclose={clearSfNotice}>{sf.notice}</Toast></div>
{/if}

<Modal open={removing !== null} title={t('radios.rm.title')} danger confirmLabel={t('radios.remove')} onconfirm={() => removing && remove(removing)} oncancel={() => (confirmId = null)}>
  <p>{t('radios.rm.body', { name: removing?.name ?? '' })}</p>
</Modal>

<style>
  .sf-toast { position: fixed; bottom: var(--space-4); left: 50%; transform: translateX(-50%); z-index: 1000; }
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
