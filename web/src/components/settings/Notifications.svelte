<script lang="ts">
import { safeStorage } from '../../lib/storage'
  import { onMount } from 'svelte'
  import { ApiError, getJSON, notifyStatus, notifyTest, send, telegramFindChat, type NotifyStatus } from '../../lib/api'
  import { loadNotifyPrefs, notifySupported, saveNotifyPrefs } from '../../lib/notify'
  import { parseKeywords, type AppSettings } from '../../lib/settings'
  import { t } from '../../lib/i18n/index.svelte'
  import { translateServer } from '../../lib/i18n/server'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Check from '../../lib/ui/Check.svelte'
  import Field from '../../lib/ui/Field.svelte'
  import Switch from '../../lib/ui/Switch.svelte'
  import Toast from '../../lib/ui/Toast.svelte'

  const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

  // Su questo dispositivo: preferenza del browser (safeStorage()), non salvata sul server
  const supported = notifySupported(window as unknown as { isSecureContext?: boolean; [k: string]: unknown })
  let dmOn = $state(false)
  let dmDenied = $state(false)

  // Notifiche esterne: impostazioni del server
  let toast = $state(true)
  let telegram = $state(false)
  let mineStatus = $state(true)
  let newNode = $state(false)
  let keywordsText = $state('')
  let chatId = $state('')
  let chatTitle = $state('')
  let tokenSet = $state(false)
  let replacing = $state(false)
  let tokenInput = $state('')
  let status = $state<NotifyStatus | null>(null)
  let testResult = $state<{ kind: 'ok' | 'warn'; text: string } | null>(null)

  let loaded = $state(false)
  let loadFailed = $state(false)
  let error = $state('')
  let info = $state('')
  let busy = $state(false)
  let testing = $state<'toast' | 'telegram' | null>(null)

  const toastAvailable = $derived(status?.toast_available ?? false)
  const chatOk = $derived(chatId.trim() === '' || /^-?\d{1,20}$/.test(chatId.trim()))

  async function refreshStatus() {
    try {
      status = await notifyStatus()
    } catch {
      /* resta l'ultimo stato noto */
    }
  }

  onMount(async () => {
    dmOn = loadNotifyPrefs(safeStorage()).dm
    try {
      const s = await getJSON<AppSettings>('/settings')
      toast = s.notify_toast ?? true
      telegram = s.notify_telegram ?? false
      mineStatus = s.notify_mine_status ?? true
      newNode = s.notify_new_node ?? false
      keywordsText = (s.notify_keywords ?? []).join(', ')
      chatId = s.telegram_chat_id ?? ''
      tokenSet = !!s.telegram_token
      loaded = true
    } catch {
      loadFailed = true
    }
    await refreshStatus()
  })

  async function setDm(v: boolean) {
    dmDenied = false
    if (!v) {
      dmOn = false
      saveNotifyPrefs(safeStorage(), { dm: false })
      return
    }
    let permission: NotificationPermission = Notification.permission
    if (permission !== 'granted') {
      try {
        permission = await Notification.requestPermission()
      } catch {
        permission = 'denied'
      }
    }
    if (permission === 'granted') {
      dmOn = true
      saveNotifyPrefs(safeStorage(), { dm: true })
    } else {
      dmOn = false
      dmDenied = true
      saveNotifyPrefs(safeStorage(), { dm: false })
    }
  }

  // Invio con Invio nei campi: senza questo, il modulo dell'intera pagina Impostazioni si invierebbe
  function noSubmit(e: KeyboardEvent) {
    if (e.key === 'Enter') e.preventDefault()
  }

  async function put(body: Record<string, unknown>, done: string): Promise<boolean> {
    error = info = ''
    try {
      await send<AppSettings>('PUT', '/settings', body)
      info = done
      return true
    } catch (e) {
      error = errMsg(e, t('notify.saveFailed'))
      return false
    }
  }

  async function saveToken() {
    const v = tokenInput.trim()
    if (v === '') {
      // campo vuoto: il token resta invariato
      replacing = false
      return
    }
    if (await put({ telegram_token: v }, t('notify.tokenSaved'))) {
      tokenSet = true
      tokenInput = ''
      replacing = false
    }
  }

  async function removeToken() {
    if (await put({ telegram_token: '' }, t('notify.tokenRemoved'))) {
      tokenSet = false
      tokenInput = ''
      replacing = false
    }
  }

  async function findChat() {
    error = info = ''
    busy = true
    try {
      const r = await telegramFindChat()
      chatId = r.chat_id
      chatTitle = r.title
    } catch (e) {
      error = errMsg(e, t('notify.findChatFailed'))
    } finally {
      busy = false
    }
  }

  async function saveExternal() {
    if (!chatOk) return
    const keywords = parseKeywords(keywordsText)
    busy = true
    const done = await put(
      {
        notify_toast: toast,
        notify_telegram: telegram,
        telegram_chat_id: chatId.trim(),
        notify_mine_status: mineStatus,
        notify_new_node: newNode,
        notify_keywords: keywords,
      },
      t('notify.saved'),
    )
    if (done) keywordsText = keywords.join(', ')
    busy = false
    await refreshStatus()
  }

  async function test(channel: 'toast' | 'telegram') {
    testing = channel
    testResult = null
    try {
      await notifyTest(channel)
      testResult = { kind: 'ok', text: t('notify.testSent') }
    } catch (e) {
      testResult = { kind: 'warn', text: t('notify.testFailed', { reason: errMsg(e, t('notify.saveFailed')) }) }
    } finally {
      testing = null
    }
    if (channel === 'telegram') await refreshStatus()
  }
</script>

<Card>
  <section class="sec">
    <h3>{t('notify.title')}</h3>
    {#if loadFailed}
      <Banner kind="danger" title={t('notify.loadFailed')} />
    {:else if !loaded}
      <p class="muted">{t('notify.loadFailed')}</p>
    {:else}
      <div class="grp">
        <h4>{t('notify.deviceGroup')}</h4>
        <Switch bind:checked={dmOn} disabled={!supported} label={t('notify.dmSwitch')} onchange={setDm} />
        {#if !supported}<p class="ui-hint">{t('chat.notifyUnsupported')}</p>{/if}
        {#if dmDenied}<Banner kind="warn" title={t('notify.permissionDenied')} />{/if}
      </div>

      <div class="grp">
        <h4>{t('notify.externalGroup')}</h4>

        <Switch bind:checked={toast} disabled={!toastAvailable} label={t('notify.toastSwitch')} />
        {#if status && !toastAvailable}<p class="ui-hint">{t('notify.toastUnavailable')}</p>{/if}

        <Switch bind:checked={telegram} label={t('notify.telegramSwitch')} />

        <div class="tok">
          <span class="ui-lbl" id="notif-token-label">{t('notify.tokenLabel')}</span>
          {#if tokenSet && !replacing}
            <div class="row">
              <span class="ui-hint" aria-labelledby="notif-token-label">{t('notify.tokenSet')}</span>
              <Button onclick={() => (replacing = true)}>{t('notify.tokenChange')}</Button>
              <Button kind="danger" onclick={removeToken} disabled={busy}>{t('notify.tokenRemove')}</Button>
            </div>
          {:else}
            <div class="row">
              <input
                class="ui-input ui-mono grow"
                type="password"
                autocomplete="off"
                aria-labelledby="notif-token-label"
                placeholder={t('notify.tokenPlaceholder')}
                onkeydown={noSubmit}
                bind:value={tokenInput}
              />
              <Button kind="primary" onclick={saveToken} disabled={busy}>{t('notify.tokenSave')}</Button>
              {#if replacing}<Button onclick={() => ((replacing = false), (tokenInput = ''))}>{t('common.cancel')}</Button>{/if}
            </div>
          {/if}
        </div>

        <Field
          label={t('notify.chatLabel')}
          for="notif-chat"
          error={chatOk ? undefined : t('notify.chatInvalid')}
          hint={chatTitle ? t('notify.chatFound', { title: chatTitle }) : t('notify.chatHint')}
        >
          {#snippet children({ describedby, invalid })}
            <div class="row">
              <input
                id="notif-chat"
                class="ui-input ui-mono grow"
                class:err={invalid}
                type="text"
                inputmode="numeric"
                autocomplete="off"
                autocapitalize="off"
                spellcheck="false"
                aria-describedby={describedby}
                aria-invalid={invalid}
                onkeydown={noSubmit}
                bind:value={chatId}
              />
              <Button disabled={!tokenSet || busy} onclick={findChat}>{t('notify.findChat')}</Button>
            </div>
          {/snippet}
        </Field>

        <div class="row">
          <Button disabled={!toastAvailable || testing !== null} onclick={() => test('toast')}>{t('notify.sendTestToast')}</Button>
          <Button disabled={!tokenSet || !chatOk || testing !== null} onclick={() => test('telegram')}>{t('notify.sendTestTelegram')}</Button>
        </div>
        {#if testResult}
          <Toast kind={testResult.kind} onclose={() => (testResult = null)}>{testResult.text}</Toast>
        {/if}

        {#if status?.telegram_last_error}
          <Banner kind="warn" title={t('notify.telegramLastError', { reason: translateServer(status.telegram_last_error) })} />
        {/if}

        <Check bind:checked={mineStatus} label={t('notify.mineStatus')} />
        <Check bind:checked={newNode} label={t('notify.newNode')} />

        <Field label={t('notify.keywordsLabel')} for="notif-keywords" hint={t('notify.keywordsHint')}>
          {#snippet children({ describedby })}
            <textarea id="notif-keywords" class="ui-input ui-mono" rows="2" aria-describedby={describedby} bind:value={keywordsText}></textarea>
          {/snippet}
        </Field>

        <div class="row">
          <Button kind="primary" disabled={busy || !chatOk} onclick={saveExternal}>{t('notify.save')}</Button>
        </div>
      </div>

      {#if error}<Banner kind="danger" title={error} />{/if}
      {#if info}<Banner kind="ok" title={info} />{/if}
    {/if}
  </section>
</Card>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  h4 { margin: 0; font: 600 14px/20px var(--font-sans); color: var(--ink-muted); }
  p { margin: 0; }
  .grp { display: flex; flex-direction: column; gap: var(--space-3); }
  .tok { display: flex; flex-direction: column; gap: var(--space-2); }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .grow { flex: 1; min-width: 160px; width: auto; }
  .err { color: var(--danger); }
  .muted { color: var(--ink-muted); font: 400 13px/18px var(--font-sans); }
  textarea { min-height: 64px; resize: vertical; }
  :global(.vp-phone) .muted { font-size: 14px; line-height: 20px; }
</style>
