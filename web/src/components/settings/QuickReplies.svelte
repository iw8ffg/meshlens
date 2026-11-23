<script lang="ts">
  // Messaggi rapidi (WP1, E10): elenco gestito nelle impostazioni, usato dal compositore della chat.
  import { onMount } from 'svelte'
  import { t } from '../../lib/i18n/index.svelte'
  import type { MsgKey } from '../../lib/i18n/index.svelte'
  import { translateServer } from '../../lib/i18n/server'
  import { MAX_QUICK_REPLIES, QUICK_REPLY_MAX_BYTES, VARIABLES, validateQuickReply } from '../../lib/quickreplies'
  import type { QuickReplyError } from '../../lib/quickreplies'
  import { loadQuickReplies, quick, saveQuickReplies } from '../../lib/quickreplies.svelte'
  import { byteCount } from '../../lib/send'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Field from '../../lib/ui/Field.svelte'

  const uid = $props.id()
  let draft = $state<string[]>([])
  let newText = $state('')
  let saving = $state(false)
  let saveError = $state('')
  let savedOk = $state(false)

  async function init(force = false) {
    await loadQuickReplies(force)
    draft = [...quick.list]
  }
  onMount(() => void init())

  const dirty = $derived(JSON.stringify(draft) !== JSON.stringify(quick.list))
  const trimmed = $derived(newText.trim())
  const newError = $derived<QuickReplyError | null>(trimmed === '' ? null : validateQuickReply(trimmed, draft))
  const full = $derived(draft.length >= MAX_QUICK_REPLIES)
  const canAdd = $derived(trimmed !== '' && newError === null && !full)

  const ERR: Record<QuickReplyError, MsgKey> = {
    empty: 'quick.err.empty',
    edges: 'quick.err.edges',
    tooLong: 'quick.err.tooLong',
    control: 'quick.err.control',
    duplicate: 'quick.err.duplicate',
  }

  function add(text: string) {
    if (draft.length >= MAX_QUICK_REPLIES || validateQuickReply(text, draft) !== null) return
    draft = [...draft, text]
    savedOk = false
  }

  function addNew() {
    if (!canAdd) return
    add(trimmed)
    newText = ''
  }

  function addExamples() {
    for (const k of ['quick.example.1', 'quick.example.2', 'quick.example.3'] as const) add(t(k))
  }

  function move(i: number, delta: number) {
    const j = i + delta
    if (j < 0 || j >= draft.length) return
    const next = [...draft]
    ;[next[i], next[j]] = [next[j], next[i]]
    draft = next
    savedOk = false
  }

  function remove(i: number) {
    draft = draft.filter((_, k) => k !== i)
    savedOk = false
  }

  async function save() {
    saving = true
    saveError = ''
    savedOk = false
    try {
      await saveQuickReplies(draft)
      draft = [...quick.list]
      savedOk = true
    } catch (e) {
      saveError = translateServer(e instanceof Error ? e.message : '') || t('quick.saveError')
    } finally {
      saving = false
    }
  }
</script>

<Card>
  <section class="sec">
    <h3>{t('quick.title')}</h3>
    <p class="muted">{t('quick.intro')}</p>
    <p class="muted">{t('quick.variables')}</p>
    <Banner kind="warn" title={t('quick.positionWarning')} />

    {#if quick.error && !quick.loaded}
      <Banner kind="danger" title={t('quick.loadError')}>
        {#snippet action()}<Button onclick={() => init(true)}>{t('common.retry')}</Button>{/snippet}
      </Banner>
    {:else}
      {#if draft.length === 0}
        <p class="muted">{t('quick.emptyList')}</p>
      {:else}
        <ul class="list">
          {#each draft as r, i (r)}
            {@const bc = byteCount(r, QUICK_REPLY_MAX_BYTES)}
            <li>
              <div class="tx">
                <span class="txt">{r}</span>
                <span class="muted ui-mono">{t('quick.bytes', { n: bc.bytes, max: bc.max })}</span>
              </div>
              <div class="btns">
                <Button iconOnly icon="chevU" label={t('quick.up')} disabled={i === 0} onclick={() => move(i, -1)} />
                <Button iconOnly icon="chevD" label={t('quick.down')} disabled={i === draft.length - 1} onclick={() => move(i, 1)} />
                <Button iconOnly icon="trash" label={t('quick.remove')} onclick={() => remove(i)} />
              </div>
            </li>
          {/each}
        </ul>
      {/if}

      <Field label={t('quick.newLabel')} for="{uid}-new" error={newError ? t(ERR[newError]) : undefined} hint={full ? t('quick.max', { max: MAX_QUICK_REPLIES }) : t('quick.variablesHint', { names: VARIABLES.map((v) => `{${v}}`).join(' ') })}>
        {#snippet children({ describedby, invalid })}
          <div class="row">
            <input
              id="{uid}-new"
              class="ui-input grow"
              type="text"
              autocomplete="off"
              aria-describedby={describedby}
              aria-invalid={invalid}
              placeholder={t('quick.placeholder')}
              bind:value={newText}
              onkeydown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addNew() } }}
            />
            <Button disabled={!canAdd} onclick={addNew}>{t('quick.add')}</Button>
          </div>
        {/snippet}
      </Field>

      <div class="row foot">
        <span class="muted ui-mono">{t('quick.count', { n: draft.length, max: MAX_QUICK_REPLIES })}</span>
        <Button onclick={addExamples} disabled={full}>{t('quick.addExamples')}</Button>
        <Button kind="primary" disabled={!dirty || saving} onclick={save}>{t('quick.save')}</Button>
      </div>
      {#if savedOk}<p class="muted" role="status">{t('quick.saved')}</p>{/if}
      {#if saveError}<Banner kind="danger" title={saveError} />{/if}
    {/if}
  </section>
</Card>

<style>
  .sec { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .muted { color: var(--ink-muted); font: 400 14px/20px var(--font-sans); }
  .list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: var(--space-2); }
  .list li { display: flex; align-items: center; gap: var(--space-2); border: 1px solid var(--line); border-radius: var(--radius-md); padding: var(--space-2) var(--space-3); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .txt { overflow-wrap: anywhere; }
  .btns { display: flex; gap: var(--space-1); flex: none; }
  .row { display: flex; gap: var(--space-2); align-items: center; flex-wrap: wrap; }
  .grow { flex: 1; min-width: 160px; }
  .foot { justify-content: flex-end; }
  .foot .muted { margin-right: auto; }
</style>
