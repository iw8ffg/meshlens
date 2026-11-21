<script lang="ts">
  import { onMount } from 'svelte'
  import Icon from '../ui/Icon.svelte'
  import Segmented from '../ui/Segmented.svelte'
  import Logo from './Logo.svelte'
  import { app, updates } from '../stores.svelte'
  import { viewport } from '../viewport.svelte'
  import { getTheme, THEME_LABELS, type ThemePref } from '../theme'
  import { num } from '../format'
  import { DESKTOP_TABS, type Tab } from './nav'
  import type { Alert } from '../types'

  interface Props {
    visible: number
    tab: Tab
    onselect: (t: Tab) => void
    onupdate: () => void
    onpickalert: (nodeId: string) => void
  }
  let { visible, tab, onselect, onupdate, onpickalert }: Props = $props()

  const mqtt = $derived(app.status?.mqtt ?? null)
  const upd = $derived(updates.status?.available ? updates.status.latest : null)
  const radiosOn = $derived(app.radios.filter((r) => r.state === 'connected').length)

  let open = $state<'alerts' | 'menu' | null>(null)
  let root = $state<HTMLElement>()
  let pref = $state<ThemePref>('auto')
  const themeItems = (Object.keys(THEME_LABELS) as ThemePref[]).map((v) => ({ value: v, label: THEME_LABELS[v] }))

  onMount(() => {
    const ctl = getTheme()
    pref = ctl.pref()
    return ctl.subscribe((_t, p) => (pref = p))
  })

  function toggle(which: 'alerts' | 'menu') {
    open = open === which ? null : which
  }
  function outside(e: MouseEvent) {
    if (open && root && !root.contains(e.target as Node)) open = null
  }
  function esc(e: KeyboardEvent) {
    if (e.key === 'Escape' && open) open = null
  }
  function alertText(a: Alert): string {
    return a.kind === 'battery_low' ? `Batteria ${num(Math.round(a.value))}% — ${a.node_name}` : `Silenzioso da ${num(Math.round(a.value))} h — ${a.node_name}`
  }
</script>

<svelte:window onclick={outside} onkeydown={esc} />

<header class="tb" bind:this={root}>
  <div class="brand">
    <Logo size={viewport.phone ? 28 : 26} />
    {#if !viewport.phone}<span class="name">MeshLens</span>{/if}
  </div>

  {#if !viewport.phone}
    <nav class="tabs" aria-label="Sezioni">
      {#each DESKTOP_TABS as t (t.id)}
        <button type="button" class:on={tab === t.id} aria-current={tab === t.id ? 'page' : undefined} onclick={() => onselect(t.id)}>
          <Icon name={t.icon} size={16} />{t.label}
        </button>
      {/each}
    </nav>
  {/if}

  <div class="status">
    <span class="it" title={mqtt ? (mqtt.connected ? 'MQTT connesso' : 'MQTT non connesso') : 'MQTT: in attesa'}>
      <span class="dot" class:ok={mqtt?.connected} class:ko={mqtt && !mqtt.connected}></span>
      {#if viewport.phone}MQTT{:else}MQTT {mqtt ? (mqtt.connected ? 'connesso' : 'non connesso') : '…'}{/if}
    </span>
    {#if !viewport.phone}
      <span class="it ui-mono">{mqtt ? num(mqtt.msgs_per_s, 1) : '–'} msg/s</span>
    {/if}
    <span class="it"><Icon name="nodes" size={16} />{num(visible)}{#if !viewport.phone}&nbsp;nodi{/if}</span>
    <span class="it"><Icon name="radio" size={16} />{radiosOn}/{app.radios.length}{#if !viewport.phone}&nbsp;radio{/if}</span>
  </div>

  <div class="acts">
    {#if upd}
      <button type="button" class="upd" onclick={onupdate}>
        <Icon name="download" size={16} />{#if viewport.phone}Aggiorna{:else}Disponibile {upd}{/if}
      </button>
    {/if}
    {#if app.alerts.length > 0}
      <div class="pop-wrap">
        <button type="button" class="ib warn" aria-expanded={open === 'alerts'} aria-label="{app.alerts.length} {app.alerts.length === 1 ? 'avviso' : 'avvisi'}" onclick={() => toggle('alerts')}>
          <Icon name="alert" size={18} /><span class="n">{num(app.alerts.length)}</span>
        </button>
        {#if open === 'alerts'}
          <div class="pop alerts" role="dialog" aria-label="Avvisi">
            <ul>
              {#each app.alerts as a (a.key)}
                <li>
                  <button
                    type="button"
                    onclick={() => {
                      open = null
                      onpickalert(a.node_id)
                    }}>{alertText(a)}</button>
                </li>
              {/each}
            </ul>
          </div>
        {/if}
      </div>
    {/if}
    <div class="pop-wrap">
      <button type="button" class="ib" aria-expanded={open === 'menu'} aria-label="Menu e tema" onclick={() => toggle('menu')}>
        <Icon name="more" size={18} />
      </button>
      {#if open === 'menu'}
        <div class="pop menu" role="dialog" aria-label="Menu">
          <div class="lbl">Tema</div>
          <Segmented items={themeItems} bind:value={pref} fill label="Tema" onchange={(v) => getTheme().setPref(v)} />
        </div>
      {/if}
    </div>
  </div>
</header>

<style>
  .tb { position: relative; flex: none; display: flex; align-items: center; gap: var(--space-4); height: var(--topbar-h); padding: 0 var(--space-3); box-sizing: border-box; background: var(--surface); border-bottom: 1px solid var(--line-strong); color: var(--ink); z-index: var(--z-topbar); font: 400 14px/20px var(--font-sans); }
  .brand { display: flex; align-items: center; gap: var(--space-2); flex: none; }
  .name { font: 600 16px/24px var(--font-sans); }
  .tabs { display: flex; gap: 2px; min-width: 0; overflow-x: auto; scrollbar-width: none; }
  .tabs button { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 var(--space-3); border: 0; border-radius: var(--radius-md); background: none; color: var(--ink-muted); font: 500 14px/20px var(--font-sans); cursor: pointer; white-space: nowrap; }
  .tabs button:hover { color: var(--ink); background: var(--surface-sunken); }
  .tabs button.on { background: var(--accent-soft); color: var(--accent-ink); }
  .status { display: flex; align-items: center; gap: var(--space-4); margin-left: auto; min-width: 0; white-space: nowrap; }
  .it { display: inline-flex; align-items: center; gap: 6px; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: var(--ink-muted); flex: none; }
  .dot.ok { background: var(--ok); }
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
  .alerts ul { list-style: none; margin: 0; padding: 0; }
  .alerts li button { display: block; width: 100%; min-height: var(--touch-min); text-align: left; padding: var(--space-2) var(--space-3); background: none; border: 0; border-radius: var(--radius-md); color: var(--ink); font: 400 14px/20px var(--font-sans); cursor: pointer; }
  .alerts li button:hover { background: var(--accent-soft); }
  :global(.vp-phone) .tb { gap: var(--space-2); padding: env(safe-area-inset-top) var(--space-2) 0; height: calc(var(--topbar-h) + env(safe-area-inset-top)); }
  :global(.vp-phone) .status { gap: var(--space-3); overflow: hidden; }
  :global(.vp-phone) .upd { height: var(--touch-min); }
  :global(.vp-phone) .pop { position: fixed; top: calc(var(--topbar-h) + env(safe-area-inset-top)); right: 8px; }
</style>
