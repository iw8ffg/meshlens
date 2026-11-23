<script lang="ts">
  // Primo avvio guidato (WP1, E1): checklist dopo il PIN, ripetibile da Ctrl+K. Compare da sola solo
  // con `onboarding_done === false` esplicito; «Chiudi» non scrive nulla, «Non mostrare più» sì.
  import { onMount, untrack } from 'svelte'
  import { getJSON, mapsState } from '../lib/api'
  import { t } from '../lib/i18n/index.svelte'
  import type { MsgKey } from '../lib/i18n/index.svelte'
  import { visibleNodes } from '../lib/filters'
  import { onboardingSteps, shouldAutoOpen } from '../lib/onboarding'
  import type { StepId } from '../lib/onboarding'
  import { closeOnboarding, finishOnboarding, onboardingUi, openOnboarding } from '../lib/onboarding.svelte'
  import type { AppSettings } from '../lib/settings'
  import { navigate } from '../lib/shell/navigate'
  import type { Tab } from '../lib/shell/nav'
  import { app } from '../lib/stores.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Banner from '../lib/ui/Banner.svelte'
  import Icon from '../lib/ui/Icon.svelte'

  let brokers = $state<{ enabled: boolean }[]>([])
  let mapCount = $state<number | null>(null)

  const steps = $derived(
    onboardingSteps({
      brokers,
      radios: app.radios,
      nodes: visibleNodes(app.nodes.values()),
      mapCount,
    }),
  )
  const allDone = $derived(steps.every((s) => s.done))
  const uid = $props.id()

  async function loadState(): Promise<AppSettings | null> {
    let settings: AppSettings | null = null
    try {
      settings = await getJSON<AppSettings>('/settings')
      brokers = (settings.mqtt_brokers ?? []).map((b) => ({ enabled: b.enabled }))
    } catch {
      /* resta lo stato precedente */
    }
    try {
      mapCount = (await mapsState()).maps.length
    } catch {
      mapCount = null
    }
    return settings
  }

  onMount(async () => {
    const settings = await loadState()
    // un errore di rete (settings nullo) non apre nulla
    if (settings && shouldAutoOpen(settings.onboarding_done, onboardingUi.closedThisSession)) openOnboarding()
  })

  // a ogni apertura (anche da Ctrl+K) lo stato dei passi si rilegge
  $effect(() => {
    if (onboardingUi.open) untrack(() => void loadState())
  })

  function go(tab: Tab) {
    closeOnboarding()
    navigate(tab)
  }

  const STEP_ACTIONS: Record<StepId, { key: MsgKey; tab: Tab }[]> = {
    source: [
      { key: 'onboarding.goRadio', tab: 'radio' },
      { key: 'onboarding.goMqtt', tab: 'settings' },
    ],
    nodes: [{ key: 'onboarding.goNodes', tab: 'nodes' }],
    maps: [{ key: 'onboarding.goMaps', tab: 'settings' }],
  }
  const TITLE: Record<StepId, MsgKey> = { source: 'onboarding.step.source.title', nodes: 'onboarding.step.nodes.title', maps: 'onboarding.step.maps.title' }
  const BODY: Record<StepId, MsgKey> = { source: 'onboarding.step.source.body', nodes: 'onboarding.step.nodes.body', maps: 'onboarding.step.maps.body' }

  const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

  /** Focus nella finestra, trappola di Tab, Esc chiude, il focus torna a chi lo aveva. */
  function dialog(node: HTMLElement) {
    const prev = document.activeElement as HTMLElement | null
    ;(node.querySelector<HTMLElement>('[data-autofocus]') ?? node).focus()
    const onkey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.preventDefault()
        e.stopPropagation()
        closeOnboarding()
        return
      }
      if (e.key !== 'Tab') return
      const items = [...node.querySelectorAll<HTMLElement>(FOCUSABLE)]
      if (!items.length) {
        e.preventDefault()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      const active = document.activeElement
      if (e.shiftKey && (active === first || active === node)) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && active === last) {
        e.preventDefault()
        first.focus()
      }
    }
    node.addEventListener('keydown', onkey)
    return {
      destroy() {
        node.removeEventListener('keydown', onkey)
        prev?.focus?.()
      },
    }
  }
</script>

{#if onboardingUi.open}
  <div class="ui-modalbg" role="presentation" onpointerdown={(e) => { if (e.target === e.currentTarget) closeOnboarding() }}>
    <div class="ui-modal ob" role="dialog" aria-modal="true" aria-labelledby="{uid}-t" tabindex="-1" use:dialog>
      <h2 id="{uid}-t">{t('onboarding.title')}</h2>
      <p class="intro">{t('onboarding.intro')}</p>
      <ol class="steps">
        {#each steps as s (s.id)}
          <li class:done={s.done}>
            <div class="hd">
              <span class="mark" aria-hidden="true"><Icon name={s.done ? 'check' : 'clock'} size={18} /></span>
              <h3>{t(TITLE[s.id])}</h3>
              <span class="state">{s.done ? t('onboarding.done') : t('onboarding.todo')}</span>
            </div>
            <p>{t(BODY[s.id])}</p>
            <div class="acts">
              {#each STEP_ACTIONS[s.id] as a (a.key)}
                <Button onclick={() => go(a.tab)}>{t(a.key)}</Button>
              {/each}
            </div>
          </li>
        {/each}
      </ol>
      {#if allDone}<Banner kind="ok" title={t('onboarding.allDone')} />{/if}
      {#if onboardingUi.error}<Banner kind="danger" title={t('onboarding.saveError')}>{onboardingUi.error}</Banner>{/if}
      <div class="acts end">
        <Button data-autofocus onclick={closeOnboarding}>{t('onboarding.close')}</Button>
        {#if allDone}
          <Button kind="primary" disabled={onboardingUi.saving} onclick={finishOnboarding}>{t('onboarding.finish')}</Button>
        {:else}
          <Button disabled={onboardingUi.saving} onclick={finishOnboarding}>{t('onboarding.dismiss')}</Button>
        {/if}
      </div>
    </div>
  </div>
{/if}

<style>
  .ob { max-width: 600px; }
  .intro { margin: 0; color: var(--ink-muted); }
  .steps { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-3); }
  .steps li { border: 1px solid var(--line); border-radius: var(--radius-lg); padding: var(--space-3) var(--space-4); display: flex; flex-direction: column; gap: var(--space-2); }
  .steps li.done { border-color: var(--ok); }
  .hd { display: flex; align-items: center; gap: var(--space-2); }
  .hd h3 { margin: 0; font: 600 15px/22px var(--font-sans); flex: 1; min-width: 0; }
  .mark { display: inline-flex; color: var(--ink-muted); }
  .done .mark { color: var(--ok); }
  .state { font-size: 14px; color: var(--ink-muted); }
  .steps p { margin: 0; font-size: 14px; color: var(--ink-muted); }
  .acts { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .acts.end { justify-content: flex-end; }
</style>
