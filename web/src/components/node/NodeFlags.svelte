<script lang="ts">
  // WP4 (E3): preferito/ignorato nel NodeDB delle radio collegate e azione «Ignora nodo».
  // Props fissate dal contratto §10.2.
  import { onDestroy, untrack } from 'svelte'
  import { ApiError } from '../../lib/api'
  import { getRadioFlags, ignoreWarning, nodeName, setIgnored, setRadioFlags } from '../../lib/nodes'
  import { app, upsertNodes } from '../../lib/stores.svelte'
  import { onWsResync } from '../../lib/wsext'
  import { t } from '../../lib/i18n/index.svelte'
  import { translateServer } from '../../lib/i18n/server'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Check from '../../lib/ui/Check.svelte'
  import Modal from '../../lib/ui/Modal.svelte'
  import Switch from '../../lib/ui/Switch.svelte'
  import type { Node, RadioFlagResult, RadioFlags } from '../../lib/types'

  interface Props {
    node: Node
  }
  let { node }: Props = $props()

  const connected = $derived(app.radios.filter((r) => r.state === 'connected'))
  // il nodo di una propria radio non si marca ne' si ignora
  const ownRadio = $derived(!!node.is_local_radio || app.radios.some((r) => r.my_node_id === node.id))

  let flags = $state<RadioFlags[]>([])
  let busy = $state<string | null>(null)
  let error = $state('')
  let seq = 0

  async function load() {
    const id = node.id
    const my = ++seq
    if (connected.length === 0 || ownRadio) {
      flags = []
      return
    }
    try {
      const res = await getRadioFlags(id)
      if (my === seq && id === node.id) flags = res.radios
    } catch {
      if (my === seq) flags = []
    }
  }

  // ricarica quando cambia il nodo o il numero di radio collegate
  const nodeId = $derived(node.id)
  const nConnected = $derived(connected.length)
  $effect(() => {
    void nodeId
    void nConnected
    error = ''
    // load() legge app.radios: senza untrack l'effetto riscatterebbe a ogni evento `radios`
    untrack(() => void load())
  })
  const offResync = onWsResync(() => void load())
  onDestroy(offResync)

  function failures(list: RadioFlagResult[]): string {
    return list
      .filter((r) => !r.ok)
      .map((r) => `${app.radios.find((x) => x.id === r.radio_id)?.name ?? r.radio_id}: ${translateServer(r.error ?? '')}`)
      .join(' · ')
  }

  async function setFlag(radioId: string, flag: 'favorite' | 'ignored', value: boolean) {
    busy = radioId
    error = ''
    try {
      const res = await setRadioFlags(node.id, flag === 'favorite' ? { favorite: value } : { ignored: value }, radioId)
      const bad = failures(res.radios)
      if (bad) error = t('nodeflags.radiosFailed', { list: bad })
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('nodeflags.failed')
    } finally {
      busy = null
      await load()
    }
  }

  let confirmOpen = $state(false)
  let alsoRadios = $state(true)
  let ignoreBusy = $state(false)

  function askIgnore() {
    alsoRadios = connected.length > 0
    confirmOpen = true
  }

  async function doIgnore() {
    confirmOpen = false
    ignoreBusy = true
    error = ''
    try {
      const res = await setIgnored(node.id, !node.is_ignored, alsoRadios && connected.length > 0)
      upsertNodes([res.node])
      const bad = failures(res.radios)
      // avviso del server (es. un tuo nodo: ignorato solo in MeshLens, mai sulle radio)
      error = [ignoreWarning(res), bad ? t('nodeflags.radiosFailed', { list: bad }) : ''].filter(Boolean).join(' · ')
    } catch (e) {
      // 400/409 (radio propria, sessione admin remota aperta sul nodo): il testo del server,
      // gia' tradotto, spiega cosa fare
      error = e instanceof ApiError && e.message ? e.message : t('nodeflags.failed')
    } finally {
      ignoreBusy = false
      await load()
    }
  }
</script>

{#if !ownRadio}
  <Button icon="eye" disabled={ignoreBusy} onclick={askIgnore}>{node.is_ignored ? t('nodeflags.unignore') : t('nodeflags.ignore')}</Button>
  <div class="nf">
    {#if flags.length > 0}
      <ul>
        {#each flags as f (f.radio_id)}
          <li>
            <b>{t('nodeflags.onRadio', { name: f.radio_name ?? f.radio_id })}</b>
            <Switch checked={f.favorite} disabled={busy === f.radio_id} label={t('nodeflags.favoriteOnRadio')} onchange={(v) => setFlag(f.radio_id, 'favorite', v)} />
            <Switch checked={f.ignored} disabled={busy === f.radio_id} label={t('nodeflags.ignoredOnRadio')} onchange={(v) => setFlag(f.radio_id, 'ignored', v)} />
          </li>
        {/each}
      </ul>
      <p class="hint">{t('nodeflags.help')}</p>
    {/if}
    {#if error}<Banner kind="warn" title={error} />{/if}
  </div>

  <Modal
    open={confirmOpen}
    title={node.is_ignored ? t('nodeflags.unconfirmTitle', { name: nodeName(node) }) : t('nodeflags.confirmTitle', { name: nodeName(node) })}
    confirmLabel={node.is_ignored ? t('nodeflags.unignore') : t('nodeflags.ignore')}
    onconfirm={doIgnore}
    oncancel={() => (confirmOpen = false)}
  >
    <p class="txt">{node.is_ignored ? t('nodeflags.unconfirmText') : t('nodeflags.confirmText')}</p>
    {#if connected.length > 0}
      <Check bind:checked={alsoRadios} label={node.is_ignored ? t('nodeflags.alsoRadiosOff') : t('nodeflags.alsoRadios')} />
    {/if}
  </Modal>
{/if}

<style>
  .nf {
    flex-basis: 100%;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .nf:empty {
    display: none;
  }
  ul {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  li {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: var(--space-2) var(--space-4);
    font-size: 14px;
  }
  .hint {
    margin: 0;
    color: var(--ink-muted);
    font-size: 13px;
  }
  .txt {
    margin: 0 0 var(--space-3);
  }
  :global(.vp-phone) .hint {
    font-size: 14px;
  }
</style>
