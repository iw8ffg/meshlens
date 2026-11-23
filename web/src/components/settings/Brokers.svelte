<script lang="ts">
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Field from '../../lib/ui/Field.svelte'
  import Modal from '../../lib/ui/Modal.svelte'
  import Select from '../../lib/ui/Select.svelte'
  import Switch from '../../lib/ui/Switch.svelte'
  import { app } from '../../lib/stores.svelte'
  import { ApiError, importChannelLink, importChannelsFromRadio, revealChannelPsk, type ChannelImport } from '../../lib/api'
  import {
    channelNameError,
    DEFAULT_BROKER_ID,
    isChannelLink,
    MAX_BROKER_CHANNELS,
    MAX_BROKERS,
    newBroker,
    portFor,
    pskError,
  } from '../../lib/brokers'
  import { joinLines, parseLines, type AppSettings, type Broker } from '../../lib/settings'
  import { num } from '../../lib/format'
  import { t } from '../../lib/i18n/index.svelte'
  import { translateServer } from '../../lib/i18n/server'

  let { brokers = $bindable(), dirty, onimported }: { brokers: Broker[]; dirty: boolean; onimported: (s: AppSettings) => void } = $props()

  const MASK_REF = /^••••#(\d+)$/

  let drafts = $state<Record<number, { name: string; psk: string }>>({})
  let links = $state<Record<number, string>>({})
  let radioSel = $state<Record<number, string>>({})
  let revealed = $state<Record<string, string>>({})
  let visible = $state<Record<string, boolean>>({})
  let notes = $state<Record<string, string>>({})
  let results = $state<Record<number, string>>({})
  let busyImport = $state<Record<number, boolean>>({})
  let toDelete = $state<number | null>(null)

  const radios = $derived(app.radios.filter((r) => r.state === 'connected'))

  function statusOf(b: Broker) {
    return app.status?.mqtt?.brokers?.find((s) => s.id === b.id)
  }

  /** Topic rifiutati dal broker nella connessione corrente (solo se attivo e connesso). */
  function refusedOf(b: Broker): string[] {
    if (!b.enabled || !b.id) return []
    const s = statusOf(b)
    return s?.connected ? (s.refused_topics ?? []) : []
  }

  function tone(b: Broker): 'ok' | 'ko' | 'off' {
    if (!b.enabled || !b.id) return 'off'
    return statusOf(b)?.connected ? 'ok' : 'ko'
  }

  function statusText(b: Broker): string {
    const s = statusOf(b)
    if (!b.id) return t('settings.br.unsaved')
    if (!b.enabled) return t('settings.br.off')
    if (!s) return t('settings.br.waiting')
    if (s.connected) return t('settings.br.connected', { rate: num(s.msgs_per_s, 1) })
    return s.last_error ? t('settings.br.notConnectedErr', { err: translateServer(s.last_error) }) : t('settings.br.notConnected')
  }

  const chanKey = (bi: number, ci: number) => `${bi}:${ci}`

  // Gli indici dei canali cambiano quando se ne toglie uno o si ricarica l'elenco: le chiavi mostrate si azzerano.
  function clearUi() {
    revealed = {}
    visible = {}
    notes = {}
  }

  function addBroker() {
    if (brokers.length >= MAX_BROKERS) return
    brokers = [...brokers, newBroker()]
  }

  function removeBroker() {
    if (toDelete === null) return
    brokers = brokers.filter((_, i) => i !== toDelete)
    toDelete = null
    drafts = {}
    links = {}
    radioSel = {}
    results = {}
    clearUi()
  }

  function setTopics(b: Broker, text: string) {
    b.topics = parseLines(text)
  }

  function setKeys(b: Broker, text: string) {
    b.extra_keys = parseLines(text)
  }

  function removeChannel(b: Broker, ci: number) {
    b.channels = b.channels.filter((_, i) => i !== ci)
    clearUi()
  }

  function setPsk(b: Broker, bi: number, ci: number, v: string) {
    b.channels[ci].psk = v.trim()
    delete revealed[chanKey(bi, ci)]
  }

  async function toggleEye(b: Broker, bi: number, ci: number) {
    const k = chanKey(bi, ci)
    if (k in revealed || visible[k]) {
      delete revealed[k]
      visible[k] = false
      return
    }
    const m = MASK_REF.exec(b.channels[ci].psk)
    if (!m) {
      visible[k] = true
      return
    }
    if (!b.id || dirty) {
      notes[k] = t('settings.br.saveFirst')
      return
    }
    try {
      revealed[k] = (await revealChannelPsk(b.id, Number(m[1]))).psk
      delete notes[k]
    } catch (err) {
      notes[k] = err instanceof ApiError && err.status === 403 ? t('settings.br.localOnly') : err instanceof ApiError ? err.message : t('settings.br.keyUnavailable')
    }
  }

  function pskProblem(psk: string): string | null {
    return psk === '' ? t('settings.br.keyMissing') : pskError(psk)
  }

  function nameProblem(b: Broker, ci: number): string | null {
    return channelNameError(b.channels[ci].name, b.channels.filter((_, i) => i !== ci).map((c) => c.name.trim()))
  }

  const draftOf = (bi: number) => drafts[bi] ?? { name: '', psk: '' }
  const draftNameError = (b: Broker, bi: number) => channelNameError(draftOf(bi).name, b.channels.map((c) => c.name.trim()))
  const draftPskError = (bi: number) => pskError(draftOf(bi).psk)

  function addChannel(b: Broker, bi: number) {
    const d = draftOf(bi)
    if (draftNameError(b, bi) || draftPskError(bi) || b.channels.length >= MAX_BROKER_CHANNELS) return
    b.channels = [...b.channels, { name: d.name.trim(), psk: d.psk.trim() }]
    drafts[bi] = { name: '', psk: '' }
  }

  const importOff = (b: Broker) => dirty || !b.id

  function summary(r: ChannelImport): string {
    const none = t('settings.br.none')
    const added = r.added.length ? r.added.join(', ') : none
    const skipped = r.skipped.length ? r.skipped.map((s) => `${s.name} (${translateServer(s.reason)})`).join(', ') : none
    return t('settings.br.summary', { added, skipped })
  }

  async function runImport(bi: number, b: Broker, call: (id: string) => Promise<ChannelImport>) {
    if (!b.id || busyImport[bi]) return
    busyImport[bi] = true
    try {
      const r = await call(b.id)
      onimported(r.settings)
      clearUi()
      results[bi] = summary(r)
    } catch (err) {
      results[bi] = err instanceof ApiError ? err.message : t('settings.br.importFailed')
    } finally {
      busyImport[bi] = false
    }
  }

  const importLink = (bi: number, b: Broker) => runImport(bi, b, (id) => importChannelLink(id, (links[bi] ?? '').trim()))
  const importRadio = (bi: number, b: Broker) => runImport(bi, b, (id) => importChannelsFromRadio(id, radioSel[bi] ?? radios[0]?.id ?? ''))
</script>

<div class="brokers">
  {#each brokers as b, bi (b)}
    <Card>
      <section class="sec">
        <div class="head">
          <span class="dot {tone(b)}"></span>
          <strong class="nm">{b.name || t('settings.br.unnamed')}</strong>
          <span class="st">{statusText(b)}</span>
        </div>
        {#if refusedOf(b).length}
          <Banner kind="warn" title={refusedOf(b).length >= b.topics.length ? t('settings.br.refusedAllTitle') : t('settings.br.refusedTitle')}>
            {t('settings.br.refusedBody', { topics: refusedOf(b).join(', ') })}
          </Banner>
        {/if}
        <div class="grid">
          <Field label={t('settings.br.name')} for="br-name-{bi}">{#snippet children()}<input id="br-name-{bi}" class="ui-input" type="text" maxlength="40" bind:value={b.name} />{/snippet}</Field>
          <div class="sw"><Switch bind:checked={b.enabled} label={t('settings.br.enabled')} /></div>
          <Field label={t('settings.br.host')} for="br-host-{bi}">{#snippet children()}<input id="br-host-{bi}" class="ui-input" type="text" autocomplete="off" bind:value={b.host} />{/snippet}</Field>
          <Field label={t('settings.br.port')} for="br-port-{bi}">{#snippet children()}<input id="br-port-{bi}" class="ui-input ui-mono" type="number" min="1" max="65535" bind:value={b.port} />{/snippet}</Field>
          <Field label={t('settings.br.user')} for="br-user-{bi}">{#snippet children()}<input id="br-user-{bi}" class="ui-input" type="text" autocomplete="off" bind:value={b.username} />{/snippet}</Field>
          <Field label={t('settings.br.password')} for="br-pass-{bi}">{#snippet children()}<input id="br-pass-{bi}" class="ui-input" type="password" autocomplete="new-password" bind:value={b.password} />{/snippet}</Field>
        </div>
        <Switch bind:checked={b.tls} label={t('settings.br.tls')} onchange={(v) => (b.port = portFor(v, b.port))} />
        <Switch bind:checked={b.encryption} label={t('settings.br.encryption')} />
        <p class="ui-hint">{t('settings.br.encHint')}</p>

        <Field label={t('settings.br.topics')} for="br-topics-{bi}" hint={t('settings.br.topicsHint')}>
          {#snippet children()}<textarea id="br-topics-{bi}" class="ui-input area" rows="3" value={joinLines(b.topics)} onchange={(e) => setTopics(b, e.currentTarget.value)}></textarea>{/snippet}
        </Field>
        <Field label={t('settings.br.extraKeys')} for="br-keys-{bi}">
          {#snippet children()}<textarea id="br-keys-{bi}" class="ui-input area" rows="3" value={joinLines(b.extra_keys)} onchange={(e) => setKeys(b, e.currentTarget.value)}></textarea>{/snippet}
        </Field>

        <h4>{t('settings.br.channels')}</h4>
        {#if b.channels.length === 0}<p class="ui-hint">{t('settings.br.noChannels')}</p>{/if}
        <ul class="chans">
          {#each b.channels as c, ci (ci)}
            {@const k = chanKey(bi, ci)}
            <li>
              <div class="row">
                <Field label={t('settings.br.channelName')} for="br-cn-{bi}-{ci}" error={nameProblem(b, ci) ?? undefined}>
                  {#snippet children({ describedby, invalid })}<input id="br-cn-{bi}-{ci}" class="ui-input" class:err={invalid} type="text" aria-describedby={describedby} aria-invalid={invalid} bind:value={c.name} onblur={() => (c.name = c.name.trim())} />{/snippet}
                </Field>
                <Field label={t('settings.br.psk')} for="br-ck-{bi}-{ci}" error={pskProblem(c.psk) ?? notes[k]}>
                  {#snippet children({ describedby, invalid })}
                    <input
                      id="br-ck-{bi}-{ci}"
                      class="ui-input ui-mono"
                      class:err={invalid}
                      type={k in revealed || visible[k] ? 'text' : 'password'}
                      autocomplete="off"
                      spellcheck="false"
                      aria-describedby={describedby}
                      aria-invalid={invalid}
                      value={revealed[k] ?? c.psk}
                      oninput={(e) => setPsk(b, bi, ci, e.currentTarget.value)}
                    />
                  {/snippet}
                </Field>
                <div class="acts">
                  <Button iconOnly icon="eye" label={t('settings.br.eyeAria')} onclick={() => toggleEye(b, bi, ci)} />
                  <Button icon="trash" onclick={() => removeChannel(b, ci)}>{t('settings.br.delete')}</Button>
                </div>
              </div>
            </li>
          {/each}
        </ul>

        <div class="row">
          <Field label={t('settings.br.newChannel')} for="br-nn-{bi}" error={draftOf(bi).name ? (draftNameError(b, bi) ?? undefined) : undefined}>
            {#snippet children({ describedby, invalid })}<input id="br-nn-{bi}" class="ui-input" class:err={invalid} type="text" placeholder={t('settings.br.namePh')} aria-describedby={describedby} aria-invalid={invalid} value={draftOf(bi).name} oninput={(e) => (drafts[bi] = { ...draftOf(bi), name: e.currentTarget.value })} />{/snippet}
          </Field>
          <Field label={t('settings.br.keyB64')} for="br-np-{bi}" error={draftOf(bi).psk ? (draftPskError(bi) ?? undefined) : undefined}>
            {#snippet children({ describedby, invalid })}<input id="br-np-{bi}" class="ui-input ui-mono" class:err={invalid} type="password" autocomplete="off" aria-describedby={describedby} aria-invalid={invalid} value={draftOf(bi).psk} oninput={(e) => (drafts[bi] = { ...draftOf(bi), psk: e.currentTarget.value })} />{/snippet}
          </Field>
          <div class="acts">
            <Button icon="plus" disabled={!!draftNameError(b, bi) || !!draftPskError(bi) || b.channels.length >= MAX_BROKER_CHANNELS} onclick={() => addChannel(b, bi)}>{t('settings.br.addChannel')}</Button>
          </div>
        </div>

        <div class="row imp">
          <Field label={t('settings.br.importRadio')} for="br-rad-{bi}">
            {#snippet children()}
              <Select id="br-rad-{bi}" value={radioSel[bi] ?? radios[0]?.id ?? ''} disabled={importOff(b) || radios.length === 0} onchange={(e) => (radioSel[bi] = e.currentTarget.value)}>
                {#if radios.length === 0}<option value="">{t('settings.br.noRadio')}</option>{/if}
                {#each radios as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
              </Select>
            {/snippet}
          </Field>
          <div class="acts"><Button disabled={importOff(b) || radios.length === 0 || busyImport[bi]} onclick={() => importRadio(bi, b)}>{t('settings.br.import')}</Button></div>
        </div>
        <div class="row imp">
          <Field label={t('settings.br.pasteLink')} for="br-link-{bi}" error={links[bi] && !isChannelLink(links[bi]) ? t('settings.br.linkErr') : undefined}>
            {#snippet children({ describedby, invalid })}<input id="br-link-{bi}" class="ui-input ui-mono" class:err={invalid} type="text" autocomplete="off" spellcheck="false" placeholder="https://meshtastic.org/e/#…" aria-describedby={describedby} aria-invalid={invalid} disabled={importOff(b)} value={links[bi] ?? ''} oninput={(e) => (links[bi] = e.currentTarget.value)} />{/snippet}
          </Field>
          <div class="acts"><Button disabled={importOff(b) || !isChannelLink(links[bi] ?? '') || busyImport[bi]} onclick={() => importLink(bi, b)}>{t('settings.br.importLink')}</Button></div>
        </div>
        {#if importOff(b)}<p class="ui-hint">{t('settings.br.saveFirst')}</p>{/if}
        {#if results[bi]}<p class="ui-hint" role="status">{results[bi]}</p>{/if}

        {#if b.id !== DEFAULT_BROKER_ID}
          <div><Button kind="danger" icon="trash" onclick={() => (toDelete = bi)}>{t('settings.br.deleteBroker')}</Button></div>
        {/if}
      </section>
    </Card>
  {/each}

  <div>
    <Button icon="plus" disabled={brokers.length >= MAX_BROKERS} onclick={addBroker}>{t('settings.br.addBroker')}</Button>
    {#if brokers.length >= MAX_BROKERS}<span class="ui-hint"> {t('settings.br.maxBrokers', { n: MAX_BROKERS })}</span>{/if}
  </div>
</div>

<Modal open={toDelete !== null} title={t('settings.br.deleteBroker')} danger confirmLabel={t('settings.br.delete')} onconfirm={removeBroker} oncancel={() => (toDelete = null)}>
  <p>{t('settings.br.delBody', { name: toDelete !== null ? (brokers[toDelete]?.name ?? '') : '' })}</p>
</Modal>

<style>
  .brokers { display: flex; flex-direction: column; gap: var(--space-3); }
  .sec { display: flex; flex-direction: column; gap: var(--space-3); }
  h4 { margin: 0; font: 600 14px/20px var(--font-sans); }
  p { margin: 0; }
  .head { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
  .nm { font: 600 15px/20px var(--font-sans); }
  .st { color: var(--ink-muted); font: 400 14px/20px var(--font-sans); overflow-wrap: anywhere; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--ink-muted); flex: none; }
  .dot.ok { background: var(--ok); }
  .dot.ko { background: var(--danger); }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-3); align-items: end; }
  .sw { display: flex; align-items: center; min-height: var(--control-h-desktop); }
  .area { height: auto; padding: var(--space-2) var(--space-3); resize: vertical; font-family: var(--font-mono); }
  .chans { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-3); }
  .row { display: grid; grid-template-columns: 1fr 1fr auto; gap: var(--space-3); align-items: start; }
  .row.imp { grid-template-columns: 1fr auto; }
  .acts { display: flex; gap: var(--space-2); align-items: center; min-height: var(--control-h-desktop); margin-top: 24px; }
  :global(.vp-phone) .sw, :global(.vp-phone) .acts { min-height: var(--control-h-phone); }
  :global(.vp-phone) .row, :global(.vp-phone) .row.imp { grid-template-columns: 1fr; }
  :global(.vp-phone) .acts { margin-top: 0; }
</style>
