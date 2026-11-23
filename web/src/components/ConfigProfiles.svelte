<script lang="ts">
  // WP4 (E7): profili di configurazione (salva da questa radio, anteprima su questo nodo,
  // esporta/importa) e confronto fra due radio. I profili non contengono mai segreti.
  import { onMount } from 'svelte'
  import { ApiError } from '../lib/api'
  import { pathLabel } from '../lib/config'
  import { formatDate } from '../lib/format'
  import { t, type MsgKey } from '../lib/i18n/index.svelte'
  import { nodeName } from '../lib/nodes'
  import {
    compareProfiles,
    deleteProfile,
    exportProfileUrl,
    importProfile,
    listProfiles,
    parseProfileFile,
    previewProfile,
    readSections,
    renameProfile,
    saveProfile,
    sectionGroups,
    sectionLabel,
  } from '../lib/profiles'
  import { app } from '../lib/stores.svelte'
  import type { ConfigPreview, ConfigProfile, ConfigSaved, ProfileCompare } from '../lib/types'
  import Banner from '../lib/ui/Banner.svelte'
  import Button from '../lib/ui/Button.svelte'
  import Check from '../lib/ui/Check.svelte'
  import Empty from '../lib/ui/Empty.svelte'
  import Field from '../lib/ui/Field.svelte'
  import Modal from '../lib/ui/Modal.svelte'

  let {
    nodeId,
    radioId,
    saved,
    lock,
    onpreview,
  }: {
    nodeId: string
    radioId: string | null
    saved: ConfigSaved | null
    lock: boolean
    onpreview: (p: ConfigPreview, skipped: string[]) => void
  } = $props()

  let profiles = $state<ConfigProfile[]>([])
  let error = $state('')
  let info = $state('')
  let busy = $state(false)

  // salva da questa radio
  let name = $state('')
  let notes = $state('')
  const available = $derived(saved ? readSections(saved.sections) : [])
  // sezioni scelte per il salvataggio: accese di default
  let saveOn = $state<Record<string, boolean>>({})
  $effect(() => {
    for (const s of available) if (!(s in saveOn)) saveOn[s] = true
  })
  const chosen = $derived(available.filter((s) => saveOn[s]))
  const groups = $derived(sectionGroups(available))

  // azioni sui profili
  let previewOf = $state<number | null>(null)
  let previewOn = $state<Record<string, boolean>>({})
  let renaming = $state<number | null>(null)
  let newName = $state('')
  let deleting = $state<ConfigProfile | null>(null)

  // confronto
  let sideA = $state('')
  let sideB = $state('')
  let result = $state<ProfileCompare | null>(null)

  const errText = (e: unknown) => (e instanceof ApiError ? e.message : t('profiles.failed'))

  // nodi confrontabili: questo nodo, i miei nodi e i nodi delle radio collegate
  const nodeChoices = $derived.by(() => {
    const ids = new Set<string>([nodeId])
    for (const r of app.radios) if (r.my_node_id) ids.add(r.my_node_id)
    for (const n of app.nodes.values()) if (n.is_mine && !n.is_ignored) ids.add(n.id)
    return [...ids].map((id) => {
      const n = app.nodes.get(id)
      return { id, label: n ? nodeName(n) : id }
    })
  })

  async function load() {
    try {
      profiles = await listProfiles()
    } catch (e) {
      error = errText(e)
    }
  }
  onMount(() => {
    sideB = nodeId
    void load()
  })

  async function act(fn: () => Promise<void>) {
    busy = true
    error = ''
    info = ''
    try {
      await fn()
    } catch (e) {
      error = errText(e)
    } finally {
      busy = false
    }
  }

  const save = () =>
    act(async () => {
      await saveProfile({ node_id: nodeId, name: name.trim(), sections: chosen, notes: notes.trim() || null })
      name = ''
      notes = ''
      info = t('profiles.saved')
      await load()
    })

  function openPreview(p: ConfigProfile) {
    previewOf = previewOf === p.id ? null : p.id
    previewOn = Object.fromEntries(p.sections.map((s) => [s, true]))
  }

  const runPreview = (p: ConfigProfile) =>
    act(async () => {
      const secs = p.sections.filter((s) => previewOn[s])
      const res = await previewProfile(p.id, nodeId, secs.length === p.sections.length ? null : secs)
      previewOf = null
      onpreview(res.preview, res.skipped)
    })

  const compareWith = (p: ConfigProfile) =>
    act(async () => {
      sideA = `p:${p.id}`
      sideB = nodeId
      result = await compareProfiles({ profile: p.id, b: nodeId })
    })

  const rename = (p: ConfigProfile) =>
    act(async () => {
      await renameProfile(p.id, { name: newName.trim() })
      renaming = null
      await load()
    })

  const confirmDelete = () =>
    act(async () => {
      const p = deleting
      deleting = null
      if (!p) return
      await deleteProfile(p.id)
      await load()
    })

  async function onFile(e: Event) {
    const input = e.currentTarget as HTMLInputElement
    const file = input.files?.[0]
    input.value = ''
    if (!file) return
    await act(async () => {
      let doc: Record<string, unknown>
      try {
        doc = parseProfileFile(await file.text())
      } catch (err) {
        error = t((err as Error).message as MsgKey)
        return
      }
      await importProfile(doc)
      info = t('profiles.imported')
      await load()
    })
  }

  const runCompare = () =>
    act(async () => {
      if (!sideA || !sideB) return
      result = await compareProfiles(
        sideA.startsWith('p:') ? { profile: Number(sideA.slice(2)), b: sideB } : { a: sideA, b: sideB },
      )
    })

  const show = (v: unknown) => (v === null || v === undefined ? '–' : typeof v === 'object' ? JSON.stringify(v) : String(v))
</script>

{#snippet boxes(title: string, list: string[])}
  {#if list.length}
    <fieldset>
      <legend>{title}</legend>
      {#each list as s (s)}
        {#if s in saveOn}<Check bind:checked={saveOn[s]} label={sectionLabel(s)} disabled={lock || busy} />{/if}
      {/each}
    </fieldset>
  {/if}
{/snippet}

<section class="cp">
  <h3>{t('profiles.save.title')}</h3>
  <p class="muted">{t('profiles.neverCopied')}</p>
  {#if !saved}
    <p class="muted">{t('profiles.save.readFirst')}</p>
  {:else}
    <div class="row">
      <Field label={t('profiles.name')} for="prof-name">
        {#snippet children()}<input id="prof-name" class="ui-input" maxlength="60" bind:value={name} disabled={lock || busy} />{/snippet}
      </Field>
      <Field label={t('profiles.notes')} for="prof-notes">
        {#snippet children()}<input id="prof-notes" class="ui-input" maxlength="500" bind:value={notes} disabled={lock || busy} placeholder={t('profiles.optional')} />{/snippet}
      </Field>
    </div>
    {@render boxes(t('profiles.group.config'), groups.config)}
    {@render boxes(t('profiles.group.modules'), groups.module_config)}
    <div><Button kind="primary" icon="download" disabled={lock || busy || !name.trim() || chosen.length === 0} onclick={save}>{t('profiles.save.button')}</Button></div>
  {/if}

  {#if error}<Banner kind="danger" title={error} />{/if}
  {#if info}<Banner kind="ok" title={info} />{/if}

  <h3>{t('profiles.list.title')}</h3>
  {#if profiles.length === 0}
    <Empty icon="layers" title={t('profiles.list.empty')} />
  {:else}
    <ul class="list">
      {#each profiles as p (p.id)}
        <li>
          <div class="head">
            {#if renaming === p.id}
              <input class="ui-input grow" maxlength="60" bind:value={newName} aria-label={t('profiles.name')} />
              <Button disabled={busy || !newName.trim()} onclick={() => rename(p)}>{t('profiles.rename.save')}</Button>
              <Button kind="ghost" onclick={() => (renaming = null)}>{t('common.cancel')}</Button>
            {:else}
              <b class="grow">{p.name}</b>
            {/if}
          </div>
          <p class="muted">
            {[p.source_hw, p.firmware, formatDate(p.updated)].filter(Boolean).join(' · ')}
            {#if p.notes}<br />{p.notes}{/if}
          </p>
          <p class="muted">{p.sections.map(sectionLabel).join(', ')}</p>
          <div class="acts">
            <Button disabled={lock || busy} onclick={() => openPreview(p)}>{t('profiles.preview')}</Button>
            <Button disabled={busy} onclick={() => compareWith(p)}>{t('profiles.compareHere')}</Button>
            <a class="ui-btn" href={exportProfileUrl(p.id)} download>{t('profiles.export')}</a>
            <Button kind="ghost" disabled={busy} onclick={() => { renaming = p.id; newName = p.name }}>{t('profiles.rename')}</Button>
            <Button kind="ghost" icon="trash" disabled={busy} onclick={() => (deleting = p)}>{t('profiles.delete')}</Button>
          </div>
          {#if previewOf === p.id}
            <fieldset>
              <legend>{t('profiles.preview.sections')}</legend>
              {#each p.sections as s (s)}
                {#if s in previewOn}<Check bind:checked={previewOn[s]} label={sectionLabel(s)} />{/if}
              {/each}
            </fieldset>
            <div><Button kind="primary" disabled={lock || busy || !p.sections.some((s) => previewOn[s])} onclick={() => runPreview(p)}>{t('profiles.preview.run')}</Button></div>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  <h3>{t('profiles.import.title')}</h3>
  <label class="file">
    <span class="ui-lbl">{t('profiles.import.pick')}</span>
    <input type="file" accept=".json,application/json" disabled={busy} onchange={onFile} />
  </label>

  <h3>{t('profiles.compare.title')}</h3>
  <div class="row">
    <Field label={t('profiles.compare.a')} for="prof-a">
      {#snippet children()}
        <select id="prof-a" class="ui-select" bind:value={sideA}>
          <option value="">{t('profiles.compare.pick')}</option>
          {#each nodeChoices as n (n.id)}<option value={n.id}>{n.label}</option>{/each}
          {#each profiles as p (p.id)}<option value={`p:${p.id}`}>{t('profiles.compare.profile', { name: p.name })}</option>{/each}
        </select>
      {/snippet}
    </Field>
    <Field label={t('profiles.compare.b')} for="prof-b">
      {#snippet children()}
        <select id="prof-b" class="ui-select" bind:value={sideB}>
          {#each nodeChoices as n (n.id)}<option value={n.id}>{n.label}</option>{/each}
        </select>
      {/snippet}
    </Field>
    <Button disabled={busy || !sideA || !sideB} onclick={runCompare}>{t('profiles.compare.run')}</Button>
  </div>
  <p class="muted">{t('profiles.compare.hint')}</p>
  {#if result}
    {#if result.rows.length === 0}
      <Empty icon="check" title={t('profiles.compare.none')} />
    {:else}
      <table class="cmp">
        <thead>
          <tr><th>{t('profiles.compare.field')}</th><th>{result.a.label}</th><th>{result.b.label}</th></tr>
        </thead>
        <tbody>
          {#each result.rows as r (r.path)}
            <tr class:excl={r.excluded}>
              <td>{pathLabel(r.path)}{#if r.excluded}<br /><small>{t('profiles.compare.excluded')}</small>{/if}</td>
              <td class="ui-mono">{show(r.a)}</td>
              <td class="ui-mono">{show(r.b)}</td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  {/if}
</section>

<Modal
  open={deleting !== null}
  title={t('profiles.delete.title', { name: deleting?.name ?? '' })}
  danger
  confirmLabel={t('profiles.delete')}
  onconfirm={confirmDelete}
  oncancel={() => (deleting = null)}
>
  <p>{t('profiles.delete.body')}</p>
</Modal>

<style>
  .cp {
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  h3 {
    margin: var(--space-2) 0 0;
    font: 600 14px/20px var(--font-sans);
  }
  .muted {
    margin: 0;
    color: var(--ink-muted);
    font-size: 13px;
  }
  .row {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-3);
    align-items: flex-end;
  }
  fieldset {
    border: 1px solid var(--line);
    border-radius: var(--radius-2, 8px);
    padding: var(--space-2) var(--space-3);
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2) var(--space-4);
    margin: 0;
  }
  legend {
    font-size: 13px;
    color: var(--ink-muted);
  }
  .list {
    list-style: none;
    margin: 0;
    padding: 0;
    display: flex;
    flex-direction: column;
    gap: var(--space-3);
  }
  .list li {
    border-bottom: 1px solid var(--line);
    padding-bottom: var(--space-3);
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
  }
  .head,
  .acts {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    align-items: center;
  }
  .grow {
    flex: 1;
    min-width: 140px;
  }
  .file {
    display: flex;
    flex-direction: column;
    gap: var(--space-1);
  }
  .cmp {
    width: 100%;
    border-collapse: collapse;
    font-size: 14px;
  }
  .cmp th,
  .cmp td {
    text-align: left;
    padding: var(--space-1) var(--space-2);
    border-bottom: 1px solid var(--line);
    vertical-align: top;
    overflow-wrap: anywhere;
  }
  .excl {
    color: var(--ink-muted);
  }
  :global(.vp-phone) .muted {
    font-size: 14px;
  }
  :global(.vp-phone) .acts :global(.ui-btn) {
    min-height: 44px;
  }
</style>
