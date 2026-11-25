<script lang="ts">
  import { onMount, tick } from 'svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Card from '../lib/ui/Card.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Icon from '../lib/ui/Icon.svelte'
  import Segmented from '../lib/ui/Segmented.svelte'
  import Select from '../lib/ui/Select.svelte'
  import Skeleton from '../lib/ui/Skeleton.svelte'
  import Switch from '../lib/ui/Switch.svelte'
  import MeshtasticBadge from '../lib/shell/MeshtasticBadge.svelte'
  import { getTheme, type ThemePref } from '../lib/theme'
  import { getJSON, getCountries, send, ApiError } from '../lib/api'
  import Flag from '../lib/ui/Flag.svelte'
  import OfflineMaps from './OfflineMaps.svelte'
  import Updates from './Updates.svelte'
  import MqttStatusDetail from '../lib/shell/MqttStatusDetail.svelte'
  import { app } from '../lib/stores.svelte'
  import Maintenance from './settings/Maintenance.svelte'
  import Diagnostics from './settings/Diagnostics.svelte'
  import Devices from './settings/Devices.svelte'
  import Brokers from './settings/Brokers.svelte'
  import Notifications from './settings/Notifications.svelte'
  import QuickReplies from './settings/QuickReplies.svelte'
  import AlertRules from './settings/AlertRules.svelte'
  import Automations from './settings/Automations.svelte'
  import IgnoredNodes from './settings/IgnoredNodes.svelte'
  import GuestAccess from './settings/GuestAccess.svelte'
  import { channelOptions, checkMqttNodeId, filterChannels, httpsNote, type AppSettings, type Broker, type MqttChannel, type TlsInfo } from '../lib/settings'
  import { channelNameError, fromServer, pskError } from '../lib/brokers'
  import { formatDate, countryName } from '../lib/format'
  import { i18n, setLang, t, LANGS, LANG_LABELS, type Lang, type MsgKey } from '../lib/i18n/index.svelte'
  import { translateServer } from '../lib/i18n/server'
  import { JUMP_EVENT, pickActive, sectionDomId, takeSettingsJump, visibleSections } from '../lib/settingsnav'

  let { onlogout }: { onlogout: () => void } = $props()

  type Country = { code: string; name: string; nodes: number }

  let countries = $state<Country[]>([])
  let saved = $state<string[]>([])
  let retMsg = $state(90)
  let retPos = $state(90)
  let retTel = $state(365)
  let capMb = $state(2048)
  let retPackets = $state(48)
  let packetMode = $state<'off' | 'archived' | 'all'>('archived')
  let lan = $state(false)
  let lanHttps = $state(false)
  let tls = $state<TlsInfo | null>(null)
  let batteryPct = $state(20)
  let silentH = $state(6)
  let brokers = $state<Broker[]>([])
  let brokersSnap = $state('[]')
  let onlyChosen = $state(false)
  let chosen = $state<string[]>([])
  let seenChannels = $state<MqttChannel[]>([])
  let nodeId = $state('')
  let version = $state('')
  let themePref = $state<ThemePref>('auto')
  const THEME_KEYS: Record<ThemePref, MsgKey> = { auto: 'shell.themeAuto', dark: 'shell.themeDark', light: 'shell.themeLight' }
  const themeItems = $derived((Object.keys(THEME_KEYS) as ThemePref[]).map((v) => ({ value: v, label: t(THEME_KEYS[v]) })))
  const langItems = LANGS.map((l: Lang) => ({ value: l, label: LANG_LABELS[l] }))
  const nodeIdCheck = $derived(checkMqttNodeId(nodeId))
  const dirty = $derived(JSON.stringify(brokers) !== brokersSnap)
  const brokersOk = $derived(
    brokers.every((b) =>
      b.channels.every(
        (c, i) => c.psk !== '' && !pskError(c.psk) && !channelNameError(c.name, b.channels.filter((_, j) => j !== i).map((x) => x.name.trim())),
      ),
    ),
  )
  let loaded = $state(false)
  let loadFailed = $state(false)
  let error = $state('')
  let ok = $state('')
  let busy = $state(false)

  // Dopo un'importazione si aggiornano solo i broker: le altre modifiche non salvate restano.
  function applyBrokers(s: AppSettings) {
    brokers = fromServer(s.mqtt_brokers ?? [])
    brokersSnap = JSON.stringify(brokers)
  }

  function apply(s: AppSettings) {
    saved = [...s.saved_countries]
    retMsg = s.retention_messages_days
    retPos = s.retention_positions_days
    retTel = s.retention_telemetry_days
    capMb = s.storage_cap_mb
    retPackets = s.retention_packets_hours ?? 48
    packetMode = s.packet_log_mode ?? 'archived'
    lan = s.lan_access
    lanHttps = s.lan_https ?? false
    batteryPct = s.battery_alert_pct
    silentH = s.silent_alert_hours
    applyBrokers(s)
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
      loadFailed = true
    }
    getJSON<TlsInfo>('/tls')
      .then((t) => (tls = t))
      .catch(() => {})
    try {
      seenChannels = await getJSON<MqttChannel[]>('/mqtt/channels')
    } catch {
      /* restano i preset standard */
    }
    try {
      countries = (await getCountries())
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
  let chanQuery = $state('')
  const shownChannels = $derived(filterChannels(channels, chanQuery))

  function toggleChannel(name: string) {
    chosen = chosen.includes(name) ? chosen.filter((x) => x !== name) : [...chosen, name]
  }

  function toggle(code: string) {
    saved = saved.includes(code) ? saved.filter((x) => x !== code) : [...saved, code]
  }

  async function save(e: Event) {
    e.preventDefault()
    error = ok = ''
    if (!nodeIdCheck.ok || !brokersOk) return
    busy = true
    try {
      const res = await send<AppSettings>('PUT', '/settings', {
        saved_countries: saved,
        retention_messages_days: retMsg,
        retention_positions_days: retPos,
        retention_telemetry_days: retTel,
        storage_cap_mb: capMb,
        retention_packets_hours: retPackets,
        packet_log_mode: packetMode,
        lan_access: lan,
        lan_https: lanHttps,
        mqtt_channels: onlyChosen ? chosen : [],
        mqtt_node_id: nodeIdCheck.value,
        battery_alert_pct: batteryPct,
        silent_alert_hours: silentH,
        mqtt_brokers: brokers,
      })
      if (res && typeof res === 'object' && 'mqtt_brokers' in res) apply(res)
      ok = t('settings.saved')
    } catch (err) {
      error = err instanceof ApiError ? err.message : t('settings.saveFailed')
    } finally {
      busy = false
    }
  }

  // Navigazione rapida: chip in alto, sezione in vista evidenziata, salto con messa a fuoco del titolo.
  const sections = $derived(visibleSections(loaded))
  let active = $state('appearance')
  let root: HTMLDivElement | undefined = $state()
  let navEl: HTMLElement | undefined = $state()

  /** Porta in vista il chip attivo scorrendo solo la barra (mai la pagina). */
  function showChip(id: string) {
    const chip = navEl?.querySelector<HTMLElement>(`[data-sec="${id}"]`)
    if (!navEl || !chip || navEl.scrollWidth <= navEl.clientWidth) return
    const left = chip.getBoundingClientRect().left - navEl.getBoundingClientRect().left + navEl.scrollLeft
    navEl.scrollLeft = left - (navEl.clientWidth - chip.offsetWidth) / 2
  }

  function sectionEl(id: string) {
    return document.getElementById(sectionDomId(id))
  }

  // durante un salto la sezione scelta resta evidenziata finche' lo scorrimento non si ferma
  let lockUntil = 0

  function updateActive() {
    if (performance.now() < lockUntil) return
    // linea di lettura: sotto la barra dei salti se e' visibile (telefono), altrimenti sotto la barra in alto
    const line = Math.max(navEl?.getBoundingClientRect().bottom ?? 0, 60) + 24
    const tops = sections.flatMap((s) => {
      const el = sectionEl(s.id)
      return el ? [{ id: s.id, top: el.getBoundingClientRect().top }] : []
    })
    const id = pickActive(tops, line)
    if (id && id !== active) {
      active = id
      showChip(id)
    }
  }

  async function jump(id: string) {
    await tick()
    const el = sectionEl(id)
    if (!el) return
    const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    active = id
    showChip(id)
    lockUntil = Number.POSITIVE_INFINITY // fino al prossimo scorrimento fatto dall'utente
    el.scrollIntoView({ behavior: calm ? 'auto' : 'smooth', block: 'start' })
    const h = el.querySelector<HTMLElement>('h3')
    if (h) {
      h.tabIndex = -1
      h.focus({ preventScroll: true })
    }
  }

  onMount(() => {
    const onJump = () => {
      const id = takeSettingsJump()
      if (id) void jump(id)
    }
    window.addEventListener(JUMP_EVENT, onJump)
    return () => window.removeEventListener(JUMP_EVENT, onJump)
  })

  $effect(() => {
    if (!root) return
    const els = sections.map((s) => sectionEl(s.id)).filter((e): e is HTMLElement => !!e)
    const io = new IntersectionObserver(updateActive, { rootMargin: '-64px 0px -55% 0px', threshold: [0, 1] })
    for (const e of els) io.observe(e)
    // anche alla fine di ogni scorrimento (l'observer scatta solo alle soglie)
    let raf = 0
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(updateActive)
    }
    window.addEventListener('scroll', onScroll, { passive: true, capture: true })
    // un gesto dell'utente sblocca l'evidenziazione scelta con un salto
    const unlock = () => { lockUntil = 0 }
    for (const ev of ['wheel', 'touchmove', 'keydown', 'pointerdown'] as const) window.addEventListener(ev, unlock, { passive: true, capture: true })
    updateActive()
    return () => {
      io.disconnect()
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScroll, { capture: true })
      for (const ev of ['wheel', 'touchmove', 'keydown', 'pointerdown'] as const) window.removeEventListener(ev, unlock, { capture: true })
    }
  })

  // Salto richiesto dalla ricerca globale mentre la scheda non c'era ancora
  $effect(() => {
    if (!loaded && !loadFailed) return
    const id = takeSettingsJump()
    if (id) void jump(id)
  })

  async function logout() {
    try {
      await send('POST', '/auth/logout')
    } catch {
      /* si torna comunque al login */
    }
    onlogout()
  }
</script>

<div class="settings" bind:this={root}>
  <h2>{t('settings.title')}</h2>

  <nav class="jump" aria-label={t('settings.nav.aria')} bind:this={navEl}>
    {#each sections as s (s.id)}
      <button type="button" class="chip" data-sec={s.id} class:on={active === s.id} aria-current={active === s.id ? 'true' : undefined} onclick={() => jump(s.id)}>{t(s.labelKey)}</button>
    {/each}
  </nav>

  <div class="anch" id="set-appearance">
    <Card>
      <section class="sec">
        <h3>{t('settings.appearance')}</h3>
        <div class="fld">
          <span class="ui-lbl">{t('shell.theme')}</span>
          <Segmented items={themeItems} bind:value={themePref} label={t('shell.theme')} onchange={(v) => getTheme().setPref(v)} />
          <span class="ui-hint">{t('settings.themeHint')}</span>
        </div>
        <div class="fld">
          <span class="ui-lbl">{t('shell.language')}</span>
          <Segmented items={langItems} value={i18n.lang} label={t('shell.language')} onchange={(l) => setLang(l)} />
        </div>
      </section>
    </Card>
  </div>

  {#if loadFailed}
    <Banner kind="danger" title={t('settings.loadFailed')} />
  {:else if !loaded}
    <Skeleton tall />
    <Skeleton tall />
  {:else}
    <form onsubmit={save}>
      <div class="anch" id="set-countries">
        <Card>
          <section class="sec">
            <h3>{t('settings.countries')}</h3>
            <ul class="countries">
              {#each options as c (c.code)}
                <li>
                  <label class="ui-check">
                    <input type="checkbox" checked={saved.includes(c.code)} onchange={() => toggle(c.code)} />
                    <span class="bx">{#if saved.includes(c.code)}<Icon name="check" size={14} />{/if}</span>
                    <span class="cn"><Flag code={c.code} name={countryName(c.code, c.name)} /> {countryName(c.code, c.name)}</span>
                  </label>
                </li>
              {/each}
            </ul>
          </section>
        </Card>
      </div>

      <div class="anch" id="set-retention">
        <Card>
          <section class="sec">
            <h3>{t('settings.retention')}</h3>
            <div class="grid">
              <Field label={t('settings.ret.messages')} for="set-ret-msg">{#snippet children()}<input id="set-ret-msg" class="ui-input ui-mono" type="number" min="1" bind:value={retMsg} />{/snippet}</Field>
              <Field label={t('settings.ret.positions')} for="set-ret-pos">{#snippet children()}<input id="set-ret-pos" class="ui-input ui-mono" type="number" min="1" bind:value={retPos} />{/snippet}</Field>
              <Field label={t('settings.ret.telemetry')} for="set-ret-tel">{#snippet children()}<input id="set-ret-tel" class="ui-input ui-mono" type="number" min="1" bind:value={retTel} />{/snippet}</Field>
              <Field label={t('settings.ret.cap')} for="set-cap">{#snippet children()}<input id="set-cap" class="ui-input ui-mono" type="number" min="1" bind:value={capMb} />{/snippet}</Field>
              <Field label={t('settings.ret.packets')} for="set-ret-pkt">{#snippet children()}<input id="set-ret-pkt" class="ui-input ui-mono" type="number" min="1" max="168" bind:value={retPackets} />{/snippet}</Field>
              <Field label={t('settings.ret.inspector')} for="set-pkt-mode">{#snippet children()}
                <Select id="set-pkt-mode" bind:value={packetMode}>
                  <option value="off">{t('settings.ret.off')}</option>
                  <option value="archived">{t('settings.ret.archived')}</option>
                  <option value="all">{t('settings.ret.all')}</option>
                </Select>
              {/snippet}</Field>
            </div>
            <p class="ui-hint">{t('settings.ret.hint')}</p>
          </section>
        </Card>
      </div>

      <div class="anch" id="set-db"><Maintenance /></div>

      <div class="anch" id="set-alerts">
        <Card>
          <section class="sec">
            <h3>{t('settings.alerts.title')}</h3>
            <div class="grid">
              <Field label={t('settings.alerts.battery')} for="set-batt">{#snippet children()}<input id="set-batt" class="ui-input ui-mono" type="number" min="1" max="99" bind:value={batteryPct} />{/snippet}</Field>
              <Field label={t('settings.alerts.silent')} for="set-silent">{#snippet children()}<input id="set-silent" class="ui-input ui-mono" type="number" min="1" max="168" bind:value={silentH} />{/snippet}</Field>
            </div>
          </section>
        </Card>
      </div>

      <div class="anch" id="set-notify"><Notifications /></div>
      <div class="anch" id="set-quick"><QuickReplies /></div>
      <div class="anch" id="set-alertrules"><AlertRules /></div>
      <div class="anch" id="set-automations"><Automations /></div>

      <div class="anch" id="set-net">
        <Card>
          <section class="sec">
            <h3>{t('settings.net.title')}</h3>
            <Switch bind:checked={lan} label={t('settings.net.lan')} />
            <p class="ui-hint">{t('settings.net.restart')}</p>
            <Switch bind:checked={lanHttps} disabled={!lan} label={t('settings.net.https')} />
            {#if lan && lanHttps}<p class="ui-hint">{httpsNote(tls?.port)}</p>{/if}
            {#if tls?.fingerprint_sha256}
              <div class="fld">
                <span class="ui-lbl">{t('settings.net.fp')}</span>
                <code class="ui-mono fp">{tls.fingerprint_sha256}</code>
                <span class="ui-hint">{t('settings.net.expires', { date: formatDate(tls.not_after) })}</span>
              </div>
            {/if}
            {#if tls?.error}<Banner kind="danger" title={translateServer(tls.error)} />{/if}
          </section>
        </Card>
      </div>

      <div class="anch" id="set-dev"><Devices /></div>
      <div class="anch" id="set-guest"><GuestAccess /></div>
      <div class="anch" id="set-ignored"><IgnoredNodes /></div>

      <div class="anch" id="set-mqtt">
        <Card>
          <section class="sec">
            <h3>{t('settings.mqtt.title')}</h3>
            <MqttStatusDetail status={app.status?.mqtt ?? null} />
            <Brokers bind:brokers {dirty} onimported={applyBrokers} />
            <Field
              label={t('settings.mqtt.nodeId')}
              for="set-nodeid"
              error={nodeIdCheck.ok ? undefined : nodeIdCheck.error}
              hint={t('settings.mqtt.nodeIdHint')}
            >
              {#snippet children({ describedby, invalid })}
                <input id="set-nodeid" class="ui-input ui-mono" class:err={invalid} type="text" autocomplete="off" autocapitalize="off" spellcheck="false" placeholder={t('settings.mqtt.nodeIdPh')} aria-describedby={describedby} aria-invalid={invalid} bind:value={nodeId} />
              {/snippet}
            </Field>
          </section>
        </Card>
      </div>

      <div class="anch" id="set-chan">
        <Card>
          <section class="sec">
            <h3>{t('settings.chan.title')}</h3>
            <Segmented
              label={t('settings.chan.aria')}
              items={[
                { value: 'all', label: t('settings.chan.all') },
                { value: 'chosen', label: t('settings.chan.chosen') },
              ]}
              value={onlyChosen ? 'chosen' : 'all'}
              onchange={(v) => (onlyChosen = v === 'chosen')}
            />
            {#if channels.length > 6}
              <input class="ui-input chan-search" type="search" aria-label={t('settings.chan.searchAria')} placeholder={t('settings.chan.searchPh')} bind:value={chanQuery} />
            {/if}
            <ul class="countries">
              {#each shownChannels as c (c.name)}
                <li>
                  <label class="ui-check chan">
                    <input type="checkbox" disabled={!onlyChosen} checked={chosen.includes(c.name)} onchange={() => toggleChannel(c.name)} />
                    <span class="bx">{#if chosen.includes(c.name)}<Icon name="check" size={14} />{/if}</span>
                    <span>{c.name}</span>
                    <span class="n ui-mono">{t('settings.chan.count', { n: c.count })}</span>
                  </label>
                </li>
              {:else}
                <li class="ui-hint">{t('settings.chan.none')}</li>
              {/each}
            </ul>
            {#if chosen.length}<p class="ui-hint">{t('settings.chan.selected', { n: chosen.length })}</p>{/if}
            <p class="ui-hint">{t('settings.chan.hint')}</p>
          </section>
        </Card>
      </div>

      {#if error}<Banner kind="danger" title={error} />{/if}
      {#if ok}<Banner kind="ok" title={ok} />{/if}
      <div><Button type="submit" kind="primary" disabled={busy || !nodeIdCheck.ok || !brokersOk}>{t('settings.save')}</Button></div>
    </form>

    <div class="anch" id="set-maps"><OfflineMaps /></div>
    <div class="anch" id="set-updates"><Updates /></div>
  {/if}

  <div class="anch" id="set-diag"><Diagnostics /></div>

  <div class="anch" id="set-about">
    <Card>
      <section class="sec">
        <h3>{t('settings.about.title')}</h3>
        <p class="line">MeshLens <b class="ui-mono">{version || '—'}</b></p>
        <p class="ui-hint">{t('settings.about.license')}</p>
        <p class="ui-hint">{t('settings.about.map')}</p>
        <MeshtasticBadge />
      </section>
    </Card>
  </div>

  <div class="out"><Button icon="power" onclick={logout}>{t('settings.logout')}</Button></div>
</div>

<style>
  .settings { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); max-width: 760px; margin: 0 auto; box-sizing: border-box; color: var(--ink); }
  h2 { margin: 0; font: 600 18px/24px var(--font-sans); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  h3:focus { outline: none; }
  h3:focus-visible { outline: 2px solid var(--focus-ring); outline-offset: 2px; border-radius: 4px; }
  .anch { display: flex; flex-direction: column; gap: var(--space-3); scroll-margin-top: 64px; }
  .jump { display: flex; flex-wrap: wrap; gap: 6px; margin: 0 calc(-1 * var(--space-4)); padding: var(--space-2) var(--space-4); background: var(--surface); border-bottom: 1px solid var(--line); }
  .chip { flex: none; min-height: 32px; padding: 0 12px; border: 1px solid var(--line-strong); border-radius: var(--radius-pill); background: var(--surface); color: var(--ink); font: 500 13px/1 var(--font-sans); cursor: pointer; white-space: nowrap; }
  .chip:hover { background: var(--accent-soft); }
  .chip.on { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
  :global(.vp-phone) .chip { min-height: 40px; font-size: 14px; }
  /* sul telefono una riga sola che scorre, per non coprire mezza pagina */
  :global(.vp-phone) .jump { position: sticky; top: 0; z-index: 2; flex-wrap: nowrap; overflow-x: auto; scrollbar-width: thin; }
  /* il titolo della sezione raggiunta non finisce sotto la barra fissa (telefono) */
  :global(.vp-phone) [id^='set-'] { scroll-margin-top: 64px; }
  form { display: flex; flex-direction: column; gap: var(--space-3); }
  .sec { display: flex; flex-direction: column; gap: var(--space-3); }
  .fld { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
  .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: var(--space-3); }
  .cn { display: inline-flex; align-items: center; gap: var(--space-2); }
  .countries { list-style: none; margin: 0; padding: 0; max-height: 240px; overflow: auto; }
  .chan { width: 100%; }
  .chan-search { max-width: 320px; }
  .n { margin-left: auto; color: var(--ink-muted); font-size: 13px; }
  .fp { font-size: 14px; line-height: 20px; overflow-wrap: anywhere; word-break: break-all; }
  .line { margin: 0; font: 400 14px/20px var(--font-sans); }
  p { margin: 0; }
  .out { padding-bottom: var(--space-4); }
  :global(.vp-phone) .n { font-size: 14px; }
</style>
