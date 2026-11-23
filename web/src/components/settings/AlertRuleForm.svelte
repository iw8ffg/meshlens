<script lang="ts">
  // Modulo di una regola di avviso: campi per tipo, validazione immediata (stessi limiti del server).
  import { untrack } from 'svelte'
  import {
    RULE_KINDS,
    channelOptions,
    draftErrors,
    type RuleDraft,
    type Trigger,
  } from '../../lib/alertrules'
  import { t } from '../../lib/i18n/index.svelte'
  import type { AlertRuleKind, Node } from '../../lib/types'
  import Banner from '../../lib/ui/Banner.svelte'
  import Button from '../../lib/ui/Button.svelte'
  import Card from '../../lib/ui/Card.svelte'
  import Check from '../../lib/ui/Check.svelte'
  import Field from '../../lib/ui/Field.svelte'
  import Segmented from '../../lib/ui/Segmented.svelte'
  import Select from '../../lib/ui/Select.svelte'
  import Switch from '../../lib/ui/Switch.svelte'
  import ZoneEditor from '../../lib/map/ZoneEditor.svelte'
  import { zonePoints } from '../../lib/alertrules'

  interface Props {
    draft: RuleDraft
    nodes: Node[]
    radios: { id: string; name?: string | null }[]
    mqttChannels: string[]
    busy: boolean
    error: string
    onsave: (d: RuleDraft) => void
    oncancel: () => void
  }
  let { draft, nodes, radios, mqttChannels, busy, error, onsave, oncancel }: Props = $props()

  // copia di lavoro: la bozza passata in ingresso non cambia finché non si salva
  let d = $state<RuleDraft>(untrack(() => ({ ...draft, polygon: draft.polygon.map((p) => [...p] as [number, number]) })))
  let touched = $state(false)
  let nodeQuery = $state('')

  const isNew = $derived(d.id === null)
  const errors = $derived(draftErrors(d))
  const hasErrors = $derived(Object.keys(errors).length > 0)
  const needsNode = $derived(d.kind === 'snr_low' || d.kind === 'geofence' || d.kind === 'battery' || d.kind === 'silent')
  const kindItems = $derived(RULE_KINDS.map((k) => ({ value: k, label: t(`alertrules.kind.${k}` as const) })))
  const triggerItems = $derived<{ value: Trigger; label: string }[]>([
    { value: 'exit', label: t('alertrules.field.triggerExit') },
    { value: 'enter', label: t('alertrules.field.triggerEnter') },
    { value: 'both', label: t('alertrules.field.triggerBoth') },
  ])
  const channels = $derived(channelOptions(radios, mqttChannels))

  const nodeName = (n: Node) => n.long_name || n.short_name || n.id
  const nodeChoices = $derived.by(() => {
    const q = nodeQuery.trim().toLowerCase()
    const list = nodes.filter((n) => q === '' || nodeName(n).toLowerCase().includes(q) || n.id.toLowerCase().includes(q))
    const picked = d.nodeId ? nodes.find((n) => n.id === d.nodeId) : undefined
    const shown = list.slice(0, 200)
    if (picked && !shown.includes(picked)) shown.unshift(picked)
    return shown.sort((a, b) => nodeName(a).localeCompare(nodeName(b)))
  })

  const thresholdLabel = $derived(
    d.kind === 'snr_low'
      ? t('alertrules.field.thresholdDb')
      : d.kind === 'battery'
        ? t('alertrules.field.thresholdPct')
        : t('alertrules.field.thresholdHours'),
  )
  const show = (k: keyof typeof errors): string | undefined => {
    const m = errors[k]
    return touched && m ? t(m) : undefined
  }

  function setKind(k: AlertRuleKind) {
    d.kind = k
    d.channel = null
  }

  function noSubmit(e: KeyboardEvent) {
    if (e.key === 'Enter' && (e.target as HTMLElement).tagName !== 'TEXTAREA') e.preventDefault()
  }

  function save() {
    touched = true
    if (!hasErrors && !busy) onsave(d)
  }
</script>

<Card>
  <!-- svelte-ignore a11y_no_static_element_interactions -->
  <div class="form" oninput={() => (touched = true)} onchange={() => (touched = true)} onkeydown={noSubmit}>
    <h3>{isNew ? t('alertrules.formNew') : t('alertrules.formEdit')}</h3>

    {#if isNew}
      <div class="grp">
        <span class="ui-lbl">{t('alertrules.kindLabel')}</span>
        <Segmented label={t('alertrules.kindLabel')} items={kindItems} value={d.kind} onchange={setKind} />
      </div>
    {:else}
      <p class="kind">{t(`alertrules.kind.${d.kind}` as const)}</p>
    {/if}

    <Field label={t('alertrules.field.name')} for="ar-name" error={show('name')}>
      {#snippet children({ describedby, invalid })}
        <input id="ar-name" class="ui-input" type="text" maxlength="80" autocomplete="off" aria-describedby={describedby} aria-invalid={invalid} bind:value={d.name} />
      {/snippet}
    </Field>

    <Field label={t('alertrules.field.node')} for="ar-node" error={show('node')}>
      {#snippet children({ describedby, invalid })}
        <input class="ui-input" type="search" autocomplete="off" placeholder={t('alertrules.field.searchNode')} aria-label={t('alertrules.field.searchNode')} bind:value={nodeQuery} />
        <Select id="ar-node" aria-describedby={describedby} aria-invalid={invalid} value={d.nodeId ?? ''} onchange={(e) => (d.nodeId = e.currentTarget.value || null)}>
          {#if !needsNode}<option value="">{t('alertrules.field.anyNode')}</option>{:else}<option value="" disabled>{t('alertrules.field.node')}</option>{/if}
          {#each nodeChoices as n (n.id)}
            <option value={n.id}>{nodeName(n)} ({n.id})</option>
          {/each}
        </Select>
      {/snippet}
    </Field>

    {#if d.kind === 'keyword'}
      <Field label={t('alertrules.field.channel')} for="ar-channel">
        {#snippet children({ describedby })}
          <Select id="ar-channel" aria-describedby={describedby} value={d.channel ?? ''} onchange={(e) => (d.channel = e.currentTarget.value || null)}>
            <option value="">{t('alertrules.field.anyChannel')}</option>
            {#each channels as c (c.value)}
              <option value={c.value}>{c.label}</option>
            {/each}
          </Select>
        {/snippet}
      </Field>
      <Field label={t('alertrules.field.words')} for="ar-words" hint={t('alertrules.field.wordsHint')} error={show('words')}>
        {#snippet children({ describedby, invalid })}
          <textarea id="ar-words" class="ui-input" rows="2" aria-describedby={describedby} aria-invalid={invalid} bind:value={d.wordsText}></textarea>
        {/snippet}
      </Field>
      <Check bind:checked={d.wholeWord} label={t('alertrules.field.wholeWord')} />
    {/if}

    {#if d.kind === 'snr_low' || d.kind === 'battery' || d.kind === 'silent'}
      <Field label={thresholdLabel} for="ar-thr" error={show('threshold')}>
        {#snippet children({ describedby, invalid })}
          <input id="ar-thr" class="ui-input num" type="text" inputmode="decimal" autocomplete="off" aria-describedby={describedby} aria-invalid={invalid} bind:value={d.threshold} />
        {/snippet}
      </Field>
    {/if}

    {#if d.kind === 'snr_low'}
      <div class="two">
        <Field label={t('alertrules.field.window')} for="ar-window" error={show('window')}>
          {#snippet children({ describedby, invalid })}
            <input id="ar-window" class="ui-input num" type="text" inputmode="numeric" autocomplete="off" aria-describedby={describedby} aria-invalid={invalid} bind:value={d.windowMin} />
          {/snippet}
        </Field>
        <Field label={t('alertrules.field.samples')} for="ar-samples" error={show('samples')}>
          {#snippet children({ describedby, invalid })}
            <input id="ar-samples" class="ui-input num" type="text" inputmode="numeric" autocomplete="off" aria-describedby={describedby} aria-invalid={invalid} bind:value={d.minSamples} />
          {/snippet}
        </Field>
      </div>
      <p class="ui-hint">{t('alertrules.hint.snrRestart')}</p>
    {/if}

    {#if d.kind === 'geofence'}
      <div class="grp">
        <span class="ui-lbl">{t('alertrules.field.trigger')}</span>
        <Segmented label={t('alertrules.field.trigger')} items={triggerItems} value={d.trigger} onchange={(v) => (d.trigger = v)} />
      </div>
      <div class="grp">
        <span class="ui-lbl">{t('alertrules.zone.label')}</span>
        <ZoneEditor value={d.polygon.length > 0 ? d.polygon : null} onchange={(p) => ((d.polygon = p ?? []), (touched = true))} />
        <p class="ui-hint">{d.polygon.length > 0 ? zonePoints(d.polygon.length) : t('alertrules.zone.empty')}</p>
        {#if touched && errors.polygon}<p class="ui-hint err">{t(errors.polygon)}</p>{/if}
        <p class="ui-hint">{t('alertrules.hint.geofencePrecision')}</p>
      </div>
    {/if}

    {#if d.kind === 'detection'}
      <Field label={t('alertrules.field.match')} for="ar-match" hint={t('alertrules.field.matchHint')} error={show('match')}>
        {#snippet children({ describedby, invalid })}
          <input id="ar-match" class="ui-input" type="text" autocomplete="off" aria-describedby={describedby} aria-invalid={invalid} bind:value={d.match} />
        {/snippet}
      </Field>
      <p class="ui-hint">{t('alertrules.hint.detectionMqtt')}</p>
    {/if}

    <Field label={t('alertrules.field.cooldown')} for="ar-cool" hint={t('alertrules.field.cooldownHint')} error={show('cooldown')}>
      {#snippet children({ describedby, invalid })}
        <input id="ar-cool" class="ui-input num" type="text" inputmode="numeric" autocomplete="off" aria-describedby={describedby} aria-invalid={invalid} bind:value={d.cooldownMin} />
      {/snippet}
    </Field>

    <Switch bind:checked={d.enabled} label={t('alertrules.field.enabled')} />

    {#if error}<Banner kind="danger" title={error} />{/if}

    <div class="row">
      <Button kind="primary" disabled={busy || hasErrors} onclick={save}>{t('alertrules.save')}</Button>
      <Button disabled={busy} onclick={oncancel}>{t('alertrules.cancel')}</Button>
    </div>
  </div>
</Card>

<style>
  .form { display: flex; flex-direction: column; gap: var(--space-3); color: var(--ink); }
  h3 { margin: 0; font: 600 15px/20px var(--font-sans); }
  p { margin: 0; }
  .kind { font: 600 14px/20px var(--font-sans); color: var(--ink-muted); }
  .grp { display: flex; flex-direction: column; gap: var(--space-2); }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-3); }
  .row { display: flex; gap: var(--space-2); flex-wrap: wrap; }
  .num { max-width: 160px; }
  .err { color: var(--danger); }
  textarea { min-height: 64px; resize: vertical; }
  :global(.vp-phone) .two { grid-template-columns: 1fr; }
  :global(.vp-phone) .ui-hint { font-size: 14px; line-height: 20px; }
</style>
