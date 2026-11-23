<script lang="ts">
  // Impostazioni → «Avvisi su misura»: elenco delle regole, modulo di creazione/modifica, eliminazione.
  import { onDestroy, onMount } from 'svelte'
  import { ApiError } from '../../lib/api'
  import {
    createRule,
    deleteRule,
    draftFromRule,
    draftToBody,
    emptyDraft,
    listRules,
    patchRule,
    ruleIcon,
    ruleSummary,
    type RuleDraft,
  } from '../../lib/alertrules'
  import { visibleNodes } from '../../lib/filters'
  import { ago } from '../../lib/format'
  import { t } from '../../lib/i18n/index.svelte'
  import { app } from '../../lib/stores.svelte'
  import type { AlertRule } from '../../lib/types'
  import { onWsEvent, onWsResync } from '../../lib/wsext'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Empty from '../../lib/ui/Empty.svelte'
  import Icon from '../../lib/ui/Icon.svelte'
  import Modal from '../../lib/ui/Modal.svelte'
  import Switch from '../../lib/ui/Switch.svelte'
  import AlertRuleForm from './AlertRuleForm.svelte'

  const errMsg = (e: unknown, fallback: string) => (e instanceof ApiError ? e.message : fallback)

  let rules = $state<AlertRule[]>([])
  let loaded = $state(false)
  let loadFailed = $state(false)
  let error = $state('')
  let info = $state('')
  let busy = $state(false)
  let editing = $state<RuleDraft | null>(null)
  let deleting = $state<AlertRule | null>(null)
  let now = $state(Date.now() / 1000)

  const nodes = $derived(visibleNodes([...app.nodes.values()]))
  const radios = $derived(app.radios.map((r) => ({ id: r.id, name: r.name })))
  const mqttChannels = $derived([...new Set(app.messages.filter((m) => m.source === 'mqtt' && m.channel).map((m) => m.channel))].sort())

  function nodeName(id: string): string {
    const n = app.nodes.get(id)
    return n?.long_name || n?.short_name || id
  }

  async function reload() {
    try {
      rules = await listRules()
      loaded = true
      loadFailed = false
    } catch {
      loadFailed = !loaded
    }
  }

  let offEvent: (() => void) | null = null
  let offResync: (() => void) | null = null
  let tick: ReturnType<typeof setInterval> | null = null
  onMount(() => {
    void reload()
    offEvent = onWsEvent('alert_rules', (msg) => {
      rules = msg.rules as AlertRule[]
      loaded = true
    })
    offResync = onWsResync(() => void reload())
    tick = setInterval(() => (now = Date.now() / 1000), 30_000)
  })
  onDestroy(() => {
    offEvent?.()
    offResync?.()
    if (tick) clearInterval(tick)
  })

  function startNew() {
    error = info = ''
    editing = emptyDraft('keyword')
  }
  function startEdit(r: AlertRule) {
    error = info = ''
    editing = draftFromRule(r)
  }

  async function save(d: RuleDraft) {
    error = info = ''
    busy = true
    try {
      const body = draftToBody(d)
      const saved = d.id === null ? await createRule(body) : await patchRule(d.id, body)
      rules = rules.some((r) => r.id === saved.id) ? rules.map((r) => (r.id === saved.id ? saved : r)) : [...rules, saved]
      editing = null
      info = t('alertrules.saved')
    } catch (e) {
      error = errMsg(e, t('alertrules.saveFailed'))
    } finally {
      busy = false
    }
  }

  async function toggle(r: AlertRule, enabled: boolean) {
    error = info = ''
    try {
      const saved = await patchRule(r.id, { enabled })
      rules = rules.map((x) => (x.id === saved.id ? saved : x))
    } catch (e) {
      error = errMsg(e, t('alertrules.saveFailed'))
      await reload()
    }
  }

  async function confirmDelete() {
    const r = deleting
    if (!r) return
    busy = true
    error = info = ''
    try {
      await deleteRule(r.id)
      rules = rules.filter((x) => x.id !== r.id)
      info = t('alertrules.deleted')
    } catch (e) {
      error = errMsg(e, t('alertrules.saveFailed'))
    } finally {
      busy = false
      deleting = null
    }
  }

  const label = (r: AlertRule) => r.name || ruleSummary(r, nodeName)
</script>

<Card>
  <section class="sec">
    <h3>{t('alertrules.title')}</h3>
    <p class="ui-hint">{t('alertrules.intro')}</p>

    {#if loadFailed}
      <Banner kind="danger" title={t('alertrules.loadFailed')} />
    {:else if editing}
      <AlertRuleForm draft={editing} {nodes} {radios} {mqttChannels} {busy} {error} onsave={save} oncancel={() => (editing = null)} />
    {:else if loaded}
      <div class="row">
        <Button kind="primary" icon="plus" onclick={startNew}>{t('alertrules.add')}</Button>
      </div>
      {#if rules.length === 0}
        <Empty icon="alert" title={t('alertrules.empty')} />
      {:else}
        <ul class="list">
          {#each rules as r (r.id)}
            <li class="item">
              <span class="ico"><Icon name={ruleIcon(r.kind)} size={18} /></span>
              <div class="txt">
                <span class="main">{label(r)}</span>
                {#if r.name}<span class="ui-hint">{ruleSummary(r, nodeName)}</span>{/if}
                <span class="ui-hint">{r.last_fired === null ? t('alertrules.neverFired') : t('alertrules.lastFired', { when: ago((now - r.last_fired) / 60) })}</span>
              </div>
              <div class="act">
                <Switch checked={r.enabled} label={t('alertrules.field.enabled')} onchange={(v) => toggle(r, v)} />
                <Button icon="edit" iconOnly label={t('alertrules.edit')} onclick={() => startEdit(r)} />
                <Button icon="trash" iconOnly kind="danger" label={t('alertrules.remove')} onclick={() => (deleting = r)} />
              </div>
            </li>
          {/each}
        </ul>
      {/if}
      {#if error}<Banner kind="danger" title={error} />{/if}
      {#if info}<Banner kind="ok" title={info} />{/if}
    {:else}
      <p class="ui-hint">{t('alertrules.loadFailed')}</p>
    {/if}
  </section>
</Card>

<Modal
  open={deleting !== null}
  title={t('alertrules.delete.title')}
  danger
  confirmLabel={t('alertrules.delete.confirm')}
  onconfirm={confirmDelete}
  oncancel={() => (deleting = null)}
>
  <p>{t('alertrules.delete.text', { name: deleting ? label(deleting) : '' })}</p>
</Modal>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .row { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .item { display: flex; align-items: flex-start; gap: var(--space-2); padding: var(--space-2); border: 1px solid var(--line); border-radius: var(--radius-md); flex-wrap: wrap; }
  .ico { display: inline-flex; flex: none; margin-top: 2px; color: var(--accent); }
  .txt { display: flex; flex-direction: column; flex: 1; min-width: 160px; }
  .main { font: 500 14px/20px var(--font-sans); overflow-wrap: anywhere; }
  .act { display: flex; align-items: center; gap: var(--space-2); flex-wrap: wrap; }
  :global(.vp-phone) .ui-hint { font-size: 14px; line-height: 20px; }
</style>
