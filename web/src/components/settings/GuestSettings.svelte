<script lang="ts">
  // Impostazioni dell'ospite (E19): solo tema, lingua e uscita. Nessuna chiamata al server
  // tranne il logout (le impostazioni vere sono negate all'ospite).
  import { onMount } from 'svelte'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Segmented from '../../lib/ui/Segmented.svelte'
  import MeshtasticBadge from '../../lib/shell/MeshtasticBadge.svelte'
  import { getTheme, type ThemePref } from '../../lib/theme'
  import { send } from '../../lib/api'
  import { i18n, setLang, t, LANGS, LANG_LABELS, type Lang, type MsgKey } from '../../lib/i18n/index.svelte'

  let { onlogout }: { onlogout: () => void } = $props()

  let themePref = $state<ThemePref>('auto')
  const THEME_KEYS: Record<ThemePref, MsgKey> = { auto: 'shell.themeAuto', dark: 'shell.themeDark', light: 'shell.themeLight' }
  const themeItems = $derived((Object.keys(THEME_KEYS) as ThemePref[]).map((v) => ({ value: v, label: t(THEME_KEYS[v]) })))
  const langItems = LANGS.map((l: Lang) => ({ value: l, label: LANG_LABELS[l] }))

  onMount(() => {
    const ctl = getTheme()
    themePref = ctl.pref()
    return ctl.subscribe((_t, p) => (themePref = p))
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

<div class="settings">
  <h2>{t('settings.title')}</h2>
  <Banner kind="info" title={t('guest.settings.title')}>{t('guest.settings.intro')}</Banner>

  <Card>
    <section class="sec">
      <h3>{t('guest.settings.appearance')}</h3>
      <div class="fld">
        <span class="ui-lbl">{t('shell.theme')}</span>
        <Segmented items={themeItems} bind:value={themePref} label={t('shell.theme')} onchange={(v) => getTheme().setPref(v)} />
      </div>
      <div class="fld">
        <span class="ui-lbl">{t('shell.language')}</span>
        <Segmented items={langItems} value={i18n.lang} label={t('shell.language')} onchange={(l) => setLang(l)} />
      </div>
    </section>
  </Card>

  <MeshtasticBadge />
  <div class="out"><Button icon="power" onclick={logout}>{t('settings.logout')}</Button></div>
</div>

<style>
  .settings { display: flex; flex-direction: column; gap: var(--space-3); padding: var(--space-4); max-width: 760px; margin: 0 auto; box-sizing: border-box; color: var(--ink); }
  h2 { margin: 0; font: 600 18px/24px var(--font-sans); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  .sec { display: flex; flex-direction: column; gap: var(--space-3); }
  .fld { display: flex; flex-direction: column; gap: 6px; align-items: flex-start; }
  .out { padding-bottom: var(--space-4); }
</style>
