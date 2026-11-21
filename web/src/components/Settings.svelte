<script lang="ts">
  import { onMount } from 'svelte'
  import { getJSON, send, ApiError } from '../lib/api'
  import { flag } from '../lib/format'
  import OfflineMaps from './OfflineMaps.svelte'
  import Updates from './Updates.svelte'
  import { channelOptions, joinLines, parseLines, type AppSettings, type MqttChannel } from '../lib/settings'

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
    keys = joinLines(s.mqtt.extra_keys)
    chosen = [...(s.mqtt_channels ?? [])]
    onlyChosen = chosen.length > 0
  }

  onMount(async () => {
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

{#if loadError}
  <p class="err">{loadError}</p>
{:else if !loaded}
  <p class="muted">Caricamento…</p>
{:else}
  <form onsubmit={save}>
    <fieldset>
      <legend>Nazioni da salvare nello storico</legend>
      <ul class="countries">
        {#each options as c (c.code)}
          <li>
            <label>
              <input type="checkbox" checked={saved.includes(c.code)} onchange={() => toggle(c.code)} />
              {flag(c.code)} {c.name}
            </label>
          </li>
        {/each}
      </ul>
    </fieldset>

    <fieldset>
      <legend>Conservazione</legend>
      <label>Messaggi (giorni) <input type="number" min="1" bind:value={retMsg} /></label>
      <label>Posizioni (giorni) <input type="number" min="1" bind:value={retPos} /></label>
      <label>Telemetria (giorni) <input type="number" min="1" bind:value={retTel} /></label>
      <label>Limite spazio (MB) <input type="number" min="1" bind:value={capMb} /></label>
    </fieldset>

    <fieldset>
      <legend>Avvisi (solo nodi miei)</legend>
      <label>Avviso batteria sotto (%) <input type="number" min="1" max="99" bind:value={batteryPct} /></label>
      <label>Avviso nodo silenzioso dopo (ore) <input type="number" min="1" max="168" bind:value={silentH} /></label>
    </fieldset>

    <fieldset>
      <legend>Rete</legend>
      <label class="inline"><input type="checkbox" bind:checked={lan} /> Accesso dalla rete locale</label>
      <p class="muted">Richiede il riavvio di MeshLens.</p>
    </fieldset>

    <fieldset>
      <legend>MQTT</legend>
      <label>Host <input type="text" bind:value={host} /></label>
      <label>Porta <input type="number" min="1" max="65535" bind:value={port} /></label>
      <label>Utente <input type="text" autocomplete="off" bind:value={username} /></label>
      <label>Password <input type="password" autocomplete="new-password" bind:value={password} /></label>
      <label>Topic (uno per riga) <textarea rows="3" bind:value={topics}></textarea></label>
      <label>Chiavi aggiuntive base64 (una per riga) <textarea rows="3" bind:value={keys}></textarea></label>
    </fieldset>

    <fieldset>
      <legend>Canali da ascoltare (MQTT)</legend>
      <label class="inline"><input type="radio" name="chmode" checked={!onlyChosen} onchange={() => (onlyChosen = false)} /> Tutti i canali</label>
      <label class="inline"><input type="radio" name="chmode" checked={onlyChosen} onchange={() => (onlyChosen = true)} /> Solo i canali scelti</label>
      <ul class="countries">
        {#each channels as c (c.name)}
          <li>
            <label>
              <input type="checkbox" disabled={!onlyChosen} checked={chosen.includes(c.name)} onchange={() => toggleChannel(c.name)} />
              {c.name} <span class="n">{c.count} nell'ultima ora</span>
            </label>
          </li>
        {/each}
      </ul>
      <p class="muted">LongFast è il canale pubblico predefinito; gli altri sono preset usati da meno nodi. I canali non scelti vengono ignorati del tutto (nodi, mappa, messaggi, archivio). La radio non è mai filtrata.</p>
    </fieldset>

    {#if error}<p class="err" role="alert">{error}</p>{/if}
    {#if ok}<p class="ok" role="status">{ok}</p>{/if}
    <button type="submit" class="primary" disabled={busy}>Salva</button>
  </form>
{/if}
{#if !loadError && loaded}<div class="maps"><OfflineMaps /></div>{/if}
{#if !loadError && loaded}<div class="maps"><Updates /></div>{/if}
<div class="out"><button onclick={logout}>Esci</button></div>

<style>
  form {
    display: flex;
    flex-direction: column;
    gap: 10px;
    padding: 8px;
  }
  fieldset {
    border: 1px solid #374151;
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }
  label {
    display: flex;
    flex-direction: column;
    gap: 2px;
    font-size: 13px;
  }
  label.inline {
    flex-direction: row;
    align-items: center;
    gap: 6px;
  }
  .countries {
    list-style: none;
    margin: 0;
    padding: 0;
    max-height: 180px;
    overflow: auto;
  }
  .countries label {
    flex-direction: row;
    align-items: center;
    gap: 6px;
  }
  input[type='text'],
  input[type='number'],
  input[type='password'],
  textarea {
    padding: 5px 8px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    font: inherit;
  }
  textarea {
    resize: vertical;
    font-family: ui-monospace, monospace;
    font-size: 12px;
  }
  button {
    padding: 6px 12px;
    background: #1f2937;
    color: inherit;
    border: 1px solid #374151;
    border-radius: 6px;
    cursor: pointer;
    font: inherit;
  }
  button.primary {
    background: #2563eb;
    border-color: #2563eb;
  }
  .n {
    margin-left: auto;
    color: #9ca3af;
    font-size: 13px;
  }
  .maps {
    padding: 0 8px 8px;
  }
  .out {
    padding: 8px;
  }
  .muted {
    color: #9ca3af;
    margin: 0;
    font-size: 12px;
    padding: 0 8px;
  }
  .err {
    color: #f87171;
    margin: 0;
  }
  .ok {
    color: #34d399;
    margin: 0;
  }
  @media (max-width: 767px) {
    .muted {
      font-size: 13px;
    }
    label.inline,
    .countries label {
      min-height: 40px;
    }
    input[type='text'],
    input[type='number'],
    input[type='password'] {
      min-height: 40px;
      box-sizing: border-box;
    }
    button {
      min-height: 40px;
    }
  }
</style>
