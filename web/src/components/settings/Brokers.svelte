<script lang="ts">
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

  function tone(b: Broker): 'ok' | 'ko' | 'off' {
    if (!b.enabled || !b.id) return 'off'
    return statusOf(b)?.connected ? 'ok' : 'ko'
  }

  function statusText(b: Broker): string {
    const s = statusOf(b)
    if (!b.id) return 'Non ancora salvato'
    if (!b.enabled) return 'Disattivato'
    if (!s) return 'In attesa dello stato'
    if (s.connected) return `Connesso · ${num(s.msgs_per_s, 1)} msg/s`
    return s.last_error ? `Non connesso: ${s.last_error}` : 'Non connesso'
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
    b.channels[ci].psk = v
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
      notes[k] = 'Salva prima le modifiche'
      return
    }
    try {
      revealed[k] = (await revealChannelPsk(b.id, Number(m[1]))).psk
      delete notes[k]
    } catch (err) {
      notes[k] = err instanceof ApiError && err.status === 403 ? 'Visibile solo dal PC' : err instanceof ApiError ? err.message : 'Chiave non disponibile'
    }
  }

  function pskProblem(psk: string): string | null {
    return psk === '' ? 'Chiave mancante: reinseriscila' : pskError(psk)
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
    const added = r.added.length ? r.added.join(', ') : 'nessuno'
    const skipped = r.skipped.length ? r.skipped.map((s) => `${s.name} (${s.reason})`).join(', ') : 'nessuno'
    return `Aggiunti: ${added}; saltati: ${skipped}`
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
      results[bi] = err instanceof ApiError ? err.message : 'Importazione non riuscita'
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
          <strong class="nm">{b.name || 'Broker senza nome'}</strong>
          <span class="st">{statusText(b)}</span>
        </div>
        <div class="grid">
          <Field label="Nome" for="br-name-{bi}">{#snippet children()}<input id="br-name-{bi}" class="ui-input" type="text" maxlength="40" bind:value={b.name} />{/snippet}</Field>
          <div class="sw"><Switch bind:checked={b.enabled} label="Attivo" /></div>
          <Field label="Host" for="br-host-{bi}">{#snippet children()}<input id="br-host-{bi}" class="ui-input" type="text" autocomplete="off" bind:value={b.host} />{/snippet}</Field>
          <Field label="Porta" for="br-port-{bi}">{#snippet children()}<input id="br-port-{bi}" class="ui-input ui-mono" type="number" min="1" max="65535" bind:value={b.port} />{/snippet}</Field>
          <Field label="Utente" for="br-user-{bi}">{#snippet children()}<input id="br-user-{bi}" class="ui-input" type="text" autocomplete="off" bind:value={b.username} />{/snippet}</Field>
          <Field label="Password" for="br-pass-{bi}">{#snippet children()}<input id="br-pass-{bi}" class="ui-input" type="password" autocomplete="new-password" bind:value={b.password} />{/snippet}</Field>
        </div>
        <Switch bind:checked={b.tls} label="TLS" onchange={(v) => (b.port = portFor(v, b.port))} />
        <Switch bind:checked={b.encryption} label="Crittografia" />
        <p class="ui-hint">Spenta: i messaggi inviati escono in chiaro. Accesa: sono cifrati con la chiave del canale.</p>

        <Field label="Topic (uno per riga)" for="br-topics-{bi}" hint="Esempio: msh/EU_868/IT/# per il traffico italiano (se manca, /# viene aggiunto da solo). I messaggi inviati via MQTT usano la radice del primo topic.">
          {#snippet children()}<textarea id="br-topics-{bi}" class="ui-input area" rows="3" value={joinLines(b.topics)} onchange={(e) => setTopics(b, e.currentTarget.value)}></textarea>{/snippet}
        </Field>
        <Field label="Chiavi aggiuntive base64 (una per riga; ••••#n = chiave salvata, cancella la riga per rimuoverla)" for="br-keys-{bi}">
          {#snippet children()}<textarea id="br-keys-{bi}" class="ui-input area" rows="3" value={joinLines(b.extra_keys)} onchange={(e) => setKeys(b, e.currentTarget.value)}></textarea>{/snippet}
        </Field>

        <h4>Canali</h4>
        {#if b.channels.length === 0}<p class="ui-hint">Nessun canale personalizzato.</p>{/if}
        <ul class="chans">
          {#each b.channels as c, ci (ci)}
            {@const k = chanKey(bi, ci)}
            <li>
              <div class="row">
                <Field label="Nome canale" for="br-cn-{bi}-{ci}" error={nameProblem(b, ci) ?? undefined}>
                  {#snippet children({ describedby, invalid })}<input id="br-cn-{bi}-{ci}" class="ui-input" class:err={invalid} type="text" aria-describedby={describedby} aria-invalid={invalid} bind:value={c.name} />{/snippet}
                </Field>
                <Field label="Chiave (PSK)" for="br-ck-{bi}-{ci}" error={pskProblem(c.psk) ?? notes[k]}>
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
                  <Button iconOnly icon="eye" label="Mostra o nascondi la chiave" onclick={() => toggleEye(b, bi, ci)} />
                  <Button icon="trash" onclick={() => removeChannel(b, ci)}>Elimina</Button>
                </div>
              </div>
            </li>
          {/each}
        </ul>

        <div class="row">
          <Field label="Nuovo canale" for="br-nn-{bi}" error={draftOf(bi).name ? (draftNameError(b, bi) ?? undefined) : undefined}>
            {#snippet children({ describedby, invalid })}<input id="br-nn-{bi}" class="ui-input" class:err={invalid} type="text" placeholder="Nome (max 11 byte)" aria-describedby={describedby} aria-invalid={invalid} value={draftOf(bi).name} oninput={(e) => (drafts[bi] = { ...draftOf(bi), name: e.currentTarget.value })} />{/snippet}
          </Field>
          <Field label="Chiave (base64)" for="br-np-{bi}" error={draftOf(bi).psk ? (draftPskError(bi) ?? undefined) : undefined}>
            {#snippet children({ describedby, invalid })}<input id="br-np-{bi}" class="ui-input ui-mono" class:err={invalid} type="password" autocomplete="off" aria-describedby={describedby} aria-invalid={invalid} value={draftOf(bi).psk} oninput={(e) => (drafts[bi] = { ...draftOf(bi), psk: e.currentTarget.value })} />{/snippet}
          </Field>
          <div class="acts">
            <Button icon="plus" disabled={!!draftNameError(b, bi) || !!draftPskError(bi) || b.channels.length >= MAX_BROKER_CHANNELS} onclick={() => addChannel(b, bi)}>Aggiungi canale</Button>
          </div>
        </div>

        <div class="row imp">
          <Field label="Importa dalla radio" for="br-rad-{bi}">
            {#snippet children()}
              <Select id="br-rad-{bi}" value={radioSel[bi] ?? radios[0]?.id ?? ''} disabled={importOff(b) || radios.length === 0} onchange={(e) => (radioSel[bi] = e.currentTarget.value)}>
                {#if radios.length === 0}<option value="">Nessuna radio collegata</option>{/if}
                {#each radios as r (r.id)}<option value={r.id}>{r.name}</option>{/each}
              </Select>
            {/snippet}
          </Field>
          <div class="acts"><Button disabled={importOff(b) || radios.length === 0 || busyImport[bi]} onclick={() => importRadio(bi, b)}>Importa</Button></div>
        </div>
        <div class="row imp">
          <Field label="Incolla link" for="br-link-{bi}" error={links[bi] && !isChannelLink(links[bi]) ? 'Serve un link https://meshtastic.org/e/#…' : undefined}>
            {#snippet children({ describedby, invalid })}<input id="br-link-{bi}" class="ui-input ui-mono" class:err={invalid} type="text" autocomplete="off" spellcheck="false" placeholder="https://meshtastic.org/e/#…" aria-describedby={describedby} aria-invalid={invalid} disabled={importOff(b)} value={links[bi] ?? ''} oninput={(e) => (links[bi] = e.currentTarget.value)} />{/snippet}
          </Field>
          <div class="acts"><Button disabled={importOff(b) || !isChannelLink(links[bi] ?? '') || busyImport[bi]} onclick={() => importLink(bi, b)}>Importa link</Button></div>
        </div>
        {#if importOff(b)}<p class="ui-hint">Salva prima le modifiche</p>{/if}
        {#if results[bi]}<p class="ui-hint" role="status">{results[bi]}</p>{/if}

        {#if b.id !== DEFAULT_BROKER_ID}
          <div><Button kind="danger" icon="trash" onclick={() => (toDelete = bi)}>Elimina broker</Button></div>
        {/if}
      </section>
    </Card>
  {/each}

  <div>
    <Button icon="plus" disabled={brokers.length >= MAX_BROKERS} onclick={addBroker}>Aggiungi broker</Button>
    {#if brokers.length >= MAX_BROKERS}<span class="ui-hint"> Massimo {MAX_BROKERS} broker.</span>{/if}
  </div>
</div>

<Modal open={toDelete !== null} title="Elimina broker" danger confirmLabel="Elimina" onconfirm={removeBroker} oncancel={() => (toDelete = null)}>
  <p>Eliminare «{toDelete !== null ? brokers[toDelete]?.name : ''}» con i suoi canali e le sue chiavi? L'eliminazione vale dopo Salva.</p>
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
