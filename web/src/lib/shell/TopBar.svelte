<script lang="ts">
  import { onMount } from 'svelte'
  import Icon from '../ui/Icon.svelte'
  import Segmented from '../ui/Segmented.svelte'
  import Logo from './Logo.svelte'
  import MqttStatusDetail from './MqttStatusDetail.svelte'
  import { mqttSummary } from '../mqttstatus'
  import { app, updates } from '../stores.svelte'
  import { unread, totalUnread } from '../unread.svelte'
  import { t, tn, type MsgKey } from '../i18n/index.svelte'
  import { viewport } from '../viewport.svelte'
  import { getTheme, type ThemePref } from '../theme'
  import { num } from '../format'
  import { DESKTOP_TABS, type Tab } from './nav'
  import AlertsList from './AlertsList.svelte'
  import { alertTone } from '../alerts'
  import { openGlobalSearch } from '../globalsearch.svelte'
  import { tabsFor } from '../guest'
  import { session } from '../guest.svelte'

  interface Props {
    visible: number
    now: number
    tab: Tab
    onselect: (t: Tab) => void
    onupdate: () => void
    onpickalert: (nodeId: string) => void
  }
  let { visible, now, tab, onselect, onupdate, onpickalert }: Props = $props()

  const mqtt = $derived(app.status?.mqtt ?? null)
  const mqttSum = $derived(mqttSummary(mqtt, Date.now() / 1000))
  const upd = $derived(updates.status?.available ? updates.status.latest : null)
  const hasWarnAlert = $derived(app.alerts.some((a) => alertTone(a.kind) === 'warn'))
  const unreadTotal = $derived(totalUnread(unread.counts))
  const radiosOn = $derived(app.radios.filter((r) => r.state === 'connected').length)
  // ospite (E19): niente ricerca (anche messaggi), radio, aggiornamenti, impostazioni MQTT
  const guest = $derived(session.role === 'guest')

  let open = $state<'alerts' | 'menu' | 'mqtt' | null>(null)
  let root = $state<HTMLElement>()
  let pref = $state<ThemePref>('auto')
  const THEME_KEYS: Record<ThemePref, MsgKey> = { auto: 'shell.themeAuto', dark: 'shell.themeDark', light: 'shell.themeLight' }
  const themeItems = $derived((Object.keys(THEME_KEYS) as ThemePref[]).map((v) => ({ value: v, label: t(THEME_KEYS[v]) })))

  onMount(() => {
    const ctl = getTheme()
    pref = ctl.pref()
    return ctl.subscribe((_t, p) => (pref = p))
  })

  function toggle(which: 'alerts' | 'menu' | 'mqtt') {
    open = open === which ? null : which
  }
  function outside(e: MouseEvent) {
    if (open && root && !root.contains(e.target as Node)) open = null
  }
  function esc(e: KeyboardEvent) {
    if (e.key === 'Escape' && open) open = null
  }
</script>

<svelte:window onclick={outside} onkeydown={esc} />

<header class="tb" bind:this={root}>
  <div class="brand">
    <Logo size={viewport.phone ? 28 : 26} />
    {#if !viewport.phone}<span class="name">MeshLens</span>{/if}
    {#if guest}<span class="guest" title={t('guest.badge')}><Icon name="eye" size={14} />{viewport.phone ? t('guest.badgeShort') : t('guest.badge')}</span>{/if}
  </div>

  {#if !viewport.phone}
    <nav class="tabs" aria-label={t('nav.sections')}>
      {#each tabsFor(DESKTOP_TABS, session.role) as d (d.id)}
        <button type="button" class:on={tab === d.id} aria-current={tab === d.id ? 'page' : undefined} onclick={() => onselect(d.id)}>
          <Icon name={d.icon} size={16} />{t(d.labelKey)}{#if d.id === 'chat' && unreadTotal > 0}<span class="bdg" aria-label={tn('shell.unread', unreadTotal)}>{num(unreadTotal)}</span>{/if}
        </button>
      {/each}
    </nav>
  {/if}

  <div class="status">
    <div class="pop-wrap">
      <button type="button" class="it mq" aria-haspopup="dialog" aria-expanded={open === 'mqtt'} title={mqttSum.title} onclick={() => toggle('mqtt')}>
        <span class="dot" class:ok={mqttSum.tone === 'ok'} class:warn={mqttSum.tone === 'warn'} class:ko={mqttSum.tone === 'ko'}></span>
        {#if viewport.phone}MQTT{:else}MQTT {mqtt ? (mqtt.connected ? t('shell.mqttConnectedShort') : t('shell.mqttDownShort')) : '…'}{/if}
      </button>
      {#if open === 'mqtt'}
        <div class="pop mqtt" role="dialog" aria-label={t('shell.mqttStatus')}>
          <MqttStatusDetail
            status={mqtt}
            onsettings={guest
              ? undefined
              : () => {
                  open = null
                  onselect('settings')
                }} />
        </div>
      {/if}
    </div>
    {#if !viewport.phone}
      <span class="it ui-mono">{mqtt ? num(mqtt.msgs_per_s, 1) : '–'} msg/s</span>
    {/if}
    <span class="it"><Icon name="nodes" size={16} />{num(visible)}{#if !viewport.phone}&nbsp;{t('shell.nodesWord')}{/if}</span>
    {#if !guest}
      <span class="it"><Icon name="radio" size={16} />{radiosOn}/{app.radios.length}{#if !viewport.phone}&nbsp;{t('shell.radiosWord')}{/if}</span>
    {/if}
  </div>

  <div class="acts">
    {#if !guest}
      <button type="button" class="ib" aria-label={t('search.open')} title={t('search.open')} onclick={openGlobalSearch}><Icon name="search" size={18} /></button>
    {/if}
    {#if upd && !guest}
      <button type="button" class="upd" onclick={onupdate}>
        <Icon name="download" size={16} />{#if viewport.phone}{t('shell.updateShort')}{:else}{t('shell.updateAvailable', { version: upd })}{/if}
      </button>
    {/if}
    {#if app.alerts.length > 0}
      <div class="pop-wrap">
        <button type="button" class:warn={hasWarnAlert} class="ib" aria-haspopup="dialog" aria-expanded={open === 'alerts'} aria-label={tn('shell.alerts', app.alerts.length)} onclick={() => toggle('alerts')}>
          <Icon name="alert" size={18} /><span class="n">{num(app.alerts.length)}</span>
        </button>
        {#if open === 'alerts'}
          <div class="pop alerts" role="dialog" aria-label={t('shell.alertsTitle')}>
            <AlertsList
              alerts={app.alerts}
              {now}
              onpick={(id) => {
                open = null
                onpickalert(id)
              }} />
          </div>
        {/if}
      </div>
    {/if}
    <div class="pop-wrap">
      <button type="button" class="ib" aria-haspopup="dialog" aria-expanded={open === 'menu'} aria-label={t('shell.menuAria')} onclick={() => toggle('menu')}>
        <Icon name="more" size={18} />
      </button>
      {#if open === 'menu'}
        <div class="pop menu" role="dialog" aria-label={t('shell.menu')}>
          <div class="lbl">{t('shell.theme')}</div>
          <Segmented items={themeItems} bind:value={pref} fill label={t('shell.theme')} onchange={(v) => getTheme().setPref(v)} />
        </div>
      {/if}
    </div>
  </div>
</header>

<style>
  .tb { position: relative; flex: none; display: flex; align-items: center; gap: var(--space-4); height: var(--topbar-h); padding: 0 var(--space-3); box-sizing: border-box; background: var(--surface); border-bottom: 1px solid var(--line-strong); color: var(--ink); z-index: var(--z-topbar); font: 400 14px/20px var(--font-sans); }
  .brand { display: flex; align-items: center; gap: var(--space-2); flex: none; }
  .name { font: 600 16px/24px var(--font-sans); }
  .guest { display: inline-flex; align-items: center; gap: 4px; height: 24px; padding: 0 var(--space-2); border-radius: var(--radius-pill); background: var(--accent-soft); color: var(--accent-ink); font: 600 13px/16px var(--font-sans); white-space: nowrap; }
  .tabs { display: flex; gap: 2px; min-width: 0; overflow-x: auto; scrollbar-width: none; }
  .tabs button { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 var(--space-3); border: 0; border-radius: var(--radius-md); background: none; color: var(--ink-muted); font: 500 14px/20px var(--font-sans); cursor: pointer; white-space: nowrap; }
  .tabs button:hover { color: var(--ink); background: var(--surface-sunken); }
  .bdg { min-width: 18px; height: 18px; padding: 0 5px; box-sizing: border-box; border-radius: var(--radius-pill); background: var(--warn); color: var(--bg); font: 700 14px/18px var(--font-sans); text-align: center; }
  .tabs button.on { background: var(--accent-soft); color: var(--accent-ink); }
  .status { display: flex; align-items: center; gap: var(--space-4); margin-left: auto; min-width: 0; white-space: nowrap; }
  .it { display: inline-flex; align-items: center; gap: 6px; }
  .mq { min-height: 32px; padding: 0 var(--space-2); border: 0; border-radius: var(--radius-md); background: none; color: inherit; font: inherit; cursor: pointer; }
  .mq:hover { background: var(--surface-sunken); }
  .pop.mqtt { right: auto; left: 0; white-space: normal; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--ink-muted); flex: none; }
  .dot.ok { background: var(--ok); }
  .dot.warn { background: var(--warn); }
  .dot.ko { background: var(--danger); }
  .acts { display: flex; align-items: center; gap: var(--space-2); flex: none; }
  .ib { display: inline-flex; align-items: center; justify-content: center; gap: 4px; min-width: var(--touch-min); height: var(--touch-min); padding: 0 var(--space-2); border: 0; border-radius: var(--radius-md); background: none; color: var(--ink); cursor: pointer; font: 600 14px/20px var(--font-sans); }
  .ib:hover { background: var(--surface-sunken); }
  .ib.warn { color: var(--warn); }
  .upd { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 var(--space-3); border: 0; border-radius: var(--radius-pill); background: var(--accent); color: var(--on-accent); font: 600 14px/20px var(--font-sans); cursor: pointer; white-space: nowrap; }
  .upd:hover { background: var(--accent-hover); }
  .pop-wrap { position: relative; }
  .pop { position: absolute; top: calc(100% + 4px); right: 0; width: 300px; max-width: calc(100vw - 16px); max-height: 60dvh; overflow: auto; background: var(--surface-raised); border: 1px solid var(--line-strong); border-radius: var(--radius-lg); box-shadow: var(--shadow-2); z-index: var(--z-modal); padding: var(--space-3); box-sizing: border-box; }
  .pop .lbl { font: 600 13px/16px var(--font-sans); color: var(--ink-muted); margin-bottom: var(--space-2); }
  .alerts { padding: var(--space-1); }
  :global(.vp-phone) .tb { gap: var(--space-2); padding: env(safe-area-inset-top) var(--space-2) 0; height: calc(var(--topbar-h) + env(safe-area-inset-top)); }
  :global(.vp-phone) .status { gap: var(--space-3); overflow: hidden; }
  :global(.vp-phone) .upd { height: var(--touch-min); }
  :global(.vp-phone) .pop { position: fixed; top: calc(var(--topbar-h) + env(safe-area-inset-top)); right: 8px; }
  :global(.vp-phone) .pop.mqtt { left: 8px; right: 8px; width: auto; }
  :global(.vp-phone) .mq { min-height: var(--touch-min); }
</style>
