<script lang="ts">
  import { onMount } from 'svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Icon from '../lib/ui/Icon.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import Skeleton from '../lib/ui/Skeleton.svelte'
  import Switch from '../lib/ui/Switch.svelte'
  import MeshtasticBadge from '../lib/shell/MeshtasticBadge.svelte'
  import { getTheme, THEME_LABELS, type ThemePref } from '../lib/theme'
  import { getJSON, send, ApiError } from '../lib/api'
  import Flag from '../lib/ui/Flag.svelte'
  import OfflineMaps from './OfflineMaps.svelte'
  import Updates from './Updates.svelte'
  import Maintenance from './settings/Maintenance.svelte'
  import { channelOptions, checkMqttNodeId, joinLines, maskedKeyLines, parseLines, type AppSettings, type MqttChannel } from '../lib/settings'

  let { onlogout }: { onlogout: () => void } = $props()

  type Country = { code: string; name: string; nodes: number }
  const MASK = '••••'

  let countries = $state<Country[]>([])
  let saved = $state<string[]>([])
  let retMsg = $state(90)
  let retPos = $state(90)
  let retTel = $state(365)
  let capMb = $state(2048)
  let lan = $state(false)
  let batteryPct = $state(20)
  let silentH = $state(6)
  let host = $state('')
  let port = $state(1883)
  let username = $state('')
  let password = $state('')
  let topics = $state('')
  let keys = $state('')
  let onlyChosen = $state(false)
  let chosen = $state<string[]>([])
  let seenChannels = $state<MqttChannel[]>([])
  let nodeId = $state('')
  let version = $state('')
  let themePref = $state<ThemePref>('auto')
  const themeItems = (Object.keys(THEME_LABELS) as ThemePref[]).map((v) => ({ value: v, label: THEME_LABELS[v] }))
  const nodeIdCheck = $derived(checkMqttNodeId(nodeId))
  let loaded = $state(false)
  let loadError = $state('')
  let error = $state('')
  let ok = $state('')
  let busy = $state(false)

  function apply(s: AppSettings) {
    saved = [...s.saved_countries]
    retMsg = s.retention_messages_days
    retPos = s.retention_positions_days
    retTel = s.retention_telemetry_days
    capMb = s.storage_cap_mb
    lan = s.lan_access
    batteryPct = s.battery_alert_pct
    silentH = s.silent_alert_hours
    host = s.mqtt.host
    port = s.mqtt.port
    username = s.mqtt.username
    password = s.mqtt.password
    topics = joinLines(s.mqtt.topics)
    keys = joinLines(maskedKeyLines(s.mqtt.extra_keys))
    chosen = [...(s.mqtt_channels ?? [])]
    nodeId = s.mqtt_node_id ?? ''
    onlyChosen = chosen.length > 0
  }

  onMount(() => {
    const ctl = getTheme()
    themePref = ctl.pref()
    return ctl.subscribe((_t, p) => (themePref = p))
  })

  onMount(async () => {
    getJSON<{ version: string }>('/version')
      .then((v) => (version = v.version))
      .catch(() => {})
    try {
      apply(await getJSON<AppSettings>('/settings'))
      loaded = true
    } catch {
      loadError = 'Impostazioni non disponibili'
    }
    try {
      seenChannels = await getJSON<MqttChannel[]>('/mqtt/channels')
    } catch {
      /* restano i preset standard */
    }
    try {
      countries = (await getJSON<Country[]>('/countries'))
        .filter((c) => c.code !== 'none')
        .sort((a, b) => b.nodes - a.nodes)
    } catch {
      /* resta l'elenco delle nazioni gia' salvate */
    }
  })

  // Nazioni salvate non presenti nell'elenco restano selezionabili
  const options = $derived([
    ...countries,
    ...saved.filter((c) => !countries.some((x) => x.code === c)).map((c) => ({ code: c, name: c, nodes: 0 })),
  ])

  const channels = $derived(channelOptions(seenChannels, chosen))

  function toggleChannel(name: string) {
    chosen = chosen.includes(name) ? chosen.filter((x) => x !== name) : [...chosen, name]
  }

  function toggle(code: string) {
    saved = saved.includes(code) ? saved.filter((x) => x !== code) : [...saved, code]
  }

  async function save(e: Event) {
    e.preventDefault()
    error = ok = ''
    if (!nodeIdCheck.ok) return
    busy = true
    try {
      const res = await send<AppSettings>('PUT', '/settings', {
        saved_countries: saved,
        retention_messages_days: retMsg,
        retention_positions_days: retPos,
        retention_telemetry_days: retTel,
        storage_cap_mb: capMb,
        lan_access: lan,
        mqtt_channels: onlyChosen ? chosen : [],
        mqtt_node_id: nodeIdCheck.value,
        battery_alert_pct: batteryPct,
        silent_alert_hours: silentH,
        mqtt: {
          host,
          port,
          username,
          password: password === '' ? MASK : password,
          topics: parseLines(topics),
          extra_keys: parseLines(keys),
        },
      })
      if (res && typeof res === 'object' && 'mqtt' in res) apply(res)
      ok = 'Impostazioni salvate'
    } catch (err) {
      error = err instanceof ApiError ? err.message : 'Salvataggio non riuscito'
    } finally {
      busy = false
    }
  }

  async function logout() {
    try {
      await send('POST', '/auth/logout')
    } catch {
      /* si torna comunque al login */
    }
    onlogout()
  }
</script>

<div class="settings">
  <h2>Impostazioni</h2>

  <Card>
    <section class="sec">
      <h3>Aspetto</h3>
      <div class="fld">
        <span class="ui-lbl">Tema</span>
        <Segmented items={themeItems} bind:value={themePref} label="Tema" onchange={(v) => getTheme().setPref(v)} />
        <span class="ui-hint">Auto segue il tema del dispositivo.</span>
      </div>
    </section>
  </Card>

  {#if loadError}
    <Banner kind="danger" title={loadError} />
  {:else if !loaded}
    <Skeleton tall />
    <Skeleton tall />
  {:else}
    <form onsubmit={save}>
      <Card>
        <section class="sec">
          <h3>Nazioni da salvare nello storico</h3>
          <ul class="countries">
            {#each options as c (c.code)}
              <li>
                <label class="ui-check">
                  <input type="checkbox" checked={saved.includes(c.code)} onchange={() => toggle(c.code)} />
                  <span class="bx">{#if saved.includes(c.code)}<Icon name="check" size={14} />{/if}</span>
                  <span class="cn"><Flag code={c.code} name={c.name} /> {c.name}</span>
                </label>
              </li>
            {/each}
          </ul>
        </section>
      </Card>

      <Card>
        <section class="sec">
          <h3>Conservazione</h3>
          <div class="grid">
            <Field label="Messaggi (giorni)" for="set-ret-msg">{#snippet children()}<input id="set-ret-msg" class="ui-input ui-mono" type="number" min="1" bind:value={retMsg} />{/snippet}</Field>
            <Field label="Posizioni (giorni)" for="set-ret-pos">{#snippet children()}<input id="set-ret-pos" class="ui-input ui-mono" type="number" min="1" bind:value={retPos} />{/snippet}</Field>
            <Field label="Telemetria (giorni)" for="set-ret-tel">{#snippet children()}<input id="set-ret-tel" class="ui-input ui-mono" type="number" min="1" bind:value={retTel} />{/snippet}</Field>
            <Field label="Limite spazio (MB)" for="set-cap">{#snippet children()}<input id="set-cap" class="ui-input ui-mono" type="number" min="1" bind:value={capMb} />{/snippet}</Field>
          </div>
        </section>
      </Card>

      <Maintenance />

      <Card>
        <section class="sec">
          <h3>Avvisi (solo nodi miei)</h3>
          <div class="grid">
            <Field label="Avviso batteria sotto (%)" for="set-batt">{#snippet children()}<input id="set-batt" class="ui-input ui-mono" type="number" min="1" max="99" bind:value={batteryPct} />{/snippet}</Field>
            <Field label="Avviso nodo silenzioso dopo (ore)" for="set-silent">{#snippet children()}<input id="set-silent" class="ui-input ui-mono" type="number" min="1" max="168" bind:value={silentH} />{/snippet}</Field>
          </div>
        </section>
      </Card>

      <Card>
        <section class="sec">
          <h3>Rete</h3>
          <Switch bind:checked={lan} label="Accesso dalla rete locale" />
          <p class="ui-hint">Richiede il riavvio di MeshLens.</p>
        </section>
      </Card>

      <Card>
        <section class="sec">
          <h3>MQTT</h3>
          <div class="grid">
            <Field label="Host" for="set-host">{#snippet children()}<input id="set-host" class="ui-input" type="text" bind:value={host} />{/snippet}</Field>
            <Field label="Porta" for="set-port">{#snippet children()}<input id="set-port" class="ui-input ui-mono" type="number" min="1" max="65535" bind:value={port} />{/snippet}</Field>
            <Field label="Utente" for="set-user">{#snippet children()}<input id="set-user" class="ui-input" type="text" autocomplete="off" bind:value={username} />{/snippet}</Field>
            <Field label="Password" for="set-pass">{#snippet children()}<input id="set-pass" class="ui-input" type="password" autocomplete="new-password" bind:value={password} />{/snippet}</Field>
          </div>
          <Field label="Topic (uno per riga)" for="set-topics" hint="Esempio: msh/EU_868/IT/# per il traffico italiano (se manca, /# viene aggiunto da solo). I messaggi inviati via MQTT usano la radice del primo topic, per esempio msh/EU_868/IT, così arrivano ai gateway che la ascoltano.">{#snippet children()}<textarea id="set-topics" class="ui-input area" rows="3" bind:value={topics}></textarea>{/snippet}</Field>
          <Field label="Chiavi aggiuntive base64 (una per riga; ••••#n = chiave salvata, cancella la riga per rimuoverla)" for="set-keys">{#snippet children()}<textarea id="set-keys" class="ui-input area" rows="3" bind:value={keys}></textarea>{/snippet}</Field>
          <Field
            label="Il tuo id nodo per MQTT"
            for="set-nodeid"
            error={nodeIdCheck.ok ? undefined : nodeIdCheck.error}
            hint="È l'id con cui scrivi nella rete MQTT pubblica. Se lo lasci vuoto si usa quello della radio collegata."
          >
            {#snippet children({ describedby, invalid })}
              <input id="set-nodeid" class="ui-input ui-mono" class:err={invalid} type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder="!a1b2c3d4" aria-describedby={describedby} aria-invalid={invalid} bind:value={nodeId} />
            {/snippet}
          </Field>
        </section>
      </Card>

      <Card>
        <section class="sec">
          <h3>Canali da ascoltare (MQTT)</h3>
          <Segmented
            label="Canali da ascoltare"
            items={[
              { value: 'all', label: 'Tutti i canali' },
              { value: 'chosen', label: 'Solo i canali scelti' },
            ]}
            value={onlyChosen ? 'chosen' : 'all'}
            onchange={(v) => (onlyChosen = v === 'chosen')}
          />
          <ul class="countries">
            {#each channels as c (c.name)}
              <li>
                <label class="ui-check chan">
                  <input type="checkbox" disabled={!onlyChosen} checked={chosen.includes(c.name)} onchange={() => toggleChannel(c.name)} />
                  <span class="bx">{#if chosen.includes(c.name)}<Icon name="check" size={14} />{/if}</span>
                  <span>{c.name}</span>
                  <span class="n ui-mono">{c.count} nell'ultima ora</span>
                </label>
              </li>
            {/each}
          </ul>
          <p class="ui-hint">LongFast è il canale pubblico predefinito; gli altri sono preset usati da meno nodi. I canali non scelti vengono ignorati del tutto (nodi, mappa, messaggi, archivio). La radio non è mai filtrata.</p>
        </section>
      </Card>

      {#if error}<Banner kind="danger" title={error} />{/if}
      {#if ok}<Banner kind="ok" title={ok} />{/if}
      <div><Button type="submit" kind="primary" disabled={busy || !nodeIdCheck.ok}>Salva</Button></div>
    </form>

    <OfflineMaps />
    <Updates />
  {/if}

  <Card>
    <section class="sec">
      <h3>Informazioni</h3>
      <p class="line">MeshLens <b class="ui-mono">{version || '—'}</b></p>
      <p class="ui-hint">
        Software libero con licenza GNU GPL v3 (file LICENSE). Le componenti di terze parti (font IBM Plex con licenza OFL, icone Lucide con licenza ISC, bandiere flag-icons con licenza MIT, Protomaps e le librerie Python) sono elencate con le rispettive licenze nel file THIRD_PARTY_NOTICES.
      </p>
      <p class="ui-hint">Dati delle mappe © OpenStreetMap contributors, disponibili con licenza ODbL (Open Database License).</p>
      <MeshtasticBadge />
    </section>
  </Card>

  <div class="out"><Button icon="power" onclick={logout}>Esci</Button></div>
</div>

<style>
  .settings { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); max-width: 760px; margin: 0 auto; box-sizing: border-box; color: var(--ink); }
  h2 { margin: 0; font: 600 18px/24px var(--font-sans); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  form { display: flex; flex-direction: column; gap: var(--space-3); }
  .sec { display: flex; flex-direction: column; gap: var(--space-3); }
  .fld { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-3); }
  .cn { display: inline-flex; align-items: center; gap: var(--space-2); }
  .countries { list-style: none; margin: 0; padding: 0; max-height: 240px; overflow: auto; }
  .chan { width: 100%; }
  .n { margin-left: auto; color: var(--ink-muted); font-size: 13px; }
  .area { height: auto; padding: var(--space-2) var(--space-3); resize: vertical; font-family: var(--font-mono); }
  .line { margin: 0; font: 400 14px/20px var(--font-sans); }
  p { margin: 0; }
  .out { padding-bottom: var(--space-4); }
  :global(.vp-phone) .n { font-size: 14px; }
</style>
