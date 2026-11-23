<script lang="ts">
  // Webhook in uscita: indirizzo segreto (mascherato, mai rimandato), eventi, prova, attivazione
  // dalla rotta dedicata (PUT /settings puo' solo spegnerlo).
  import { onMount } from 'svelte'
  import { ApiError, send } from '../../../lib/api'
  import {
    enableWebhook, isLoopbackHost, testWebhook, WEBHOOK_EVENTS, webhookCodeLabel, webhookStatus, type WebhookStatus,
  } from '../../../lib/bot'
  import { formatDate } from '../../../lib/format'
  import { t, type MsgKey } from '../../../lib/i18n/index.svelte'
  import type { AppSettings, WebhookEvent } from '../../../lib/settings'
  import Banner from '../../../lib/ui/Banner.svelte'
  import Button from '../../../lib/ui/Button.svelte'
  import Card from '../../../lib/ui/Card.svelte'
  import Check from '../../../lib/ui/Check.svelte'
  import Switch from '../../../lib/ui/Switch.svelte'

  let { settings, onsaved, reload }: { settings: AppSettings; onsaved: (s: AppSettings) => void; reload: () => Promise<void> } = $props()

  let status = $state<WebhookStatus | null>(null)
  let on = $state(false)
  let urlInput = $state('')
  let replacing = $state(false)
  let events = $state<WebhookEvent[]>([])
  let busy = $state(false)
  let error = $state('')
  let ok = $state('')
  const local = typeof location !== 'undefined' && isLoopbackHost(location.hostname)
  const configured = $derived(!!settings.webhook_url)

  $effect(() => {
    on = settings.webhook_enabled === true
    events = [...(settings.webhook_events ?? ['alert'])]
  })

  async function loadStatus() {
    try {
      status = await webhookStatus()
    } catch {
      /* accessorio */
    }
  }
  onMount(() => void loadStatus())

  const errMsg = (e: unknown, fb: string) => (e instanceof ApiError ? e.message : fb)

  async function put(changes: Partial<AppSettings>, msg: string) {
    busy = true
    error = ok = ''
    try {
      onsaved(await send<AppSettings>('PUT', '/settings', changes))
      ok = msg
      await loadStatus()
    } catch (e) {
      error = errMsg(e, t('bot.webhook.saveFailed'))
    } finally {
      busy = false
    }
  }

  async function saveUrl() {
    const url = urlInput.trim()
    if (!url) return
    await put({ webhook_url: url }, t('bot.webhook.saved'))
    if (!error) {
      urlInput = ''
      replacing = false
    }
  }

  function setEvent(ev: WebhookEvent, v: boolean) {
    const next = v ? [...events.filter((x) => x !== ev), ev] : events.filter((x) => x !== ev)
    events = WEBHOOK_EVENTS.filter((x) => next.includes(x))
    void put({ webhook_events: events }, t('bot.webhook.saved'))
  }

  async function toggle(v: boolean) {
    busy = true
    error = ok = ''
    try {
      status = await enableWebhook(v)
      await reload()
    } catch (e) {
      on = !v
      error = errMsg(e, t('bot.webhook.saveFailed'))
    } finally {
      busy = false
    }
  }

  async function test() {
    busy = true
    error = ok = ''
    try {
      const r = await testWebhook()
      const msg = t('bot.webhook.testResult', { result: webhookCodeLabel(r.code) })
      if (r.ok) ok = msg
      else error = msg
      await loadStatus()
    } catch (e) {
      error = errMsg(e, t('bot.webhook.saveFailed'))
    } finally {
      busy = false
    }
  }
</script>

<Card>
  <section class="sec">
    <h3>{t('bot.webhook.title')}</h3>
    <p class="muted">{t('bot.webhook.intro')}</p>
    <Switch bind:checked={on} disabled={busy || (!on && (!configured || !local))} label={t('bot.webhook.switch')} onchange={(v) => void toggle(v)} />
    {#if !local && !on}<Banner kind="info" title={t('bot.webhook.localOnly')} />{/if}

    <div class="url">
      <span class="ui-lbl" id="wh-url-label">{t('bot.webhook.url')}</span>
      {#if configured && !replacing}
        <div class="row">
          <span class="muted">{t('bot.webhook.urlSet')}</span>
          <Button onclick={() => (replacing = true)}>{t('bot.webhook.replace')}</Button>
        </div>
      {:else}
        <div class="row">
          <input class="ui-input ui-mono grow" type="url" autocomplete="off" aria-labelledby="wh-url-label"
            placeholder={t('bot.webhook.urlHint')} maxlength="2048" bind:value={urlInput} />
          <Button kind="primary" disabled={busy || !urlInput.trim()} onclick={saveUrl}>{t('bot.webhook.saveUrl')}</Button>
          {#if replacing}<Button onclick={() => ((replacing = false), (urlInput = ''))}>{t('common.cancel')}</Button>{/if}
        </div>
        {#if !configured}<p class="muted">{t('bot.webhook.urlNone')}</p>{/if}
      {/if}
    </div>

    <h4>{t('bot.webhook.events')}</h4>
    <div class="grid">
      {#each WEBHOOK_EVENTS as ev (ev)}
        <Check bind:checked={() => events.includes(ev), (v) => setEvent(ev, v)} disabled={busy}
          label={t(`bot.webhook.ev.${ev}` as MsgKey)} />
      {/each}
    </div>

    <div class="row">
      <Button disabled={busy || !configured} onclick={test}>{t('bot.webhook.test')}</Button>
    </div>
    {#if status?.last}
      <p class="muted">{t('bot.webhook.last', { when: formatDate(status.last.time), result: webhookCodeLabel(status.last.code) })}</p>
    {/if}
    <p class="muted">{t('bot.webhook.note')}</p>
    {#if error}<Banner kind="danger" title={error} />{/if}
    {#if ok}<Banner kind="ok" title={ok} />{/if}
  </section>
</Card>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  h4 { margin: var(--space-2) 0 0; font: 600 14px/20px var(--font-sans); }
  p { margin: 0; }
  .url { display: flex; flex-direction: column; gap: var(--space-1); }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .grow { flex: 1 1 260px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: var(--space-2); }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
