<script lang="ts">
  // Bot: canali, comandi, risposte personalizzate, limiti (PUT /settings, chiavi non segrete) e
  // attivazione opt-in con modale di conferma (POST /api/bot/enable, solo da questo PC).
  import { onMount, untrack } from 'svelte'
  import { ApiError, mqttChannels, send } from '../../../lib/api'
  import { automation } from '../../../lib/automation.svelte'
  import {
    BOT_COMMANDS, canEnable, confirmedBrokers, enableBot, errorKey, isLoopbackHost, LIMITS, MAX_BOT_REPLIES,
    MAX_BOT_TARGETS, pausedLabel, previewBot, sameTarget, targetKey, targetLabel, toggleTarget, validateLimit,
    validateReplyText, validateTrigger, validChannelName, type BotPreview,
  } from '../../../lib/bot'
  import { visibleNodes } from '../../../lib/filters'
  import { t, type MsgKey } from '../../../lib/i18n/index.svelte'
  import type { AppSettings, BotCommand, BotReply, BotTarget } from '../../../lib/settings'
  import { app } from '../../../lib/stores.svelte'
  import Badge from '../../../lib/ui/Badge.svelte'
  import Banner from '../../../lib/ui/Banner.svelte'
  import Button from '../../../lib/ui/Button.svelte'
  import Card from '../../../lib/ui/Card.svelte'
  import Check from '../../../lib/ui/Check.svelte'
  import Field from '../../../lib/ui/Field.svelte'
  import Modal from '../../../lib/ui/Modal.svelte'
  import Select from '../../../lib/ui/Select.svelte'

  let { settings, onsaved, reload }: { settings: AppSettings; onsaved: (s: AppSettings) => void; reload: () => Promise<void> } = $props()

  type Form = {
    targets: BotTarget[]
    commands: BotCommand[]
    weather: string
    replies: BotReply[]
    minInterval: number | null
    maxPerHour: number | null
    cooldown: number | null
  }
  const fromSettings = (s: AppSettings): Form => ({
    targets: [...(s.bot_targets ?? [])],
    commands: [...(s.bot_commands ?? ['ping', 'info', 'time'])],
    weather: s.bot_weather_node ?? '',
    replies: (s.bot_replies ?? []).map((r) => ({ ...r })),
    minInterval: s.bot_min_interval_s ?? 30,
    maxPerHour: s.bot_max_per_hour ?? 20,
    cooldown: s.bot_node_cooldown_s ?? 300,
  })
  let form = $state<Form>(untrack(() => fromSettings(settings)))
  let saved = $state(untrack(() => JSON.stringify(fromSettings(settings))))
  // impostazioni del bot cambiate (salvate qui o altrove): il modulo riparte da quelle;
  // un salvataggio di altre chiavi (es. webhook) non cancella le modifiche in corso
  $effect(() => {
    const f = fromSettings(settings)
    const js = JSON.stringify(f)
    if (js === untrack(() => saved)) return
    saved = js
    form = f
  })
  const dirty = $derived(JSON.stringify(form) !== saved)

  let busy = $state(false)
  let error = $state('')
  let ok = $state('')
  let confirming = $state(false)
  let previewText = $state('')
  let preview = $state<BotPreview | null>(null)
  let mqttNames = $state<Record<string, string[]>>({})
  const local = typeof location !== 'undefined' && isLoopbackHost(location.hostname)
  let now = $state(Date.now() / 1000)

  onMount(() => {
    const timer = setInterval(() => (now = Date.now() / 1000), 15_000)
    for (const b of settings.mqtt_brokers ?? []) {
      if (!b.id || !b.enabled) continue
      const id = b.id
      mqttChannels(id)
        .then((list) => {
          const names = new Set([...b.channels.map((c) => c.name), ...list.filter((c) => c.enabled || c.custom || c.count_1h > 0).map((c) => c.name)])
          mqttNames = { ...mqttNames, [id]: [...names].filter(validChannelName).sort() }
        })
        .catch(() => (mqttNames = { ...mqttNames, [id]: b.channels.map((c) => c.name).filter(validChannelName) }))
    }
    return () => clearInterval(timer)
  })

  const brokers = $derived((settings.mqtt_brokers ?? []).filter((b) => b.id).map((b) => ({ id: b.id as string, name: b.name })))
  const radioOptions = $derived(
    app.radios
      .filter((r) => r.state === 'connected')
      .flatMap((r) => r.channels.filter((c) => c.role !== 'DISABLED').map((c): BotTarget => ({ kind: 'radio', radio_id: r.id, channel_index: c.index }))),
  )
  const mqttOptions = $derived(
    (settings.mqtt_brokers ?? [])
      .filter((b) => b.id && b.enabled)
      .flatMap((b) => (mqttNames[b.id as string] ?? []).map((ch): BotTarget => ({ kind: 'mqtt', broker: b.id as string, channel: ch }))),
  )
  // i bersagli gia' scelti restano visibili anche se la radio e' scollegata
  const options = $derived.by(() => {
    const all = [...radioOptions, ...mqttOptions]
    for (const tg of form.targets) if (!all.some((o) => sameTarget(o, tg))) all.push(tg)
    return all
  })
  const confirmed = $derived(confirmedBrokers(settings))
  const weatherNodes = $derived(visibleNodes(app.nodes.values()).filter((n) => n.is_mine))
  const savedTargets = $derived(settings.bot_targets ?? [])
  const enableCheck = $derived(canEnable({ targets: savedTargets, confirmedBrokers: confirmed }))
  const st = $derived(automation.bot)
  const enabled = $derived(settings.bot_enabled === true)

  const replyErrors = $derived(
    form.replies.map((r, i) => {
      const others = form.replies.filter((_, j) => j !== i).map((x) => x.trigger)
      return validateTrigger(r.trigger, others) ?? validateReplyText(r.text)
    }),
  )
  const limitsValid = $derived(
    validateLimit('bot_min_interval_s', form.minInterval) && validateLimit('bot_max_per_hour', form.maxPerHour)
      && validateLimit('bot_node_cooldown_s', form.cooldown),
  )
  const formValid = $derived(limitsValid && replyErrors.every((e) => e === null))

  function isOn(tg: BotTarget): boolean {
    return form.targets.some((x) => sameTarget(x, tg))
  }
  function setTarget(tg: BotTarget, on: boolean) {
    form.targets = toggleTarget(form.targets, tg, on)
  }
  function setCommand(c: BotCommand, on: boolean) {
    form.commands = on ? [...form.commands.filter((x) => x !== c), c] : form.commands.filter((x) => x !== c)
  }

  const errMsg = (e: unknown, fb: string) => (e instanceof ApiError ? e.message : fb)

  async function save() {
    if (!formValid) return
    busy = true
    error = ok = ''
    try {
      const s = await send<AppSettings>('PUT', '/settings', {
        bot_targets: form.targets,
        bot_commands: BOT_COMMANDS.filter((c) => form.commands.includes(c)),
        bot_weather_node: form.weather,
        bot_replies: form.replies,
        bot_min_interval_s: form.minInterval,
        bot_max_per_hour: form.maxPerHour,
        bot_node_cooldown_s: form.cooldown,
      })
      onsaved(s)
      ok = t('bot.saved')
    } catch (e) {
      error = errMsg(e, t('bot.saveFailed'))
    } finally {
      busy = false
    }
  }

  async function setEnabled(on: boolean) {
    confirming = false
    busy = true
    error = ok = ''
    try {
      const r = await enableBot(on)
      automation.bot = r.status
      await reload()
    } catch (e) {
      error = errMsg(e, t('bot.enableFailed'))
    } finally {
      busy = false
    }
  }

  async function runPreview() {
    error = ''
    try {
      preview = await previewBot(previewText)
    } catch (e) {
      error = errMsg(e, t('bot.saveFailed'))
    }
  }
</script>

<Card>
  <section class="sec">
    <div class="head">
      <h3>{t('bot.card.title')}</h3>
      <Badge kind={enabled ? 'ok' : 'neutral'}>{enabled ? t('bot.status.on') : t('bot.status.off')}</Badge>
    </div>
    <p class="muted">{t('bot.card.intro')}</p>
    {#if st}
      <p class="line">
        {t('bot.queued', { n: st.queued })} · {t('bot.sentHour', { n: st.sent_last_hour })}
        {#if pausedLabel(st.paused_until, now)} · {pausedLabel(st.paused_until, now)}{/if}
      </p>
      {#if st.last_error}<Banner kind="warn" title={t('bot.lastError', { error: t(errorKey(st.last_error)) })} />{/if}
    {/if}

    <h4>{t('bot.targets')}</h4>
    <p class="muted">{t('bot.targetsHint')}</p>
    {#if options.length === 0}
      <p class="muted">{t('bot.noTargets')}</p>
    {:else}
      <div class="grid">
        {#each options as tg (targetKey(tg))}
          <Check bind:checked={() => isOn(tg), (v) => setTarget(tg, v)} disabled={!isOn(tg) && form.targets.length >= MAX_BOT_TARGETS}>
            {targetLabel(tg, app.radios, brokers)}
            {#if tg.kind === 'mqtt' && !confirmed.includes(tg.broker)}<span class="muted">{t('bot.brokerUnconfirmed')}</span>{/if}
          </Check>
        {/each}
      </div>
    {/if}

    <h4>{t('bot.commands')}</h4>
    <div class="grid">
      {#each BOT_COMMANDS as c (c)}
        <Check bind:checked={() => form.commands.includes(c), (v) => setCommand(c, v)} label={t(`bot.cmd.${c}` as MsgKey)} />
      {/each}
    </div>
    <Field label={t('bot.weatherNode')} hint={t('bot.weatherHint')} for="bot-weather">
      {#snippet children()}
        <Select id="bot-weather" bind:value={form.weather}>
          <option value="">{t('bot.weatherNone')}</option>
          {#each weatherNodes as n (n.id)}<option value={n.id}>{n.long_name || n.id}</option>{/each}
        </Select>
      {/snippet}
    </Field>

    <h4>{t('bot.replies')}</h4>
    <p class="muted">{t('bot.repliesHint')}</p>
    {#each form.replies as r, i (i)}
      <div class="reply">
        <input class="ui-input" aria-label={t('bot.trigger')} placeholder={t('bot.trigger')} maxlength="32" bind:value={r.trigger} />
        <input class="ui-input grow" aria-label={t('bot.replyText')} placeholder={t('bot.replyText')} bind:value={r.text} />
        <Button iconOnly icon="trash" kind="danger" label={t('bot.removeReply', { trigger: r.trigger })} onclick={() => (form.replies = form.replies.filter((_, j) => j !== i))} />
        {#if replyErrors[i]}<span class="err">{t(replyErrors[i])}</span>{/if}
      </div>
    {/each}
    <div class="row">
      <Button disabled={form.replies.length >= MAX_BOT_REPLIES} onclick={() => (form.replies = [...form.replies, { trigger: '', text: '' }])}>{t('bot.addReply')}</Button>
    </div>

    <h4>{t('bot.limits')}</h4>
    <div class="limits">
      <Field label={t('bot.minInterval')} for="bot-min" error={validateLimit('bot_min_interval_s', form.minInterval) ? undefined : t('bot.err.limit')}>
        {#snippet children()}<input id="bot-min" class="ui-input ui-mono" type="number" min={LIMITS.bot_min_interval_s[0]} max={LIMITS.bot_min_interval_s[1]} step="1" bind:value={form.minInterval} />{/snippet}
      </Field>
      <Field label={t('bot.maxPerHour')} for="bot-max" error={validateLimit('bot_max_per_hour', form.maxPerHour) ? undefined : t('bot.err.limit')}>
        {#snippet children()}<input id="bot-max" class="ui-input ui-mono" type="number" min={LIMITS.bot_max_per_hour[0]} max={LIMITS.bot_max_per_hour[1]} step="1" bind:value={form.maxPerHour} />{/snippet}
      </Field>
      <Field label={t('bot.cooldown')} for="bot-cd" error={validateLimit('bot_node_cooldown_s', form.cooldown) ? undefined : t('bot.err.limit')}>
        {#snippet children()}<input id="bot-cd" class="ui-input ui-mono" type="number" min={LIMITS.bot_node_cooldown_s[0]} max={LIMITS.bot_node_cooldown_s[1]} step="1" bind:value={form.cooldown} />{/snippet}
      </Field>
    </div>
    <div class="row">
      <Button kind="primary" disabled={busy || !dirty || !formValid} onclick={save}>{t('bot.save')}</Button>
    </div>

    <h4>{t('bot.preview')}</h4>
    <div class="row">
      <input class="ui-input grow" aria-label={t('bot.preview')} placeholder={t('bot.previewHint')} maxlength="200" bind:value={previewText} />
      <Button disabled={!previewText.trim()} onclick={runPreview}>{t('bot.previewRun')}</Button>
    </div>
    {#if preview}
      <p class="line ui-mono">{preview.reply ?? t('bot.previewNone')}</p>
      {#if preview.sample}<p class="muted">{t('bot.previewSample')}</p>{/if}
    {/if}

    <div class="row">
      {#if enabled}
        <Button kind="danger" disabled={busy} onclick={() => void setEnabled(false)}>{t('bot.disable')}</Button>
      {:else}
        <Button kind="primary" disabled={busy || !local || dirty || !enableCheck.ok} onclick={() => (confirming = true)}>{t('bot.enable')}</Button>
      {/if}
    </div>
    {#if !enabled}
      {#if !local}
        <Banner kind="info" title={t('bot.enable.localOnly')} />
      {:else if dirty}
        <p class="muted">{t('bot.unsaved')}</p>
      {:else if enableCheck.reason}
        <p class="muted">{t(enableCheck.reason)}</p>
      {/if}
    {/if}
    {#if error}<Banner kind="danger" title={error} />{/if}
    {#if ok}<Banner kind="ok" title={ok} />{/if}
  </section>
</Card>

<Modal
  open={confirming}
  risk
  title={t('bot.enableTitle')}
  riskLabel={t('bot.enableRisk')}
  confirmLabel={t('bot.enable')}
  onconfirm={() => void setEnabled(true)}
  oncancel={() => (confirming = false)}
>
  <p>{t('bot.enableBody')}</p>
  <ul class="list">
    {#each savedTargets as tg (targetKey(tg))}<li>{targetLabel(tg, app.radios, brokers)}</li>{/each}
  </ul>
  <p>{t('bot.optin.public')}</p>
  <p>{t('bot.optin.limits', { n: settings.bot_max_per_hour ?? 20, s: settings.bot_min_interval_s ?? 30, c: settings.bot_node_cooldown_s ?? 300 })}</p>
  {#if savedTargets.some((tg) => tg.kind === 'mqtt')}<p>{t('bot.optin.mqtt')}</p>{/if}
  <p>{t('bot.optin.loop')}</p>
  <p>{t('bot.optin.duty')}</p>
</Modal>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  .head { display: flex; align-items: center; gap: var(--space-2); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  h4 { margin: var(--space-2) 0 0; font: 600 14px/20px var(--font-sans); }
  p { margin: 0; }
  .line { font: 400 14px/20px var(--font-sans); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: var(--space-2); }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .reply { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .reply input:first-child { flex: 0 1 160px; }
  .grow { flex: 1 1 220px; }
  .limits { display: flex; gap: var(--space-3); flex-wrap: wrap; }
  .limits :global(.ui-field) { flex: 1 1 200px; }
  .err { flex-basis: 100%; color: var(--danger); font: 400 13px/18px var(--font-sans); }
  .list { margin: var(--space-2) 0; padding-left: var(--space-4); }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  :global(.vp-phone) .muted, :global(.vp-phone) .err { font-size: 14px; line-height: 20px; }
</style>
