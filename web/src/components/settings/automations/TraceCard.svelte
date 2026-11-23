<script lang="ts">
  // Traceroute periodici: interruttore globale (rotta dedicata), tetto orario, elenco dei nodi.
  import { ApiError, send } from '../../../lib/api'
  import { automation, setTargets } from '../../../lib/automation.svelte'
  import { t } from '../../../lib/i18n/index.svelte'
  import type { AppSettings } from '../../../lib/settings'
  import { app } from '../../../lib/stores.svelte'
  import {
    intervalLabel, listTargets, MAX_PER_HOUR_RANGE, removeTarget, setAutoTraceroutes, statusKey,
  } from '../../../lib/tracesched'
  import Banner from '../../../lib/ui/Banner.svelte'
  import Button from '../../../lib/ui/Button.svelte'
  import Card from '../../../lib/ui/Card.svelte'
  import Field from '../../../lib/ui/Field.svelte'
  import Switch from '../../../lib/ui/Switch.svelte'

  let { settings, onsaved }: { settings: AppSettings; onsaved: (s: AppSettings) => void } = $props()

  let busy = $state(false)
  let error = $state('')
  let maxPerHour = $state<number | null>(null)
  $effect(() => {
    maxPerHour = settings.traceroute_auto_max_per_hour ?? 6
  })
  const [lo, hi] = MAX_PER_HOUR_RANGE
  const maxValid = $derived(Number.isInteger(maxPerHour) && maxPerHour !== null && maxPerHour >= lo && maxPerHour <= hi)

  const errMsg = (e: unknown) => (e instanceof ApiError ? e.message : t('tracesched.card.saveFailed'))

  async function toggle(on: boolean) {
    busy = true
    error = ''
    try {
      const r = await setAutoTraceroutes(on)
      automation.autoEnabled = r.enabled
      setTargets(r.targets)
    } catch (e) {
      automation.autoEnabled = !on
      error = errMsg(e)
    } finally {
      busy = false
    }
  }

  async function saveMax() {
    if (!maxValid) return
    busy = true
    error = ''
    try {
      const s = await send<AppSettings>('PUT', '/settings', { traceroute_auto_max_per_hour: maxPerHour })
      automation.maxPerHour = s.traceroute_auto_max_per_hour ?? 6
      onsaved(s)
    } catch (e) {
      error = errMsg(e)
    } finally {
      busy = false
    }
  }

  async function remove(id: string) {
    error = ''
    try {
      await removeTarget(id)
      setTargets((await listTargets()).targets)
    } catch (e) {
      error = e instanceof ApiError ? e.message : t('tracesched.removeFailed')
    }
  }

  function nodeName(id: string): string {
    const n = app.nodes.get(id)
    return n?.long_name || n?.short_name || id
  }
</script>

<Card>
  <section class="sec">
    <h3>{t('tracesched.card.title')}</h3>
    <p class="muted">{t('tracesched.card.intro')}</p>
    <Switch bind:checked={automation.autoEnabled} disabled={busy} label={t('tracesched.card.switch')} onchange={(v) => void toggle(v)} />
    <div class="row">
      <Field label={t('tracesched.card.maxPerHour')} hint={t('tracesched.card.maxHint')} for="auto-tr-max">
        {#snippet children()}<input id="auto-tr-max" class="ui-input ui-mono" type="number" min={lo} max={hi} step="1" bind:value={maxPerHour} />{/snippet}
      </Field>
      <Button disabled={busy || !maxValid || maxPerHour === (settings.traceroute_auto_max_per_hour ?? 6)} onclick={saveMax}>{t('settings.save')}</Button>
    </div>
    <p class="muted">{t('tracesched.card.note')}</p>
    {#if automation.targets.length === 0}
      <p class="muted">{t('tracesched.card.empty')}</p>
    {:else}
      <ul class="targets">
        {#each automation.targets as tg (tg.node_id)}
          <li>
            <span class="name">{nodeName(tg.node_id)}</span>
            <span class="meta">{intervalLabel(tg.interval_min)} · {t(statusKey(tg.last_status))}</span>
            <Button kind="ghost" aria-label={t('tracesched.card.removeAria', { name: nodeName(tg.node_id) })} onclick={() => void remove(tg.node_id)}>{t('tracesched.card.remove')}</Button>
          </li>
        {/each}
      </ul>
    {/if}
    {#if error}<Banner kind="danger" title={error} />{/if}
  </section>
</Card>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  .row { display: flex; gap: var(--space-2); align-items: flex-end; flex-wrap: wrap; }
  .row :global(.ui-field) { flex: 1 1 220px; max-width: 320px; }
  .targets { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .targets li { display: flex; align-items: center; gap: var(--space-3); flex-wrap: wrap; font: 400 14px/20px var(--font-sans); }
  .name { font-weight: 600; }
  .meta { color: var(--ink-muted); flex: 1 1 auto; }
  .muted { margin: 0; color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
