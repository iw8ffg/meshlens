<script lang="ts">
  import Icon from '../ui/Icon.svelte'
  import { t, tn } from '../i18n/index.svelte'
  import { num } from '../format'
  import { PHONE_NAV, navActive, type Tab } from './nav'

  let { tab, alerts = 0, unread = 0, onselect }: { tab: Tab; alerts?: number; unread?: number; onselect: (t: Tab) => void } = $props()
  const active = $derived(navActive(tab))
</script>

<nav class="bn" aria-label={t('nav.sections')}>
  {#each PHONE_NAV as it (it.id)}
    <button type="button" class:on={active === it.id} aria-current={active === it.id ? 'page' : undefined} onclick={() => onselect(it.id)}>
      <span class="ic">
        <Icon name={it.icon} size={22} />
        {#if it.id === 'chat' && unread > 0}<b class="cnt" aria-label={tn('shell.unread', unread)}>{num(unread)}</b>{/if}
        {#if it.id === 'more' && alerts > 0}<b class="cnt" aria-label={tn('shell.alerts', alerts)}>{alerts}</b>{/if}
      </span>
      <span class="lb">{t(it.labelKey)}</span>
    </button>
  {/each}
</nav>

<style>
  .bn { display: flex; flex: none; height: calc(var(--bottomnav-h) + env(safe-area-inset-bottom)); padding-bottom: env(safe-area-inset-bottom); background: var(--surface); border-top: 1px solid var(--line-strong); z-index: var(--z-topbar); box-sizing: border-box; }
  button { flex: 1; min-width: 0; min-height: var(--touch-min); position: relative; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; background: none; border: 0; color: var(--ink-muted); font: 500 14px/16px var(--font-sans); cursor: pointer; }
  button.on { color: var(--accent); }
  /* la voce attiva ha anche una barretta in alto: il colore da solo non basta */
  button.on::before { content: ''; position: absolute; top: 0; left: 25%; right: 25%; height: 3px; border-radius: 0 0 3px 3px; background: var(--accent); }
  .ic { position: relative; display: inline-flex; }
  .cnt { position: absolute; top: -6px; left: 12px; min-width: 18px; height: 18px; padding: 0 4px; box-sizing: border-box; border-radius: var(--radius-pill); background: var(--warn); color: var(--bg); font: 700 12px/18px var(--font-sans); text-align: center; }
  .lb { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 100%; }
</style>
