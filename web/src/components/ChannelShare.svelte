<script lang="ts">
  // WP4 (E13): link e QR dei canali. Contengono le chiavi: si mostrano solo dal PC dove gira
  // MeshLens, non si salvano (niente localStorage ne' store globali) e si cancellano alla chiusura.
  import { ApiError, getJSON } from '../lib/api'
  import { copyText } from '../lib/clipboard'
  import { exportChannels } from '../lib/config'
  import { t } from '../lib/i18n/index.svelte'
  import { qrMatrix, qrPath } from '../lib/qr'
  import type { AuthStatus } from '../lib/types'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Check from '../lib/ui/Check.svelte'
  import Modal from '../lib/ui/Modal.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'

  let { nodeId, open, onclose }: { nodeId: string; open: boolean; onclose: () => void } = $props()

  type Mode = 'replace' | 'add'
  let local = $state<boolean | null>(null)
  let url = $state('')
  let channels = $state<{ index: number; name: string }[]>([])
  let on = $state<Record<number, boolean>>({})
  let mode = $state<Mode>('replace')
  let busy = $state(false)
  let error = $state('')
  let copied = $state(false)

  const qr = $derived.by(() => {
    if (!url) return null
    try {
      return qrPath(qrMatrix(url))
    } catch {
      return null
    }
  })
  const picked = $derived(channels.filter((c) => on[c.index]).map((c) => c.index))
  const primaryMissing = $derived(mode === 'replace' && channels.some((c) => c.index === 0) && !on[0])

  function reset() {
    url = ''
    channels = []
    on = {}
    mode = 'replace'
    error = ''
    copied = false
    local = null
  }

  async function start() {
    reset()
    busy = true
    try {
      const st = await getJSON<AuthStatus>('/auth/status')
      local = st.is_local
      if (!local) return
      const res = await exportChannels(nodeId, null, false)
      channels = res.channels
      on = Object.fromEntries(res.channels.map((c) => [c.index, true]))
      url = res.url
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('channels.failed')
    } finally {
      busy = false
    }
  }

  async function refresh() {
    if (picked.length === 0 || primaryMissing) return
    busy = true
    error = ''
    copied = false
    try {
      const all = picked.length === channels.length
      url = (await exportChannels(nodeId, all ? null : picked, mode === 'add')).url
    } catch (e) {
      url = ''
      error = e instanceof ApiError ? e.message : t('channels.failed')
    } finally {
      busy = false
    }
  }

  async function copy() {
    copied = await copyText(url)
  }

  function close() {
    reset() // il link non resta in memoria
    onclose()
  }

  // apertura: chiede il link; chiusura: lo dimentica
  $effect(() => {
    if (open) void start()
    else reset()
  })
</script>

<Modal {open} title={t('channels.share.title')} confirmLabel={t('common.close')} onconfirm={close} oncancel={close}>
  <div class="cs">
    {#if local === false}
      <Banner kind="info" title={t('channels.share.localOnly')} />
    {:else}
      <Banner kind="warn" title={t('channels.share.warning')} />
      {#if channels.length}
        <Segmented
          items={[{ value: 'replace', label: t('channels.share.replace') }, { value: 'add', label: t('channels.share.add') }]}
          bind:value={mode}
          label={t('channels.share.mode')}
          onchange={() => void refresh()}
        />
        <div class="chs">
          {#each channels as c (c.index)}
            {#if c.index in on}
              <Check bind:checked={on[c.index]} label={t('channels.share.channel', { n: c.index, name: c.name || '–' })} disabled={busy} />
            {/if}
          {/each}
        </div>
        {#if primaryMissing}<p class="hint">{t('channels.share.primaryRequired')}</p>{/if}
        <div><Button disabled={busy || picked.length === 0 || primaryMissing} onclick={refresh}>{t('channels.share.update')}</Button></div>
      {/if}
      {#if qr && url}
        <!-- QR sempre scuro su chiaro: i lettori non riconoscono i colori invertiti del tema scuro -->
        <svg class="qr" viewBox={qr.viewBox} role="img" aria-label={t('channels.share.qrAria')} shape-rendering="crispEdges">
          <rect width="100%" height="100%" fill="#ffffff" />
          <path d={qr.d} fill="#000000" />
        </svg>
        <code class="url ui-mono">{url}</code>
        <div><Button icon="copy" onclick={copy}>{copied ? t('channels.share.copied') : t('channels.share.copy')}</Button></div>
      {/if}
      {#if error}<Banner kind="danger" title={error} />{/if}
    {/if}
  </div>
</Modal>

<style>
  .cs {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .chs {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-4);
  }
  .qr {
    width: min(280px, 100%);
    height: auto;
    align-self: center;
    border-radius: var(--radius-2, 8px);
  }
  .url {
    font-size: 13px;
    overflow-wrap: anywhere;
    word-break: break-all;
    max-height: 6em;
    overflow: auto;
  }
  .hint {
    margin: 0;
    color: var(--ink-muted);
    font-size: 13px;
  }
  :global(.vp-phone) .hint,
  :global(.vp-phone) .url {
    font-size: 14px;
  }
</style>
